#!/usr/bin/env python3
"""Cloud Migration Tool for Personal AI Brain.

Extracts all relational state (indexed files, bookmarks, conversation sessions, messages)
from local SQLite and all vector embeddings from local ChromaDB, migrating them
directly into managed PostgreSQL (Neon / Supabase) and Qdrant Cloud.
"""

import argparse
import logging
from pathlib import Path
import sqlite3
import sys
import time
import uuid

from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings as ChromaSettings

# Load root .env
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_to_cloud")


def migrate_sqlite_to_postgres(sqlite_path: Path, postgres_url: str) -> dict:
    """Migrate all tables and records from SQLite into PostgreSQL."""
    import psycopg
    from psycopg.rows import dict_row

    logger.info(f"Connecting to local SQLite: {sqlite_path}")
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found at {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    logger.info(f"Connecting to PostgreSQL: {postgres_url.split('@')[-1] if '@' in postgres_url else 'target'}")
    pg_conn = psycopg.connect(
        postgres_url,
        row_factory=dict_row,
        prepare_threshold=None,
    )

    stats = {
        "files_migrated": 0,
        "bookmarks_migrated": 0,
        "sessions_migrated": 0,
        "messages_migrated": 0,
    }

    try:
        # 1. Initialize PostgreSQL schema
        with pg_conn.cursor() as cur:
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
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_files_indexed_at ON indexed_files(indexed_at);
                CREATE INDEX IF NOT EXISTS idx_bookmarks_indexed_at ON indexed_bookmarks(indexed_at);
            """)
            pg_conn.commit()

        # 2. Migrate indexed_files
        files = [dict(r) for r in sqlite_conn.execute("SELECT * FROM indexed_files").fetchall()]
        logger.info(f"Found {len(files)} indexed files in SQLite")
        with pg_conn.cursor() as cur:
            for f in files:
                cur.execute(
                    """
                    INSERT INTO indexed_files (
                        file_path, file_name, file_hash, file_size, mtime, chunk_count, indexed_at, status, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(file_path) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_size = EXCLUDED.file_size,
                        mtime = EXCLUDED.mtime,
                        chunk_count = EXCLUDED.chunk_count,
                        indexed_at = EXCLUDED.indexed_at,
                        status = EXCLUDED.status,
                        error_message = EXCLUDED.error_message;
                    """,
                    (
                        f["file_path"],
                        f["file_name"],
                        f["file_hash"],
                        f["file_size"],
                        f["mtime"],
                        f.get("chunk_count", 0),
                        f["indexed_at"],
                        f["status"],
                        f.get("error_message"),
                    ),
                )
            pg_conn.commit()
            stats["files_migrated"] = len(files)

        # 3. Migrate indexed_bookmarks
        bookmarks = [dict(r) for r in sqlite_conn.execute("SELECT * FROM indexed_bookmarks").fetchall()]
        logger.info(f"Found {len(bookmarks)} indexed bookmarks in SQLite")
        with pg_conn.cursor() as cur:
            for b in bookmarks:
                cur.execute(
                    """
                    INSERT INTO indexed_bookmarks (
                        bookmark_id, title, url, folder, content_hash, chunk_count, fetched_at, indexed_at, status, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(url) DO UPDATE SET
                        bookmark_id = EXCLUDED.bookmark_id,
                        title = EXCLUDED.title,
                        folder = EXCLUDED.folder,
                        content_hash = EXCLUDED.content_hash,
                        chunk_count = EXCLUDED.chunk_count,
                        fetched_at = EXCLUDED.fetched_at,
                        indexed_at = EXCLUDED.indexed_at,
                        status = EXCLUDED.status,
                        error_message = EXCLUDED.error_message;
                    """,
                    (
                        b["bookmark_id"],
                        b["title"],
                        b["url"],
                        b["folder"],
                        b.get("content_hash"),
                        b.get("chunk_count", 0),
                        b.get("fetched_at"),
                        b["indexed_at"],
                        b["status"],
                        b.get("error_message"),
                    ),
                )
            pg_conn.commit()
            stats["bookmarks_migrated"] = len(bookmarks)

        # 4. Migrate sessions
        sessions = [dict(r) for r in sqlite_conn.execute("SELECT * FROM sessions").fetchall()]
        logger.info(f"Found {len(sessions)} sessions in SQLite")
        with pg_conn.cursor() as cur:
            for s in sessions:
                cur.execute(
                    """
                    INSERT INTO sessions (id, title, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        title = EXCLUDED.title,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (s["id"], s["title"], s["created_at"], s["updated_at"]),
                )
            pg_conn.commit()
            stats["sessions_migrated"] = len(sessions)

        # 5. Migrate messages
        messages = [dict(r) for r in sqlite_conn.execute("SELECT * FROM messages").fetchall()]
        logger.info(f"Found {len(messages)} messages in SQLite")
        with pg_conn.cursor() as cur:
            for m in messages:
                cur.execute(
                    """
                    INSERT INTO messages (id, session_id, role, content, sources, provider, model, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO NOTHING;
                    """,
                    (
                        m["id"],
                        m["session_id"],
                        m["role"],
                        m["content"],
                        m.get("sources"),
                        m.get("provider"),
                        m.get("model"),
                        m["created_at"],
                    ),
                )
            pg_conn.commit()
            stats["messages_migrated"] = len(messages)

        # Verify row counts in PostgreSQL
        with pg_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as c FROM indexed_files")
            pg_files = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) as c FROM indexed_bookmarks")
            pg_bookmarks = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) as c FROM sessions")
            pg_sessions = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) as c FROM messages")
            pg_messages = cur.fetchone()["c"]

        logger.info(
            f"Postgres verification counts: {pg_files} files, {pg_bookmarks} bookmarks, {pg_sessions} sessions, {pg_messages} messages"
        )
        assert pg_files >= len(files), f"Mismatch in files: {pg_files} vs {len(files)}"
        assert pg_bookmarks >= len(bookmarks), f"Mismatch in bookmarks: {pg_bookmarks} vs {len(bookmarks)}"

    finally:
        sqlite_conn.close()
        pg_conn.close()

    return stats


def migrate_chroma_to_qdrant(
    chroma_dir: Path,
    qdrant_url: str,
    qdrant_api_key: str,
    collection_name: str = "personal_brain",
    embedder=None,
) -> dict:
    """Extract chunks from ChromaDB, re-embed using FastEmbedder, and upload to Qdrant Cloud."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams
    from src.embeddings import FastEmbedder

    embedder = embedder or FastEmbedder()

    logger.info(f"Connecting to ChromaDB at: {chroma_dir}")
    client_chroma = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )
    coll = client_chroma.get_collection("personal_brain")
    total_in_chroma = coll.count()
    logger.info(f"Total chunks in ChromaDB collection 'personal_brain': {total_in_chroma}")

    if total_in_chroma == 0:
        logger.warning("No vectors/chunks found in ChromaDB to migrate.")
        return {"vectors_migrated": 0}

    # Fetch all data documents and metadata
    data = coll.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []

    if not documents or len(documents) == 0:
        raise ValueError("ChromaDB returned empty documents! Ensure collection has valid data.")

    # Re-embed all chunks with configured cloud embedder
    logger.info(f"Re-embedding {len(documents)} chunks using {embedder.model_name}...")
    embeddings = embedder.embed_documents(documents)
    dimension = len(embeddings[0]) if embeddings else 768
    logger.info(f"Generated {len(embeddings)} vectors with dimension {dimension}")

    masked_qdrant = qdrant_url.split("//")[-1].rstrip("/") if "//" in qdrant_url else qdrant_url
    logger.info(f"Connecting to Qdrant Cloud at: {masked_qdrant}")
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=60.0)

    # Re-create collection or ensure exists
    if not qdrant.collection_exists(collection_name):
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant Cloud collection '{collection_name}' (dim={dimension}, Cosine)")
    else:
        logger.info(f"Qdrant Cloud collection '{collection_name}' already exists.")

    # Ensure 'source' keyword payload index exists
    try:
        qdrant.create_payload_index(
            collection_name=collection_name,
            field_name="source",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info(f"Ensured 'source' keyword payload index on collection '{collection_name}'")
    except Exception as e:
        err_msg = str(e).lower()
        if "already exists" in err_msg or "already indexed" in err_msg:
            pass
        else:
            logger.warning(f"Failed to create 'source' payload index: {e}")

    # Prepare points with deterministic, idempotent UUIDs
    points = []
    for chunk_id, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
        point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))
        payload = {
            "id": chunk_id,
            "text": doc or "",
            **(meta or {}),
        }
        points.append(
            PointStruct(
                id=point_uuid,
                vector=[float(x) for x in emb],
                payload=payload,
            )
        )

    # Upsert in batches of 50
    batch_size = 50
    total_upserted = 0
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        qdrant.upsert(collection_name=collection_name, points=batch)
        total_upserted += len(batch)
        logger.info(f"Progress: upserted {total_upserted}/{len(points)} points into Qdrant Cloud...")

    # Verification count
    time.sleep(1.0)
    qdrant_count = qdrant.count(collection_name=collection_name, exact=True).count
    logger.info(f"Verified Qdrant Cloud point count: {qdrant_count}")

    # Run live test query with embedder
    test_query_vec = embedder.embed_text(documents[0])
    test_res = qdrant.query_points(
        collection_name=collection_name,
        query=test_query_vec,
        limit=2,
        with_payload=True,
    )
    assert len(test_res.points) > 0, "Test search returned 0 results from Qdrant Cloud!"
    top_score = float(test_res.points[0].score)
    logger.info(f"Live test vector search verification: top match score = {top_score:.4f} (expected ~1.0000)")
    assert top_score > 0.95, f"Unexpectedly low top match score: {top_score}"

    return {
        "vectors_migrated": total_upserted,
        "qdrant_total": qdrant_count,
        "top_search_score": top_score,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate Personal AI Brain to PostgreSQL and Qdrant Cloud")
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection string (Neon / Supabase)")
    parser.add_argument("--qdrant-url", default=None, help="Qdrant Cloud cluster URL")
    parser.add_argument("--qdrant-api-key", default=None, help="Qdrant Cloud API key")
    parser.add_argument("--qdrant-collection", default="personal_brain", help="Qdrant collection name")
    parser.add_argument("--sqlite-path", default=str(ROOT_DIR / "data" / "brain.db"), help="Local SQLite path")
    parser.add_argument("--chroma-dir", default=str(ROOT_DIR / "data" / "chroma_db"), help="Local ChromaDB path")
    parser.add_argument("--dry-run", action="store_true", help="Simulate migration: print counts and target hostnames without writing data")
    args = parser.parse_args()

    import os
    from src.config import settings
    from src.embeddings import FastEmbedder

    db_url = args.database_url or os.getenv("DATABASE_URL") or os.getenv("BRAIN_DATABASE_URL")
    qdrant_url = args.qdrant_url or os.getenv("QDRANT_URL") or os.getenv("BRAIN_QDRANT_URL")
    qdrant_key = args.qdrant_api_key or os.getenv("QDRANT_API_KEY") or os.getenv("BRAIN_QDRANT_API_KEY")

    if not db_url:
        print("\n[ERROR] DATABASE_URL is required (pass --database-url or set in .env)")
        sys.exit(1)
    if not qdrant_url or not qdrant_key:
        print("\n[ERROR] QDRANT_URL and QDRANT_API_KEY are required (pass flags or set in .env)")
        sys.exit(1)

    target_pg_host = db_url.split("@")[-1] if "@" in db_url else "configured postgres"
    target_qdrant_host = qdrant_url.split("//")[-1].rstrip("/") if "//" in qdrant_url else qdrant_url
    embedder = FastEmbedder()

    if args.dry_run:
        print("\n" + "=" * 65)
        print("PERSONAL AI BRAIN: CLOUD MIGRATION (DRY-RUN)")
        print("=" * 65)
        
        # Read local SQLite counts
        sqlite_p = Path(args.sqlite_path)
        if not sqlite_p.exists():
            print(f"[ERROR] SQLite database not found at {sqlite_p}")
            sys.exit(1)
            
        sq_conn = sqlite3.connect(sqlite_p)
        cur = sq_conn.cursor()
        file_count = cur.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
        bm_count = cur.execute("SELECT COUNT(*) FROM indexed_bookmarks").fetchone()[0]
        sess_count = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        msg_count = cur.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        sq_conn.close()

        # Read local Chroma chunks count
        client_chroma = chromadb.PersistentClient(path=str(args.chroma_dir))
        coll = client_chroma.get_collection("personal_brain")
        chunk_count = coll.count()

        print("\nTarget Infrastructure:")
        print(f"  • PostgreSQL Target:    {target_pg_host}")
        print(f"  • Qdrant Cloud Target:  {target_qdrant_host} (collection: '{args.qdrant_collection}')")

        print("\nEmbedder Configuration (Stored in Config):")
        print(f"  • Model:                {embedder.model_name}")
        print(f"  • Vector Dimension:     768")
        print(f"  • Document Prefix:      {repr(embedder.doc_prefix)}")
        print(f"  • Query Prefix:         {repr(embedder.query_prefix)}")

        print("\nData Entities Scheduled for Migration:")
        print(f"  • Indexed Files:        {file_count}")
        print(f"  • Indexed Bookmarks:    {bm_count}")
        print(f"  • Sessions:             {sess_count}")
        print(f"  • Messages:             {msg_count}")
        print(f"  • Total Chunks:         {chunk_count}")

        print("\n" + "-" * 65)
        print("[DRY-RUN] No data was written to PostgreSQL or Qdrant Cloud.")
        print("=" * 65 + "\n")
        return

    print("\n" + "=" * 60)
    print("PERSONAL AI BRAIN: CLOUD MIGRATION PIPELINE")
    print("=" * 60)

    # 1. Migrate SQLite -> PostgreSQL
    print("\n--- Phase 1: Migrating Relational State (SQLite -> PostgreSQL) ---")
    pg_stats = migrate_sqlite_to_postgres(Path(args.sqlite_path), db_url)
    print(f"✓ Migrated {pg_stats['files_migrated']} indexed files")
    print(f"✓ Migrated {pg_stats['bookmarks_migrated']} indexed bookmarks")
    print(f"✓ Migrated {pg_stats['sessions_migrated']} conversation sessions")
    print(f"✓ Migrated {pg_stats['messages_migrated']} conversation messages")

    # 2. Migrate ChromaDB -> Qdrant Cloud (Re-embedding with FastEmbedder)
    print("\n--- Phase 2: Migrating Vector Embeddings (Re-embedding -> Qdrant Cloud) ---")
    vec_stats = migrate_chroma_to_qdrant(
        Path(args.chroma_dir),
        qdrant_url,
        qdrant_key,
        args.qdrant_collection,
        embedder=embedder,
    )
    print(f"✓ Re-embedded & migrated {vec_stats['vectors_migrated']} embedding vectors")
    print(f"✓ Total points in Qdrant Cloud: {vec_stats['qdrant_total']}")
    print(f"✓ Live query test passed with similarity score {vec_stats['top_search_score']:.4f}")

    print("\n" + "=" * 60)
    print("✓ CLOUD MIGRATION COMPLETE AND VERIFIED!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
