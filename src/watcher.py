import argparse
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import sys
import threading
import time
from typing import Callable, Optional


# Ensure standard streams handle UTF-8 safely on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
try:
    from watchdog.observers.polling import PollingObserver
except ImportError:
    PollingObserver = Observer


from src.bookmarks import BookmarkItem, ChromeBookmarkParser
from src.config import settings
from src.db import Database
from src.embeddings import BaseEmbedder, get_embedder
from src.extractors.factory import ExtractorFactory
from src.ingest import IngestionPipeline
from src.vector_store import ChromaVectorStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("src.watcher")
console = Console(force_terminal=True, highlight=False)


# Ignored filename prefixes and patterns (temporary, lock, or swap files)
IGNORED_PREFIXES = (".", "~", "#", ".#", ".~")
IGNORED_SUFFIXES = (".tmp", ".temp", ".swp", ".swo", ".crdownload", ".part", ".bak")
IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".idea", ".vscode", "node_modules", "rag", "chroma_db", "data"}



def is_supported_document(file_path: Path) -> bool:
    """Check if a file path is a supported, non-temporary document file."""
    path = Path(file_path)

    # 1. Ignore if any parent directory is in ignored directories
    for part in path.parts[:-1]:
        if part in IGNORED_DIRS or (part.startswith(".") and part != "."):
            return False

    file_name = path.name

    # 2. Ignore hidden or temporary prefix patterns
    for prefix in IGNORED_PREFIXES:
        if file_name.startswith(prefix):
            return False

    # 3. Ignore temporary suffix patterns
    for suffix in IGNORED_SUFFIXES:
        if file_name.lower().endswith(suffix):
            return False

    # 4. Must have a supported extension
    return ExtractorFactory.supports(path)


class FileChangeHandler(FileSystemEventHandler):
    """Debounced, thread-safe file event handler for real-time document indexing."""

    def __init__(
        self,
        pipeline: IngestionPipeline,
        debounce_delay: float = 1.5,
        settle_delay: float = 0.5,
        max_settle_retries: int = 5,
        on_event_callback: Optional[Callable[[str, Path, str], None]] = None,
    ):
        super().__init__()
        self.pipeline = pipeline
        self.debounce_delay = debounce_delay
        self.settle_delay = settle_delay
        self.max_settle_retries = max_settle_retries
        self.on_event_callback = on_event_callback

        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._active_tasks: set[str] = set()

    def _cancel_timer(self, file_key: str) -> None:
        """Cancel any pending debounce timer for a file."""
        with self._lock:
            timer = self._timers.pop(file_key, None)
            if timer:
                timer.cancel()

    def _schedule_upsert(self, file_path: Path) -> None:
        """Schedule a debounced upsert (create or modify) operation."""
        file_path = file_path.resolve()
        if not is_supported_document(file_path):
            return

        file_key = str(file_path)

        with self._lock:
            # Cancel any existing debounce timer for this file
            if file_key in self._timers:
                self._timers[file_key].cancel()

            # Schedule new execution after debounce_delay
            timer = threading.Timer(
                self.debounce_delay,
                self._execute_upsert,
                args=[file_path],
            )
            self._timers[file_key] = timer
            timer.daemon = True
            timer.start()
            logger.debug(f"Debounce scheduled for: {file_path.name} in {self.debounce_delay}s")

    def _schedule_delete(self, file_path: Path) -> None:
        """Schedule or execute a file deletion cleanup."""
        file_path = file_path.resolve()
        file_key = str(file_path)

        # Cancel any pending upsert timer for this deleted file
        self._cancel_timer(file_key)

        # Execute deletion immediately in a worker thread
        threading.Thread(target=self._execute_delete, args=[file_path], daemon=True).start()

    def _wait_for_file_settle(self, file_path: Path) -> bool:
        """Wait until a file has finished writing (size and mtime stable, readable)."""
        if not file_path.exists():
            return False

        last_size = -1
        last_mtime = -1.0

        for attempt in range(self.max_settle_retries):
            try:
                stat = file_path.stat()
                current_size = stat.st_size
                current_mtime = stat.st_mtime

                # Check if size and mtime are identical to previous check
                if attempt > 0 and current_size == last_size and current_mtime == last_mtime:
                    # Verify readable
                    with open(file_path, "rb") as f:
                        f.read(1024)
                    return True

                last_size = current_size
                last_mtime = current_mtime
                time.sleep(self.settle_delay)

            except (PermissionError, FileNotFoundError, OSError):
                # File is locked by another process writing to it or temporarily unavailable
                time.sleep(self.settle_delay)

        # Final check if file can be opened
        try:
            with open(file_path, "rb") as f:
                f.read(1024)
            return True
        except Exception:
            return False

    def _execute_upsert(self, file_path: Path) -> None:
        """Execute the ingestion pipeline for a created/modified file."""
        file_key = str(file_path)

        with self._lock:
            self._timers.pop(file_key, None)
            if file_key in self._active_tasks:
                return
            self._active_tasks.add(file_key)

        try:
            if not file_path.exists():
                logger.debug(f"File was deleted before debounce completed: {file_path.name}")
                return

            if not self._wait_for_file_settle(file_path):
                logger.warning(f"File write did not settle, skipping for now: {file_path.name}")
                if self.on_event_callback:
                    self.on_event_callback("FAILED", file_path, "File write did not settle")
                return

            # Ingest via pipeline (includes SHA-256 hash check)
            indexed, chunk_cnt, error = self.pipeline.ingest_file(file_path, force=False)

            if indexed:
                console.print(
                    f"[bold green][INDEXED][/bold green] '{file_path.name}' "
                    f"([cyan]{chunk_cnt} chunks[/cyan])"
                )
                if self.on_event_callback:
                    self.on_event_callback("INDEXED", file_path, f"{chunk_cnt} chunks")
            elif error:
                console.print(f"[bold red][FAILED][/bold red] '{file_path.name}': {error}")
                if self.on_event_callback:
                    self.on_event_callback("FAILED", file_path, error)
            else:
                logger.info(f"[SKIPPED] '{file_path.name}' (content hash unchanged)")
                if self.on_event_callback:
                    self.on_event_callback("SKIPPED", file_path, "Unchanged hash")

        except Exception as e:
            logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
            if self.on_event_callback:
                self.on_event_callback("ERROR", file_path, str(e))
        finally:
            with self._lock:
                self._active_tasks.discard(file_key)

    def _execute_delete(self, file_path: Path) -> None:
        """Purge vectors and database tracking for a deleted file."""
        file_key = str(file_path)
        try:
            logger.info(f"Purging deleted document from index: {file_path.name}")
            self.pipeline.vector_store.delete_by_source(file_key)
            self.pipeline.db.remove_file(file_key)
            console.print(f"[bold yellow][DELETED][/bold yellow] Purged vectors for '{file_path.name}'")
            if self.on_event_callback:
                self.on_event_callback("DELETED", file_path, "Purged from ChromaDB & SQLite")
        except Exception as e:
            logger.error(f"Failed to purge deleted file {file_path.name}: {e}", exc_info=True)
            if self.on_event_callback:
                self.on_event_callback("ERROR", file_path, str(e))

    # --- Watchdog Event Hooks ---

    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, (DirCreatedEvent, DirModifiedEvent)):
            return
        file_path = Path(event.src_path)
        if is_supported_document(file_path):
            console.print(f"[dim][EVENT][/dim] Detected creation: [cyan]{file_path.name}[/cyan]")
            self._schedule_upsert(file_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, (DirModifiedEvent, DirCreatedEvent)):
            return
        file_path = Path(event.src_path)
        if is_supported_document(file_path):
            console.print(f"[dim][EVENT][/dim] Detected modification: [cyan]{file_path.name}[/cyan]")
            self._schedule_upsert(file_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if isinstance(event, (DirDeletedEvent, DirModifiedEvent)):
            return
        file_path = Path(event.src_path)
        if is_supported_document(file_path):
            console.print(f"[dim][EVENT][/dim] Detected deletion: [yellow]{file_path.name}[/yellow]")
            self._schedule_delete(file_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, DirMovedEvent):
            return
        # Handle rename / move
        src_path = Path(event.src_path)
        dest_path = Path(getattr(event, "dest_path", ""))

        if is_supported_document(src_path):
            console.print(f"[dim][EVENT][/dim] Detected move/rename: [yellow]{src_path.name}[/yellow] -> [cyan]{dest_path.name}[/cyan]")
            self._schedule_delete(src_path)

        if is_supported_document(dest_path):
            self._schedule_upsert(dest_path)


class DocumentWatcher:
    """Manages the background watchdog observer lifecycle."""

    def __init__(
        self,
        watch_dir: Path,
        pipeline: Optional[IngestionPipeline] = None,
        debounce_delay: float = 1.5,
        settle_delay: float = 0.5,
        max_settle_retries: int = 5,
        recursive: bool = True,
        on_event_callback: Optional[Callable[[str, Path, str], None]] = None,
    ):
        self.watch_dir = Path(watch_dir).resolve()
        self.pipeline = pipeline or IngestionPipeline()
        self.debounce_delay = debounce_delay
        self.settle_delay = settle_delay
        self.max_settle_retries = max_settle_retries
        self.recursive = recursive
        self.on_event_callback = on_event_callback

        self.handler = FileChangeHandler(
            pipeline=self.pipeline,
            debounce_delay=self.debounce_delay,
            settle_delay=self.settle_delay,
            max_settle_retries=self.max_settle_retries,
            on_event_callback=self.on_event_callback,
        )
        self.observer = Observer()
        self._is_running = False



    def start(self) -> None:
        """Start the filesystem observer."""
        if not self.watch_dir.exists():
            self.watch_dir.mkdir(parents=True, exist_ok=True)

        self.observer.schedule(self.handler, str(self.watch_dir), recursive=self.recursive)
        self.observer.start()
        self._is_running = True
        logger.info(f"DocumentWatcher started on: {self.watch_dir} (recursive={self.recursive})")

    def stop(self) -> None:
        """Stop the filesystem observer and clean up debounce timers."""
        if self._is_running:
            self.observer.stop()
            self.observer.join(timeout=5.0)
            self._is_running = False
            logger.info("DocumentWatcher stopped.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class ChromeBookmarkWatcher:
    """Continuously monitors Chrome Bookmarks and synchronizes additions and deletions."""

    def __init__(
        self,
        pipeline: IngestionPipeline,
        custom_bookmarks_path: Optional[Path] = None,
        poll_interval: float = 15.0,
    ):
        self.pipeline = pipeline
        self.custom_bookmarks_path = custom_bookmarks_path
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_state_hash = ""

    def _compute_state_hash(self, bookmarks: list[BookmarkItem]) -> str:
        s = "".join(f"{b.id}:{b.title}:{b.url}:{b.folder}" for b in bookmarks)
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def sync_bookmarks(self) -> None:
        """Diff disk bookmarks with SQLite state and sync additions and deletions."""
        try:
            current_bookmarks = ChromeBookmarkParser.discover_all_bookmarks(self.custom_bookmarks_path)
            state_hash = self._compute_state_hash(current_bookmarks)
            if state_hash == self._last_state_hash:
                return

            self._last_state_hash = state_hash
            current_urls = {b.url: b for b in current_bookmarks}
            tracked = {b["url"]: b for b in self.pipeline.db.list_all_bookmarks()}

            # 1. Identify deleted bookmarks (purge ChromaDB vectors and SQLite entry)
            for url, row in tracked.items():
                if row.get("status") == "indexed" and url not in current_urls:
                    logger.info(f"Bookmark removed from Chrome: '{row.get('title')}' -> {url}")
                    self.pipeline.delete_bookmark(url)

            # 2. Ingest new or modified bookmarks
            for url, bm in current_urls.items():
                if url not in tracked or tracked[url].get("status") != "indexed":
                    logger.info(f"New or pending bookmark found: '{bm.title}' -> {url}")
                    self.pipeline.ingest_bookmark(bm)

        except Exception as e:
            logger.error(f"Error during bookmark sync: {e}", exc_info=True)

    def _run_loop(self) -> None:
        self.sync_bookmarks()
        while self._running:
            time.sleep(self.poll_interval)
            if not self._running:
                break
            self.sync_bookmarks()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="ChromeBookmarkWatcher", daemon=True)
        self._thread.start()
        logger.info(f"Chrome bookmark watcher started (interval: {self.poll_interval}s)")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Chrome bookmark watcher stopped")


def run_watcher(
    watch_dir: Path,
    debounce_delay: float = 1.5,
    settle_delay: float = 0.5,
    initial_sync: bool = False,
    watch_bookmarks: bool = True,
    bookmarks_path: Optional[Path] = None,
    use_mock: bool = False,
) -> None:
    """Run the watcher CLI process until interrupted."""
    watch_dir = Path(watch_dir).resolve()
    watch_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        f"[bold cyan]Personal AI Brain - Knowledge Base Watcher[/bold cyan]\n"
        f"[bold white]Documents Directory:[/bold white] [green]{watch_dir}[/green]\n"
        f"[bold white]Watch Chrome Bookmarks:[/bold white] [green]{'Enabled' if watch_bookmarks else 'Disabled'}[/green]\n"
        f"[bold white]Debounce:[/bold white] [yellow]{debounce_delay}s[/yellow] | "
        f"[bold white]Supported Types:[/bold white] [magenta].pdf, .docx, .txt, .md, Chrome Bookmarks[/magenta]",
        border_style="cyan",
    ))

    embedder = get_embedder(use_mock=use_mock)
    db = Database()
    vector_store = ChromaVectorStore()
    pipeline = IngestionPipeline(db=db, vector_store=vector_store, embedder=embedder)

    if initial_sync:
        console.print("[bold blue]Performing initial directory sync...[/bold blue]")
        stats = pipeline.sync_directory(watch_dir)
        console.print(
            f"[green]Initial sync complete:[/green] {stats.indexed} indexed, "
            f"{stats.skipped} skipped, {stats.deleted} deleted."
        )

    doc_watcher = DocumentWatcher(
        watch_dir=watch_dir,
        pipeline=pipeline,
        debounce_delay=debounce_delay,
        settle_delay=settle_delay,
    )

    bm_watcher = None
    if watch_bookmarks:
        bm_watcher = ChromeBookmarkWatcher(
            pipeline=pipeline,
            custom_bookmarks_path=bookmarks_path,
            poll_interval=settings.BOOKMARK_WATCH_INTERVAL,
        )

    doc_watcher.start()
    if bm_watcher:
        bm_watcher.start()

    console.print("[bold green]✓ Watcher active and listening for document & bookmark changes... (Press Ctrl+C to stop)[/bold green]\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping watchers gracefully...[/yellow]")
    finally:
        doc_watcher.stop()
        if bm_watcher:
            bm_watcher.stop()
        console.print("[bold green]All watchers terminated.[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Personal AI Brain - Real-Time Knowledge Watcher")
    parser.add_argument(
        "--dir",
        type=str,
        default=str(settings.DOCUMENTS_DIR),
        help="Directory to watch for document changes",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=1.5,
        help="Debounce delay in seconds for rapid file events",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=0.5,
        help="Settle delay in seconds to ensure file write has finished",
    )
    parser.add_argument(
        "--initial-sync",
        action="store_true",
        help="Perform full sync of directory on startup before watching",
    )
    parser.add_argument(
        "--no-bookmarks",
        action="store_true",
        help="Disable Chrome bookmarks watching",
    )
    parser.add_argument(
        "--bookmarks-file",
        type=str,
        help="Path to Chrome Bookmarks or AccountBookmarks file",
    )
    parser.add_argument(
        "--mock-embeddings",
        action="store_true",
        help="Use mock embeddings for testing without Ollama",
    )

    args = parser.parse_args()
    bm_path = Path(args.bookmarks_file) if args.bookmarks_file else None

    run_watcher(
        watch_dir=Path(args.dir),
        debounce_delay=args.debounce,
        settle_delay=args.settle,
        initial_sync=args.initial_sync,
        watch_bookmarks=not args.no_bookmarks,
        bookmarks_path=bm_path,
        use_mock=args.mock_embeddings,
    )


if __name__ == "__main__":
    main()

