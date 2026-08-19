import shutil
import tempfile
import time
import unittest
from pathlib import Path

from src.db import Database, compute_file_hash


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_brain.db"
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_lifecycle(self):
        file_path = self.test_dir / "doc.txt"
        file_path.write_text("Test content", encoding="utf-8")

        # Initial state: needs reindexing
        needs_reindex, fhash, mtime, fsize = self.db.needs_reindexing(file_path)
        self.assertTrue(needs_reindex)
        self.assertEqual(fhash, compute_file_hash(file_path))

        # Record success
        self.db.record_success(
            file_path=file_path,
            file_hash=fhash,
            file_size=fsize,
            mtime=mtime,
            chunk_count=3,
        )

        # Check retrieval
        rec = self.db.get_file(file_path)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["status"], "indexed")
        self.assertEqual(rec["chunk_count"], 3)

        # Immediate re-check should NOT need reindexing
        needs_reindex, _, _, _ = self.db.needs_reindexing(file_path)
        self.assertFalse(needs_reindex)

        # Modify file
        time.sleep(0.01)
        file_path.write_text("Modified new content", encoding="utf-8")

        # Now it should need reindexing
        needs_reindex, new_hash, _, _ = self.db.needs_reindexing(file_path)
        self.assertTrue(needs_reindex)
        self.assertNotEqual(fhash, new_hash)

    def test_stats_and_removal(self):
        file1 = self.test_dir / "f1.txt"
        file1.write_text("Doc 1", encoding="utf-8")
        file2 = self.test_dir / "f2.txt"
        file2.write_text("Doc 2", encoding="utf-8")

        self.db.record_success(file1, "hash1", 5, 100.0, 2)
        self.db.record_failure(file2, "Corrupt file")

        stats = self.db.get_stats()
        self.assertEqual(stats["total_files"], 2)
        self.assertEqual(stats["indexed_files"], 1)
        self.assertEqual(stats["failed_files"], 1)
        self.assertEqual(stats["total_chunks"], 2)

        # Remove file
        self.db.remove_file(file1)
        stats = self.db.get_stats()
        self.assertEqual(stats["total_files"], 1)
        self.assertEqual(stats["indexed_files"], 0)


if __name__ == "__main__":
    unittest.main()
