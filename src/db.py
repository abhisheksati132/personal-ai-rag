from contextlib import contextmanager
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Optional
import uuid

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
    """Unified database manager supporting both SQLite (local default) and PostgreSQL (Neon/Supabase)."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        database_url: Optional[str] = None,
    ):
        self.database_url = database_url or settings.DATABASE_URL
        self.is_postgres = bool(self.database_url and self.database_url.strip())
        if self.is_postgres:
            self.db_path = None
        else:
            self.db_path = Path(db_path or settings.SQLITE_DB_PATH)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        if self.is_postgres:
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(self.database_url, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            try:
                yield conn
            finally:
                conn.close()

    def _exec(self, conn, sql: str, params: tuple | list = ()):
        """Execute a SQL statement adapting placeholders for SQLite (?) vs Postgres (%s)."""
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        return conn.execute(sql, params)

    def _init_db(self) -> None:
        if self.is_postgres:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS indexed_files (
                        file_path TEXT PRIMARY KEY,
                        file_name TEXT NOT NULL,
                        file_hash TEXT NOT NULL,
                        file_size BIGINT NOT NULL,
                        mtime DOUBLE PRECISION NOT NULL,
                        chunk_count INTEGER DEFAULT 0,
                        indexed_at DOUBLE PRECISION NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS indexed_bookmarks (
                        bookmark_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL UNIQUE,
                        folder TEXT NOT NULL,
                        content_hash TEXT,
                        chunk_count INTEGER DEFAULT 0,
                        fetched_at DOUBLE PRECISION,
                        indexed_at DOUBLE PRECISION NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        sources TEXT,
                        provider TEXT,
                        model TEXT,
                        created_at DOUBLE PRECISION NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_files_indexed_at ON indexed_files(indexed_at);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bookmarks_indexed_at ON indexed_bookmarks(indexed_at);
                """)
        else:
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS indexed_bookmarks (
                        bookmark_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL UNIQUE,
                        folder TEXT NOT NULL,
                        content_hash TEXT,
                        chunk_count INTEGER DEFAULT 0,
                        fetched_at REAL,
                        indexed_at REAL NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        sources TEXT,
                        provider TEXT,
                        model TEXT,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)
                """)
                conn.commit()

    def get_file(self, file_path: str | Path) -> Optional[dict[str, Any]]:
        """Retrieve tracking record for a specific file path."""
        path_str = str(file_path)
        with self._get_connection() as conn:
            cursor = self._exec(conn, "SELECT * FROM indexed_files WHERE file_path = ?", (path_str,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_bookmark(self, bookmark_id_or_url: str) -> Optional[dict[str, Any]]:
        """Retrieve tracking record for a bookmark by id or URL."""
        with self._get_connection() as conn:
            cursor = self._exec(
                conn,
                "SELECT * FROM indexed_bookmarks WHERE bookmark_id = ? OR url = ?",
                (bookmark_id_or_url, bookmark_id_or_url),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def needs_reindexing(self, file_path: Path) -> tuple[bool, str, float, int]:
        """Check if file has changed compared to database state.
        
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
            self._exec(
                conn,
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
            self._exec(
                conn,
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

    def record_bookmark_success(
        self,
        bookmark_id: str,
        title: str,
        url: str,
        folder: str,
        content_hash: str,
        chunk_count: int,
    ) -> None:
        """Record a successfully fetched and indexed bookmark."""
        now = time.time()
        with self._get_connection() as conn:
            self._exec(
                conn,
                """
                INSERT INTO indexed_bookmarks (
                    bookmark_id, title, url, folder, content_hash, chunk_count, fetched_at, indexed_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'indexed', NULL)
                ON CONFLICT(url) DO UPDATE SET
                    bookmark_id = excluded.bookmark_id,
                    title = excluded.title,
                    folder = excluded.folder,
                    content_hash = excluded.content_hash,
                    chunk_count = excluded.chunk_count,
                    fetched_at = excluded.fetched_at,
                    indexed_at = excluded.indexed_at,
                    status = 'indexed',
                    error_message = NULL
                """,
                (bookmark_id, title, url, folder, content_hash, chunk_count, now, now),
            )
            conn.commit()

    def record_bookmark_failure(
        self,
        bookmark_id: str,
        title: str,
        url: str,
        folder: str,
        error_message: str,
    ) -> None:
        """Record an extraction/fetch failure for a bookmark."""
        now = time.time()
        with self._get_connection() as conn:
            self._exec(
                conn,
                """
                INSERT INTO indexed_bookmarks (
                    bookmark_id, title, url, folder, content_hash, chunk_count, fetched_at, indexed_at, status, error_message
                ) VALUES (?, ?, ?, ?, '', 0, ?, ?, 'failed', ?)
                ON CONFLICT(url) DO UPDATE SET
                    bookmark_id = excluded.bookmark_id,
                    title = excluded.title,
                    folder = excluded.folder,
                    fetched_at = excluded.fetched_at,
                    indexed_at = excluded.indexed_at,
                    status = 'failed',
                    error_message = excluded.error_message
                """,
                (bookmark_id, title, url, folder, now, now, error_message),
            )
            conn.commit()

    def remove_file(self, file_path: str | Path) -> None:
        """Remove a file from the tracking database."""
        path_str = str(file_path)
        with self._get_connection() as conn:
            self._exec(conn, "DELETE FROM indexed_files WHERE file_path = ?", (path_str,))
            conn.commit()

    def remove_bookmark(self, bookmark_id_or_url: str) -> None:
        """Remove a bookmark from the tracking database."""
        with self._get_connection() as conn:
            self._exec(
                conn,
                "DELETE FROM indexed_bookmarks WHERE bookmark_id = ? OR url = ?",
                (bookmark_id_or_url, bookmark_id_or_url),
            )
            conn.commit()

    def list_all_files(self) -> list[dict[str, Any]]:
        """List all tracked files."""
        with self._get_connection() as conn:
            cursor = self._exec(conn, "SELECT * FROM indexed_files ORDER BY indexed_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def list_all_bookmarks(self) -> list[dict[str, Any]]:
        """List all tracked bookmarks."""
        with self._get_connection() as conn:
            cursor = self._exec(conn, "SELECT * FROM indexed_bookmarks ORDER BY indexed_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def list_all_knowledge_items(self) -> list[dict[str, Any]]:
        """List all knowledge items (files and bookmarks) with uniform structure."""
        items: list[dict[str, Any]] = []
        for f in self.list_all_files():
            items.append({
                "item_type": "file",
                "file_path": f["file_path"],
                "file_name": f["file_name"],
                "file_hash": f["file_hash"],
                "file_size": f["file_size"],
                "mtime": f["mtime"],
                "chunk_count": f["chunk_count"],
                "indexed_at": f["indexed_at"],
                "status": f["status"],
                "error_message": f.get("error_message"),
                "url": None,
                "folder": None,
            })
        for b in self.list_all_bookmarks():
            items.append({
                "item_type": "bookmark",
                "file_path": b["url"],
                "file_name": b["title"],
                "file_hash": b.get("content_hash") or "",
                "file_size": len(b.get("title", "")) + len(b.get("url", "")),
                "mtime": b.get("fetched_at") or b["indexed_at"],
                "chunk_count": b["chunk_count"],
                "indexed_at": b["indexed_at"],
                "status": b["status"],
                "error_message": b.get("error_message"),
                "url": b["url"],
                "folder": b["folder"],
            })
        items.sort(key=lambda x: x.get("indexed_at") or 0.0, reverse=True)
        return items

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate indexing statistics across files and bookmarks."""
        with self._get_connection() as conn:
            f_cursor = self._exec(
                conn,
                """
                SELECT 
                    COUNT(*) as total_files,
                    COALESCE(SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END), 0) as indexed_files,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed_files,
                    COALESCE(SUM(chunk_count), 0) as total_chunks,
                    COALESCE(SUM(file_size), 0) as total_bytes,
                    MAX(indexed_at) as last_indexed_at
                FROM indexed_files
                """,
            )
            f_stats = dict(f_cursor.fetchone() or {})

            b_cursor = self._exec(
                conn,
                """
                SELECT 
                    COUNT(*) as total_bookmarks,
                    COALESCE(SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END), 0) as indexed_bookmarks,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed_bookmarks,
                    COALESCE(SUM(chunk_count), 0) as bookmark_chunks,
                    MAX(indexed_at) as last_bookmark_indexed_at
                FROM indexed_bookmarks
                """,
            )
            b_stats = dict(b_cursor.fetchone() or {})

            total_chunks = (f_stats.get("total_chunks") or 0) + (b_stats.get("bookmark_chunks") or 0)
            indexed_items = (f_stats.get("indexed_files") or 0) + (b_stats.get("indexed_bookmarks") or 0)
            failed_items = (f_stats.get("failed_files") or 0) + (b_stats.get("failed_bookmarks") or 0)

            f_last = f_stats.get("last_indexed_at") or 0.0
            b_last = b_stats.get("last_bookmark_indexed_at") or 0.0
            last_indexed_at = max(f_last, b_last) if (f_last or b_last) else None

            return {
                "total_files": f_stats.get("total_files", 0),
                "indexed_files": f_stats.get("indexed_files", 0),
                "failed_files": f_stats.get("failed_files", 0),
                "total_bookmarks": b_stats.get("total_bookmarks", 0),
                "indexed_bookmarks": b_stats.get("indexed_bookmarks", 0),
                "failed_bookmarks": b_stats.get("failed_bookmarks", 0),
                "total_items": (f_stats.get("total_files", 0)) + (b_stats.get("total_bookmarks", 0)),
                "indexed_items": indexed_items,
                "failed_items": failed_items,
                "total_chunks": total_chunks,
                "total_bytes": f_stats.get("total_bytes", 0),
                "last_indexed_at": last_indexed_at,
            }

    # --- Conversation Sessions & Messages ---

    def create_session(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create and store a new conversation session."""
        sid = session_id or str(uuid.uuid4())
        now = time.time()
        dt = datetime.datetime.fromtimestamp(now)
        formatted_date = f"{dt.strftime('%b %d, %Y')} · {dt.strftime('%I:%M %p')}"
        session_title = title.strip() if title and title.strip() else formatted_date

        with self._get_connection() as conn:
            self._exec(
                conn,
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (sid, session_title, now, now),
            )
            conn.commit()

        return {
            "id": sid,
            "title": session_title,
            "created_at": now,
            "updated_at": now,
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all conversation sessions ordered by most recently updated."""
        with self._get_connection() as conn:
            cursor = self._exec(
                conn,
                """
                SELECT 
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) as message_count,
                    (
                        SELECT content FROM messages 
                        WHERE session_id = s.id AND role = 'user' 
                        ORDER BY created_at ASC LIMIT 1
                    ) as first_query_preview
                FROM sessions s
                LEFT JOIN messages m ON s.id = m.session_id
                GROUP BY s.id, s.title, s.created_at, s.updated_at
                ORDER BY s.updated_at DESC
                """,
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a session with all its chronological messages."""
        with self._get_connection() as conn:
            s_cursor = self._exec(
                conn,
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            )
            s_row = s_cursor.fetchone()
            if not s_row:
                return None

            session_data = dict(s_row)
            m_cursor = self._exec(
                conn,
                """
                SELECT id, session_id, role, content, sources, provider, model, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            )
            messages = []
            for row in m_cursor.fetchall():
                m_dict = dict(row)
                if m_dict.get("sources"):
                    try:
                        m_dict["sources"] = json.loads(m_dict["sources"])
                    except Exception:
                        pass
                else:
                    m_dict["sources"] = []
                messages.append(m_dict)

            session_data["messages"] = messages
            return session_data

    def rename_session(self, session_id: str, new_title: str) -> bool:
        """Rename an existing conversation session."""
        title_clean = new_title.strip()
        if not title_clean:
            return False

        now = time.time()
        with self._get_connection() as conn:
            cursor = self._exec(
                conn,
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title_clean, now, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session and all its messages."""
        with self._get_connection() as conn:
            self._exec(conn, "DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor = self._exec(conn, "DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: Optional[list[dict[str, Any]]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> str:
        """Append a message to a session, creating the session if it doesn't exist."""
        mid = message_id or str(uuid.uuid4())
        now = time.time()
        sources_json = json.dumps(sources) if sources is not None else None

        with self._get_connection() as conn:
            s_check = self._exec(conn, "SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not s_check:
                dt = datetime.datetime.fromtimestamp(now)
                formatted_date = f"{dt.strftime('%b %d, %Y')} · {dt.strftime('%I:%M %p')}"
                self._exec(
                    conn,
                    "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, formatted_date, now, now),
                )
            else:
                self._exec(conn, "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

            self._exec(
                conn,
                """
                INSERT INTO messages (
                    id, session_id, role, content, sources, provider, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, session_id, role, content, sources_json, provider, model, now),
            )
            conn.commit()

        return mid


def get_database(
    db_path: Optional[Path] = None,
    database_url: Optional[str] = None,
) -> Database:
    """Factory to get the configured Database instance (PostgreSQL or SQLite)."""
    return Database(db_path=db_path, database_url=database_url)
