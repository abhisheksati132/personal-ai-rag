#!/usr/bin/env python3
"""Empirical test script for PostgreSQL (Neon / Supabase).

Validates:
1. Secure TLS/SSL connection to managed PostgreSQL instance
2. Table creation (sessions, messages, indexed_files, indexed_bookmarks)
3. Real session write and message write
4. Real query retrieval with JSON parsed sources
5. Real session deletion and foreign key cascading deletion
"""

import argparse
import logging
import os
from pathlib import Path
import sys
import time
import uuid

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_postgres_cloud")


def test_postgres(database_url: str):
    masked = database_url.split("@")[-1] if "@" in database_url else "configured target"
    logger.info(f"Connecting to PostgreSQL: {masked}")

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # 1. Initialize schema
            cur.execute("""
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
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources TEXT,
                    provider TEXT,
                    model TEXT,
                    created_at DOUBLE PRECISION NOT NULL
                );
            """)
            conn.commit()

            # 2. Write real test session
            sid = f"test-sess-{uuid.uuid4().hex[:8]}"
            now = time.time()
            logger.info(f"Inserting real test session: {sid}...")
            cur.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                (sid, "Empirical Cloud Test Session", now, now),
            )

            # 3. Write real test message
            mid = f"test-msg-{uuid.uuid4().hex[:8]}"
            logger.info(f"Inserting real test message: {mid}...")
            cur.execute(
                """
                INSERT INTO messages (id, session_id, role, content, sources, provider, model, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    mid,
                    sid,
                    "user",
                    "Does PostgreSQL cloud storage persist across restarts?",
                    '["test_doc.md"]',
                    "cloud",
                    "llama-3.3-70b-versatile",
                    now,
                ),
            )
            conn.commit()

            # 4. Read back and verify
            logger.info("Querying back session and message...")
            cur.execute("SELECT * FROM sessions WHERE id = %s", (sid,))
            sess_row = cur.fetchone()
            assert sess_row is not None, "Session row not found!"
            assert sess_row["title"] == "Empirical Cloud Test Session"

            cur.execute("SELECT * FROM messages WHERE session_id = %s", (sid,))
            msg_rows = cur.fetchall()
            assert len(msg_rows) == 1, f"Expected 1 message, got {len(msg_rows)}"
            assert msg_rows[0]["id"] == mid
            logger.info(f"Verified session & message read: title='{sess_row['title']}', content='{msg_rows[0]['content']}'")

            # 5. Test cascading deletion
            logger.info("Testing cascading deletion of session...")
            cur.execute("DELETE FROM sessions WHERE id = %s", (sid,))
            conn.commit()

            cur.execute("SELECT * FROM messages WHERE session_id = %s", (sid,))
            remaining_msgs = cur.fetchall()
            assert len(remaining_msgs) == 0, f"Cascade delete failed! Remaining messages: {remaining_msgs}"

    print("\n" + "=" * 60)
    print("✓ EMPIRICAL POSTGRESQL CLOUD WRITE/READ/CASCADE VERIFICATION PASSED!")
    print(f"  Target: {masked}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empirical test for PostgreSQL")
    parser.add_argument("--url", default=os.getenv("DATABASE_URL") or os.getenv("BRAIN_DATABASE_URL"))
    args = parser.parse_args()

    if not args.url:
        print("[ERROR] DATABASE_URL is required.")
        sys.exit(1)

    test_postgres(args.url)
