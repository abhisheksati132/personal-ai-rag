import os
import tempfile
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.db import Database
from src.api import app, _db, _retrieval_service, _prompt_builder, _llm_local
from src.retrieval import RetrievedChunk


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_brain.db"
        db = Database(db_path=db_path)
        yield db


def test_session_db_crud(temp_db):
    # 1. Create session
    sess = temp_db.create_session(title="My Research Session")
    assert sess["id"] is not None
    assert sess["title"] == "My Research Session"
    sid = sess["id"]

    # 2. Add messages
    m1 = temp_db.add_message(
        session_id=sid,
        role="user",
        content="What is TCP handshake?",
    )
    assert m1 is not None

    m2 = temp_db.add_message(
        session_id=sid,
        role="assistant",
        content="TCP uses SYN, SYN-ACK, ACK.",
        sources=[{"file": "networks.pdf", "chunk_index": 0, "score": 0.88}],
        provider="local",
        model="llama3.2",
    )
    assert m2 is not None

    # 3. Retrieve session
    detail = temp_db.get_session(sid)
    assert detail is not None
    assert detail["id"] == sid
    assert detail["title"] == "My Research Session"
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "What is TCP handshake?"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["content"] == "TCP uses SYN, SYN-ACK, ACK."
    assert len(detail["messages"][1]["sources"]) == 1
    assert detail["messages"][1]["sources"][0]["file"] == "networks.pdf"

    # 4. List sessions
    sessions_list = temp_db.list_sessions()
    assert len(sessions_list) == 1
    assert sessions_list[0]["id"] == sid
    assert sessions_list[0]["message_count"] == 2
    assert sessions_list[0]["first_query_preview"] == "What is TCP handshake?"

    # 5. Rename session
    renamed = temp_db.rename_session(sid, "Renamed Networks Session")
    assert renamed is True
    updated = temp_db.get_session(sid)
    assert updated["title"] == "Renamed Networks Session"

    # 6. Delete session and verify cascade
    deleted = temp_db.delete_session(sid)
    assert deleted is True
    assert temp_db.get_session(sid) is None
    assert len(temp_db.list_sessions()) == 0


def test_api_session_endpoints(monkeypatch, temp_db):
    monkeypatch.setattr("src.api._db", temp_db)
    client = TestClient(app)

    # 1. POST /sessions
    res = client.post("/sessions", json={"title": "Custom Session 1"})
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Custom Session 1"
    sid = data["id"]

    # 2. GET /sessions
    res = client.get("/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == sid

    # 3. GET /sessions/{id}
    res = client.get(f"/sessions/{sid}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == sid
    assert len(detail["messages"]) == 0

    # 4. PATCH /sessions/{id}
    res = client.patch(f"/sessions/{sid}", json={"title": "Updated Title"})
    assert res.status_code == 200
    assert res.json()["title"] == "Updated Title"

    # 5. DELETE /sessions/{id}
    res = client.delete(f"/sessions/{sid}")
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # 6. 404 for deleted session
    res = client.get(f"/sessions/{sid}")
    assert res.status_code == 404


def test_query_with_and_without_session_id(monkeypatch, temp_db):
    monkeypatch.setattr("src.api._db", temp_db)
    client = TestClient(app)

    # Mock retrieval to return fixed chunk
    mock_chunk = RetrievedChunk(
        text="A mesh network connects every node directly to every other node.",
        file_name="topology.pdf",
        source_path="data/documents/topology.pdf",
        chunk_index=0,
        score=0.92,
        metadata={"title": "Topology Guide", "source_type": "file"},
    )

    monkeypatch.setattr(_retrieval_service, "retrieve", lambda query, top_k=None, min_score=None: [mock_chunk])
    monkeypatch.setattr(_llm_local, "generate", lambda prompt, system_prompt=None: "Mesh networks connect all nodes.")

    # 1. Query with session_id
    sess = temp_db.create_session(title="Session With Query")
    sid = sess["id"]

    res = client.post("/query", json={
        "question": "How does mesh topology work?",
        "session_id": sid,
        "provider": "local",
    })
    assert res.status_code == 200
    resp_data = res.json()
    assert resp_data["session_id"] == sid
    assert "Mesh networks connect all nodes" in resp_data["answer"]

    # Verify messages saved to SQLite
    detail = temp_db.get_session(sid)
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "How does mesh topology work?"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["content"] == "Mesh networks connect all nodes."
    assert len(detail["messages"][1]["sources"]) == 1

    # 2. Query WITHOUT session_id (stateless query)
    res_stateless = client.post("/query", json={
        "question": "What is star topology?",
        "provider": "local",
    })
    assert res_stateless.status_code == 200
    stateless_data = res_stateless.json()
    assert stateless_data.get("session_id") is None

    # Verify session message count did not change
    detail_after = temp_db.get_session(sid)
    assert len(detail_after["messages"]) == 2
