import shutil
import tempfile
import time
import unittest
from pathlib import Path

from src.db import Database
from src.embeddings import MockEmbedder
from src.ingest import IngestionPipeline
from src.vector_store import ChromaVectorStore


class TestIngestionPipeline(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.docs_dir = self.test_dir / "documents"
        self.docs_dir.mkdir(parents=True)
        self.db_path = self.test_dir / "brain.db"
        self.chroma_dir = self.test_dir / "chroma"

        self.db = Database(db_path=self.db_path)
        self.vector_store = ChromaVectorStore(
            persist_dir=self.chroma_dir,
            collection_name="test_brain",
        )
        self.embedder = MockEmbedder(dimension=64)

        self.pipeline = IngestionPipeline(
            db=self.db,
            vector_store=self.vector_store,
            embedder=self.embedder,
            chunk_size=100,
            chunk_overlap=20,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_end_to_end_directory_sync(self):
        # 1. Create initial files
        file1 = self.docs_dir / "guide.txt"
        file1.write_text("This is an introductory guide on local RAG infrastructure.", encoding="utf-8")

        file2 = self.docs_dir / "notes.md"
        file2.write_text("# Personal Brain\n\nNotes about Ollama, ChromaDB, and FastAPI.", encoding="utf-8")

        # Initial sync
        stats = self.pipeline.sync_directory(self.docs_dir)
        self.assertEqual(stats.total_scanned, 2)
        self.assertEqual(stats.indexed, 2)
        self.assertEqual(stats.skipped, 0)
        self.assertGreater(stats.chunks_created, 0)
        self.assertEqual(self.vector_store.count(), stats.chunks_created)

        # 2. Second sync without modifications -> should skip all
        stats2 = self.pipeline.sync_directory(self.docs_dir)
        self.assertEqual(stats2.total_scanned, 2)
        self.assertEqual(stats2.indexed, 0)
        self.assertEqual(stats2.skipped, 2)

        # 3. Modify one file and add another
        time.sleep(0.01)
        file1.write_text("Updated guide with much more detailed content for indexing.", encoding="utf-8")
        file3 = self.docs_dir / "extra.txt"
        file3.write_text("A third document added later.", encoding="utf-8")

        stats3 = self.pipeline.sync_directory(self.docs_dir)
        self.assertEqual(stats3.total_scanned, 3)
        self.assertEqual(stats3.indexed, 2)  # file1 modified, file3 new
        self.assertEqual(stats3.skipped, 1)  # file2 unchanged

        # 4. Delete file2
        file2.unlink()
        stats4 = self.pipeline.sync_directory(self.docs_dir)
        self.assertEqual(stats4.deleted, 1)
        self.assertEqual(stats4.skipped, 2)  # file1 and file3 unchanged
        self.assertIsNone(self.db.get_file(file2))


if __name__ == "__main__":
    unittest.main()
