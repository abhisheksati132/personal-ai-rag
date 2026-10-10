from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from src.db import Database
from src.embeddings import MockEmbedder
from src.ingest import IngestionPipeline
from src.vector_store import ChromaVectorStore
from src.watcher import (
    DocumentWatcher,
    FileChangeHandler,
    is_supported_document,
)


class TestFileFiltering(unittest.TestCase):
    """Test file filtering and extension support logic."""

    def test_supported_document_types(self):
        self.assertTrue(is_supported_document(Path("test.pdf")))
        self.assertTrue(is_supported_document(Path("documents/notes.md")))
        self.assertTrue(is_supported_document(Path("C:/docs/report.docx")))
        self.assertTrue(is_supported_document(Path("guide.txt")))

    def test_unsupported_document_types(self):
        self.assertFalse(is_supported_document(Path("image.jpg")))
        self.assertFalse(is_supported_document(Path("picture.png")))
        self.assertFalse(is_supported_document(Path("program.exe")))
        self.assertFalse(is_supported_document(Path("script.py")))
        self.assertFalse(is_supported_document(Path("data.json")))

    def test_hidden_and_temp_files(self):
        self.assertFalse(is_supported_document(Path(".env")))
        self.assertFalse(is_supported_document(Path(".hidden_doc.txt")))
        self.assertFalse(is_supported_document(Path(".git/config")))
        self.assertFalse(is_supported_document(Path(".venv/lib/site-packages/test.py")))
        self.assertFalse(is_supported_document(Path("~$WordDoc.docx")))
        self.assertFalse(is_supported_document(Path("data.tmp")))
        self.assertFalse(is_supported_document(Path("notes.txt.swp")))
        self.assertFalse(is_supported_document(Path("download.pdf.crdownload")))


def wait_for_condition(predicate, timeout=4.0, interval=0.03):
    """Wait up to timeout seconds for predicate to return truthy value."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return predicate()


class TestFileChangeHandler(unittest.TestCase):
    """Test debounce and event dispatching in FileChangeHandler."""

    def setUp(self):
        self.pipeline = MagicMock()
        self.pipeline.ingest_file.return_value = (True, 2, None)
        self.handler = FileChangeHandler(
            pipeline=self.pipeline,
            debounce_delay=0.1,
            settle_delay=0.01,
            max_settle_retries=2,
        )

    def test_debounce_collapses_rapid_events(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello World")
            temp_path = Path(f.name)

        try:
            # Simulate 4 rapid modifications in quick succession
            for _ in range(4):
                self.handler.on_modified(FileModifiedEvent(str(temp_path)))
                time.sleep(0.02)

            # Pipeline should not be called yet because debounce delay (0.1s) is still pending
            self.pipeline.ingest_file.assert_not_called()

            # Wait for debounce to fire
            wait_for_condition(lambda: self.pipeline.ingest_file.call_count == 1, timeout=3.0)

            # Ingest should have been called exactly once
            self.assertEqual(self.pipeline.ingest_file.call_count, 1)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_delete_event_triggers_purge(self):
        fake_path = Path("c:/docs/deleted_document.pdf")
        self.handler.on_deleted(FileDeletedEvent(str(fake_path)))

        wait_for_condition(
            lambda: self.pipeline.vector_store.delete_by_source.called and self.pipeline.db.remove_file.called,
            timeout=3.0,
        )

        self.pipeline.vector_store.delete_by_source.assert_called_with(str(fake_path.resolve()))
        self.pipeline.db.remove_file.assert_called_with(str(fake_path.resolve()))

    def test_move_event_purges_source_and_indexes_dest(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"Moved content")
            dest_path = Path(f.name)

        src_path = Path("c:/docs/old_name.docx")

        try:
            event = FileMovedEvent(src_path=str(src_path), dest_path=str(dest_path))
            self.handler.on_moved(event)

            # Verify old path purged
            wait_for_condition(lambda: self.pipeline.vector_store.delete_by_source.called, timeout=3.0)
            self.pipeline.vector_store.delete_by_source.assert_called_with(str(src_path.resolve()))

            # Verify new path scheduled for debounce
            wait_for_condition(lambda: self.pipeline.ingest_file.called, timeout=3.0)
            self.pipeline.ingest_file.assert_called_with(dest_path.resolve(), force=False)
        finally:
            if dest_path.exists():
                dest_path.unlink()

    def test_ignores_unsupported_events(self):
        self.handler.on_created(FileCreatedEvent("photo.jpg"))
        self.handler.on_modified(FileModifiedEvent("app.exe"))
        self.handler.on_deleted(FileDeletedEvent("~$temp.docx"))

        time.sleep(0.15)
        self.pipeline.ingest_file.assert_not_called()


class TestWatcherLiveIntegration(unittest.TestCase):
    """End-to-end integration test with live directory watching and MockEmbedder."""

    def test_live_watch_flow(self):
        tmp_dir = tempfile.mkdtemp()
        watch_path = Path(tmp_dir).resolve()
        db_path = watch_path / "test_brain.db"
        chroma_dir = watch_path / "test_chroma"

        try:
            db = Database(db_path=db_path)
            vector_store = ChromaVectorStore(persist_dir=chroma_dir, collection_name="test_watcher_live")
            embedder = MockEmbedder(dimension=128)
            pipeline = IngestionPipeline(db=db, vector_store=vector_store, embedder=embedder)

            events_logged = []

            def callback(action, path, details):
                events_logged.append((action, path.name, details))

            watcher = DocumentWatcher(
                watch_dir=watch_path,
                pipeline=pipeline,
                debounce_delay=0.1,
                settle_delay=0.02,
                max_settle_retries=3,
                on_event_callback=callback,
            )

            with watcher:
                # 1. Add file
                doc_file = (watch_path / "live_note.txt").resolve()
                doc_file.write_text("This is an introductory note about computer networks.", encoding="utf-8")

                # Wait for debounce and processing
                wait_for_condition(
                    lambda: db.get_file(doc_file) is not None and db.get_file(doc_file)["status"] == "indexed",
                    timeout=5.0,
                )

                # Verify indexed in SQLite and ChromaDB
                record = db.get_file(doc_file)
                self.assertIsNotNone(record)
                self.assertEqual(record["status"], "indexed")
                self.assertGreater(vector_store.count(), 0)

                # 2. Modify file
                doc_file.write_text("This is an updated note about compiler design and lexical analysis.", encoding="utf-8")
                wait_for_condition(
                    lambda: db.get_file(doc_file) is not None and db.get_file(doc_file)["file_hash"] != record["file_hash"],
                    timeout=5.0,
                )

                updated_record = db.get_file(doc_file)
                self.assertIsNotNone(updated_record)
                self.assertNotEqual(updated_record["file_hash"], record["file_hash"])

                # 3. Delete file
                doc_file.unlink()
                wait_for_condition(
                    lambda: db.get_file(doc_file) is None and vector_store.count() == 0,
                    timeout=5.0,
                )

                deleted_record = db.get_file(doc_file)
                self.assertIsNone(deleted_record)
                self.assertEqual(vector_store.count(), 0)

        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)



if __name__ == "__main__":
    unittest.main()
