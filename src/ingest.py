import argparse
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
import time
from typing import Optional

# Ensure standard streams handle UTF-8 safely on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# pyrefly: ignore [missing-import]
from rich.console import Console
# pyrefly: ignore [missing-import]
from rich.table import Table

from src.chunker import RecursiveChunker
from src.config import settings
from src.db import Database
from src.embeddings import BaseEmbedder, OllamaEmbedder, get_embedder
from src.extractors.factory import ExtractorFactory
from src.vector_store import ChromaVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
console = Console(force_terminal=True, highlight=False)


@dataclass
class IngestionStats:
    total_scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    deleted: int = 0
    chunks_created: int = 0
    elapsed_time: float = 0.0


class IngestionPipeline:
    """Orchestrates end-to-end extraction, chunking, embedding, and storage."""

    def __init__(
        self,
        db: Optional[Database] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        embedder: Optional[BaseEmbedder] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        self.db = db or Database()
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedder = embedder or get_embedder()
        self.chunker = RecursiveChunker(
            chunk_size=chunk_size or settings.CHUNK_SIZE,
            chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        )

    def ingest_file(self, file_path: Path, force: bool = False) -> tuple[bool, int, Optional[str]]:
        """Ingest a single file.
        
        Returns:
            Tuple of (indexed: bool, chunks_created: int, error_message: Optional[str])
        """
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            return False, 0, f"File does not exist: {file_path}"

        if not ExtractorFactory.supports(file_path):
            return False, 0, f"Unsupported file type: {file_path.suffix}"

        needs_reindex, file_hash, mtime, file_size = self.db.needs_reindexing(file_path)
        if not needs_reindex and not force:
            logger.debug(f"Skipping unchanged file: {file_path.name}")
            return False, 0, None

        try:
            # 1. Extract text and metadata
            extractor = ExtractorFactory.get_extractor(file_path)
            doc = extractor.extract(file_path)

            if doc.is_empty:
                logger.warning(f"File is empty or contains no extractable text: {file_path.name}")
                self.db.record_failure(file_path, "File contains no extractable text")
                return False, 0, "Empty document"

            # 2. Chunk text
            base_meta = {
                **doc.metadata,
                "source": str(file_path),
                "file_name": file_path.name,
                "file_hash": file_hash,
            }
            chunks = self.chunker.chunk_text(doc.text, base_metadata=base_meta)

            if not chunks:
                self.db.record_failure(file_path, "Failed to produce any text chunks")
                return False, 0, "No chunks generated"

            # 3. Clean up any prior vectors for this source
            self.vector_store.delete_by_source(str(file_path))

            # 4. Generate embeddings
            texts = [c.text for c in chunks]
            embeddings = self.embedder.embed_documents(texts)

            # 5. Store in ChromaDB
            self.vector_store.add_chunks(chunks, embeddings)

            # 6. Record success in SQLite
            self.db.record_success(
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                mtime=mtime,
                chunk_count=len(chunks),
            )

            logger.info(f"Successfully indexed '{file_path.name}' ({len(chunks)} chunks, {doc.char_count} chars)")
            return True, len(chunks), None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to ingest '{file_path.name}': {error_msg}", exc_info=True)
            self.db.record_failure(file_path, error_msg)
            return False, 0, error_msg

    def sync_directory(
        self,
        dir_path: Path,
        recursive: bool = True,
        force: bool = False,
    ) -> IngestionStats:
        """Scan a folder, index new/modified files, and clean up deleted files."""
        dir_path = Path(dir_path).resolve()
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        start_time = time.time()
        stats = IngestionStats()

        # 1. Discover all candidate files
        pattern = "**/*" if recursive else "*"
        disk_files: set[Path] = set()
        for p in dir_path.glob(pattern):
            if p.is_file() and ExtractorFactory.supports(p):
                disk_files.add(p.resolve())

        stats.total_scanned = len(disk_files)

        # 2. Check for deleted files that are still recorded in SQLite
        tracked_files = self.db.list_all_files()
        dir_str = str(dir_path)
        for tracked in tracked_files:
            tracked_path = Path(tracked["file_path"]).resolve()
            # Only check files within this target directory
            if str(tracked_path).startswith(dir_str):
                if not tracked_path.exists():
                    logger.info(f"Detected deleted file: {tracked_path.name} — cleaning up vectors.")
                    self.vector_store.delete_by_source(str(tracked_path))
                    self.db.remove_file(str(tracked_path))
                    stats.deleted += 1

        # 3. Process disk files
        for file_path in disk_files:
            indexed, chunk_cnt, error = self.ingest_file(file_path, force=force)
            if indexed:
                stats.indexed += 1
                stats.chunks_created += chunk_cnt
            elif error:
                stats.failed += 1
            else:
                stats.skipped += 1

        stats.elapsed_time = time.time() - start_time
        return stats


def print_stats_table(stats_dict: dict) -> None:
    """Print nicely formatted SQLite stats."""
    table = Table(title="Personal AI Brain - Indexing Status", header_style="bold cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("Total Tracked Files", str(stats_dict.get("total_files", 0)))
    table.add_row("Successfully Indexed", str(stats_dict.get("indexed_files", 0)))
    table.add_row("Failed Files", str(stats_dict.get("failed_files", 0)))
    table.add_row("Total Vector Chunks", str(stats_dict.get("total_chunks", 0)))
    
    total_bytes = stats_dict.get("total_bytes", 0)
    size_mb = f"{total_bytes / (1024 * 1024):.2f} MB"
    table.add_row("Total Indexed Size", size_mb)

    last_indexed = stats_dict.get("last_indexed_at")
    if last_indexed:
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_indexed))
        table.add_row("Last Indexed At", time_str)

    console.print(table)


def peek_file(file_path: Path, max_chars: int = 2000) -> None:
    """Extract and display raw text from a document without indexing."""
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        console.print(f"[bold red]File not found:[/bold red] {file_path}")
        return

    if not ExtractorFactory.supports(file_path):
        console.print(f"[bold red]Unsupported file type:[/bold red] {file_path.suffix}")
        return

    try:
        extractor = ExtractorFactory.get_extractor(file_path)
        doc = extractor.extract(file_path)

        meta_table = Table(title=f"Document Metadata: {file_path.name}", header_style="bold cyan")
        meta_table.add_column("Property", style="bold white")
        meta_table.add_column("Value", style="green")

        meta_table.add_row("File Path", str(file_path))
        meta_table.add_row("Total Characters", str(doc.char_count))
        meta_table.add_row("Total Words", str(len(doc.text.split())))
        for k, v in doc.metadata.items():
            meta_table.add_row(k.replace("_", " ").title(), str(v))

        console.print(meta_table)

        console.print(f"\n[bold yellow]--- Raw Extracted Text (First {max_chars} chars) ---[/bold yellow]")
        if doc.is_empty:
            console.print("[bold red][WARNING: Extracted text is completely empty!][/bold red]")
        else:
            preview = doc.text[:max_chars]
            console.print(preview)
            if len(doc.text) > max_chars:
                console.print(f"\n[dim]... [truncated {len(doc.text) - max_chars} characters] ...[/dim]")

    except Exception as e:
        console.print(f"[bold red]Extraction failed with error:[/bold red] {e}")


def peek_chunks(file_path: Path, chunk_size: int = settings.CHUNK_SIZE, chunk_overlap: int = settings.CHUNK_OVERLAP) -> None:
    """Extract and display all chunks and boundaries for a document."""
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        console.print(f"[bold red]File not found:[/bold red] {file_path}")
        return

    try:
        extractor = ExtractorFactory.get_extractor(file_path)
        doc = extractor.extract(file_path)
        chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        base_meta = {**doc.metadata, "source": str(file_path), "file_name": file_path.name}
        chunks = chunker.chunk_text(doc.text, base_metadata=base_meta)

        console.print(f"[bold cyan]Generated {len(chunks)} chunks for '{file_path.name}' (chunk_size={chunk_size}, overlap={chunk_overlap}):[/bold cyan]\n")
        for c in chunks:
            console.print(f"[bold magenta]=== Chunk {c.chunk_index} [Chars {c.start_char}:{c.end_char} | Len: {len(c.text)}] ID: {c.chunk_id} ===[/bold magenta]")
            console.print(c.text)
            console.print("[dim]------------------------------------------------------------[/dim]")

    except Exception as e:
        console.print(f"[bold red]Chunking inspection failed:[/bold red] {e}")


def query_store(query_text: str, top_k: int = 5, use_mock: bool = False) -> None:
    """Run a test semantic retrieval query directly against ChromaDB."""
    embedder = get_embedder(use_mock=use_mock)
    vector_store = ChromaVectorStore()

    if vector_store.count() == 0:
        console.print("[bold yellow]Vector database is currently empty. Run ingestion first.[/bold yellow]")
        return

    console.print(f"[bold cyan]Querying vector store:[/bold cyan] '{query_text}' (top_k={top_k})")
    query_vec = embedder.embed_text(query_text)
    results = vector_store.query_by_embedding(query_vec, top_k=top_k)

    if not results:
        console.print("[yellow]No relevant chunks found.[/yellow]")
        return

    for idx, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        score = r.get("score", 0.0)
        source = meta.get("file_name") or meta.get("source", "Unknown")
        chunk_idx = meta.get("chunk_index", "?")
        text_preview = r.get("text", "").strip()

        console.print(f"\n[bold green]Match {idx} [Score: {score:.4f}] - Source: {source} (Chunk #{chunk_idx})[/bold green]")
        console.print(text_preview)
        console.print("[dim]" + "-" * 60 + "[dim]")


def main():
    parser = argparse.ArgumentParser(description="Personal AI Brain - Document Ingestion CLI")
    parser.add_argument("--dir", type=str, default=str(settings.DOCUMENTS_DIR), help="Directory to scan and index")
    parser.add_argument("--file", type=str, help="Index a specific single file")
    parser.add_argument("--peek", type=str, help="Peek at raw extracted text and metadata for a file without indexing")
    parser.add_argument("--peek-chunks", type=str, help="Inspect generated chunks and boundary splits for a file")
    parser.add_argument("--query", type=str, help="Run a test query against indexed chunks in ChromaDB")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of unchanged files")
    parser.add_argument("--mock-embeddings", action="store_true", help="Use mock embedder (for testing without Ollama)")
    parser.add_argument("--stats", action="store_true", help="Display current indexing statistics and exit")
    parser.add_argument("--clear", action="store_true", help="Clear all vectors and tracking data")

    args = parser.parse_args()

    if args.peek:
        peek_file(Path(args.peek))
        return

    if args.peek_chunks:
        peek_chunks(Path(args.peek_chunks))
        return

    if args.query:
        query_store(args.query, use_mock=args.mock_embeddings)
        return

    db = Database()
    vector_store = ChromaVectorStore()

    if args.clear:
        console.print("[bold red]Clearing all vectors and SQLite records...[/bold red]")
        vector_store.clear()
        for f in db.list_all_files():
            db.remove_file(f["file_path"])
        console.print("[bold green]All vector data and SQLite records cleared successfully.[/bold green]")
        return

    if args.stats:
        print_stats_table(db.get_stats())
        return

    embedder = get_embedder(use_mock=args.mock_embeddings)
    if not args.mock_embeddings and isinstance(embedder, OllamaEmbedder):
        if not embedder.is_available():
            console.print(
                f"[yellow]Warning: Ollama model '{settings.EMBEDDING_MODEL}' is not currently reachable at {settings.OLLAMA_BASE_URL}.[/yellow]\n"
                "[yellow]You can use --mock-embeddings for offline testing or start Ollama with 'ollama run nomic-embed-text'.[/yellow]"
            )

    pipeline = IngestionPipeline(db=db, vector_store=vector_store, embedder=embedder)

    if args.file:
        file_path = Path(args.file)
        console.print(f"[bold blue]Indexing file:[/bold blue] {file_path}")
        indexed, chunks, err = pipeline.ingest_file(file_path, force=args.force)
        if indexed:
            console.print(f"[bold green]Successfully indexed {file_path.name} with {chunks} chunks![/bold green]")
        elif err:
            console.print(f"[bold red]Failed: {err}[/bold red]")
        else:
            console.print("[bold yellow]File was already up-to-date (skipped).[/bold yellow]")
    else:
        scan_dir = Path(args.dir)
        console.print(f"[bold blue]Scanning and syncing directory:[/bold blue] {scan_dir}")
        stats = pipeline.sync_directory(scan_dir, force=args.force)

        summary_table = Table(title="Ingestion Summary", header_style="bold magenta")
        summary_table.add_column("Category", style="bold")
        summary_table.add_column("Count", style="cyan")

        summary_table.add_row("Files Scanned", str(stats.total_scanned))
        summary_table.add_row("Files Indexed", str(stats.indexed))
        summary_table.add_row("Files Skipped (Unchanged)", str(stats.skipped))
        summary_table.add_row("Files Failed", str(stats.failed))
        summary_table.add_row("Deleted Files Removed", str(stats.deleted))
        summary_table.add_row("Chunks Created", str(stats.chunks_created))
        summary_table.add_row("Elapsed Time", f"{stats.elapsed_time:.2f}s")

        console.print(summary_table)

    print_stats_table(db.get_stats())


if __name__ == "__main__":
    main()
