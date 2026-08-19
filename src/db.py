from contextlib import contextmanager
import hashlib
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file efficiently in chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class Database:
    """SQLite manager for tracking file indexing states, hashes, and chunk statistics."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or settings.SQLITE_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    file_path TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            """)
            conn.commit()

    def get_file(self, file_path: str | Path) -> Optional[dict[str, Any]]:
        """Retrieve tracking record for a specific file path."""
        path_str = str(file_path)
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM indexed_files WHERE file_path = ?", (path_str,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def needs_reindexing(self, file_path: Path) -> tuple[bool, str, float, int]:
        """Check if file has changed compared to SQLite state.
        
        Returns:
            Tuple of (needs_reindex: bool, file_hash: str, mtime: float, file_size: int)
        """
        path_str = str(file_path)
        if not file_path.exists():
            return False, "", 0.0, 0

        stat = file_path.stat()
        mtime = stat.st_mtime
        file_size = stat.st_size
        file_hash = compute_file_hash(file_path)

        existing = self.get_file(path_str)
        if not existing:
            return True, file_hash, mtime, file_size

        if existing["status"] != "indexed":
            return True, file_hash, mtime, file_size

        # Check hash and modified time
        if existing["file_hash"] != file_hash or existing["file_size"] != file_size:
            return True, file_hash, mtime, file_size

        return False, file_hash, mtime, file_size

    def record_success(
        self,
        file_path: Path,
        file_hash: str,
        file_size: int,
        mtime: float,
        chunk_count: int,
    ) -> None:
        """Record a successfully indexed file."""
        path_str = str(file_path)
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO indexed_files (
                    file_path, file_name, file_hash, file_size, mtime, chunk_count, indexed_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'indexed', NULL)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    file_hash = excluded.file_hash,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    status = 'indexed',
                    error_message = NULL
                """,
                (path_str, file_path.name, file_hash, file_size, mtime, chunk_count, now),
            )
            conn.commit()

    def record_failure(self, file_path: Path, error_message: str) -> None:
        """Record an indexing failure for a file."""
        path_str = str(file_path)
        now = time.time()
        stat = file_path.stat() if file_path.exists() else None
        mtime = stat.st_mtime if stat else 0.0
        file_size = stat.st_size if stat else 0

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO indexed_files (
                    file_path, file_name, file_hash, file_size, mtime, chunk_count, indexed_at, status, error_message
                ) VALUES (?, ?, '', ?, ?, 0, ?, 'failed', ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    indexed_at = excluded.indexed_at,
                    status = 'failed',
                    error_message = excluded.error_message
                """,
                (path_str, file_path.name, file_size, mtime, now, error_message),
            )
            conn.commit()

    def remove_file(self, file_path: str | Path) -> None:
        """Remove a file from the tracking database."""
        path_str = str(file_path)
        with self._get_connection() as conn:
            conn.execute("DELETE FROM indexed_files WHERE file_path = ?", (path_str,))
            conn.commit()

    def list_all_files(self) -> list[dict[str, Any]]:
        """List all tracked files."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM indexed_files ORDER BY indexed_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate indexing statistics."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    COALESCE(SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END), 0) as indexed_files,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed_files,
                    COALESCE(SUM(chunk_count), 0) as total_chunks,
                    COALESCE(SUM(file_size), 0) as total_bytes,
                    MAX(indexed_at) as last_indexed_at
                FROM indexed_files
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}
