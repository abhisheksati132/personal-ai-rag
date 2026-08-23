import json
from pathlib import Path
import tempfile
import pytest

from src.bookmarks import BookmarkContentFetcher, BookmarkFetchResult, BookmarkItem, ChromeBookmarkParser
from src.db import Database
from src.embeddings import get_embedder
from src.ingest import IngestionPipeline
from src.prompt import PromptBuilder
from src.retrieval import RetrievalService
from src.vector_store import ChromaVectorStore


def test_chrome_bookmark_parser_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        bm_path = Path(tmpdir) / "Bookmarks"
        sample_json = {
            "roots": {
                "bookmark_bar": {
                    "name": "Bookmarks bar",
                    "type": "folder",
                    "children": [
                        {
                            "id": "1",
                            "name": "Test Site 1",
                            "type": "url",
                            "url": "https://example.com/site1",
                        },
                        {
                            "id": "2",
                            "name": "Internal Chrome Page",
                            "type": "url",
                            "url": "chrome://settings",
                        },
                        {
                            "id": "3",
                            "name": "Folder A",
                            "type": "folder",
                            "children": [
                                {
                                    "id": "4",
                                    "name": "Nested Bookmark",
                                    "type": "url",
                                    "url": "https://example.com/nested",
                                }
                            ],
                        },
                    ],
                }
            }
        }
        with open(bm_path, "w", encoding="utf-8") as f:
            json.dump(sample_json, f)

        items = ChromeBookmarkParser.parse_file(bm_path)
        assert len(items) == 2  # chrome:// scheme should be excluded
        assert items[0].title == "Test Site 1"
        assert items[0].url == "https://example.com/site1"
        assert items[0].folder == "Bookmarks bar"

        assert items[1].title == "Nested Bookmark"
        assert items[1].url == "https://example.com/nested"
        assert items[1].folder == "Bookmarks bar/Folder A"



def test_bookmark_db_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path=db_path)

        # 1. Record bookmark success
        db.record_bookmark_success(
            bookmark_id="b1",
            title="FastAPI Docs",
            url="https://fastapi.tiangolo.com",
            folder="Tech/Python",
            content_hash="abc123hash",
            chunk_count=5,
        )

        bm = db.get_bookmark("https://fastapi.tiangolo.com")
        assert bm is not None
        assert bm["title"] == "FastAPI Docs"
        assert bm["status"] == "indexed"
        assert bm["chunk_count"] == 5

        # 2. Record bookmark failure
        db.record_bookmark_failure(
            bookmark_id="b2",
            title="Dead Link",
            url="https://example.com/dead",
            folder="Tech",
            error_message="HTTP 404: Page not found",
        )

        dead_bm = db.get_bookmark("https://example.com/dead")
        assert dead_bm is not None
        assert dead_bm["status"] == "failed"
        assert "404" in dead_bm["error_message"]

        # 3. List unified knowledge items
        items = db.list_all_knowledge_items()
        assert len(items) == 2
        assert items[0]["item_type"] == "bookmark"

        # 4. Check stats
        stats = db.get_stats()
        assert stats["total_bookmarks"] == 2
        assert stats["indexed_bookmarks"] == 1
        assert stats["failed_bookmarks"] == 1
        assert stats["total_chunks"] == 5

        # 5. Remove bookmark
        db.remove_bookmark("https://fastapi.tiangolo.com")
        assert db.get_bookmark("https://fastapi.tiangolo.com") is None


def test_bookmark_prompt_formatting():
    from src.retrieval import RetrievedChunk

    prompt_builder = PromptBuilder()
    chunk = RetrievedChunk(
        text="FastAPI is a modern, fast web framework for building APIs with Python.",
        file_name="FastAPI Tutorial",
        source_path="https://fastapi.tiangolo.com/tutorial/",
        chunk_index=0,
        score=0.92,
        metadata={
            "source_type": "bookmark",
            "title": "FastAPI Tutorial",
            "url": "https://fastapi.tiangolo.com/tutorial/",
            "folder": "Tech/Python",
        },
    )

    sys_p, user_p, has_ctx = prompt_builder.build_prompt("What is FastAPI?", [chunk])
    assert has_ctx is True
    assert "Bookmark: 'FastAPI Tutorial' (https://fastapi.tiangolo.com/tutorial/)" in user_p
    assert "FastAPI is a modern, fast web framework" in user_p
