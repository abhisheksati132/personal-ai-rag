#!/usr/bin/env python3
"""Comprehensive Quantized Model (-Q) Embedder Parity Evaluation."""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import numpy as np

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

import chromadb
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from fastembed import TextEmbedding
from src.embeddings import OllamaEmbedder

TEST_QUESTIONS = [
    # 8 In-domain questions
    {"id": 1, "query": "Explain how a modern compiler processes the statement through all compilation phases in CAT-1.", "type": "in-domain"},
    {"id": 2, "query": "What tokens are identified during lexical analysis of the C-like statement in CAT-1?", "type": "in-domain"},
    {"id": 3, "query": "How many ports at end devices and total cables are needed for 5 devices in a Full Mesh Topology?", "type": "in-domain"},
    {"id": 4, "query": "What is the single-link failure impact and fault tolerance for 5 devices in a Star Topology?", "type": "in-domain"},
    {"id": 5, "query": "Why is a bus topology single backbone cable considered a major single point of failure?", "type": "in-domain"},
    {"id": 6, "query": "What are the columns and data types in the ORDERS table schema in DBMS Lab Manual 3?", "type": "in-domain"},
    {"id": 7, "query": "What are the core design principles and index type used in ChromaDB architecture?", "type": "in-domain"},
    {"id": 8, "query": "What is the formula for Scaled Dot-Product Attention in the Transformer architecture?", "type": "in-domain"},
    # 2 Out-of-domain refusal questions
    {"id": 9, "query": "What is the secret recipe for baking homemade chocolate chip cookies?", "type": "refusal"},
    {"id": 10, "query": "Who won the FIFA World Cup in 2022 in Qatar?", "type": "refusal"},
]


def run_quantized_parity_analysis():
    qdrant_url = os.getenv("QDRANT_URL") or os.getenv("BRAIN_QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY") or os.getenv("BRAIN_QDRANT_API_KEY")
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=30.0)

    # 1. Load ChromaDB baseline data
    chroma_client = chromadb.PersistentClient(path=str(ROOT_DIR / "data" / "chroma_db"))
    chroma_coll = chroma_client.get_collection("personal_brain")
    chroma_data = chroma_coll.get(include=["embeddings", "documents", "metadatas"])

    ollama_emb = OllamaEmbedder()
    q_model = TextEmbedding(model_name="nomic-ai/nomic-embed-text-v1.5-Q")

    print("\n" + "=" * 80)
    print("TEST 2A: Ollama Doc Vectors + nomic-embed-text-v1.5-Q Query Embeddings")
    print("=" * 80)

    temp_coll_2a = "parity_test_2a"
    if qdrant.collection_exists(temp_coll_2a):
        qdrant.delete_collection(temp_coll_2a)
    qdrant.create_collection(collection_name=temp_coll_2a, vectors_config=VectorParams(size=768, distance=Distance.COSINE))

    points_2a = []
    for idx, orig_id in enumerate(chroma_data["ids"]):
        meta = chroma_data["metadatas"][idx] or {}
        meta["_orig_id"] = orig_id
        meta["text"] = chroma_data["documents"][idx]
        points_2a.append(
            PointStruct(
                id=idx,
                vector=[float(x) for x in chroma_data["embeddings"][idx]],  # Ollama FP32 vectors
                payload=meta,
            )
        )
    qdrant.upsert(collection_name=temp_coll_2a, points=points_2a)
    time.sleep(1.0)

    results_2a = []
    max_delta_2a = 0.0
    all_top8_identical_2a = True

    for item in TEST_QUESTIONS:
        qid = item["id"]
        qtext = item["query"]
        qtype = item["type"]

        # Baseline: Chroma + Ollama
        v_ollama = ollama_emb.embed_text(qtext)
        c_res = chroma_coll.query(query_embeddings=[v_ollama], n_results=8, include=["metadatas", "distances"])
        c_hits = []
        for i in range(len(c_res["ids"][0])):
            cid = c_res["ids"][0][i]
            sim = 1.0 - c_res["distances"][0][i]
            c_hits.append({"id": cid, "score": sim, "file": c_res["metadatas"][0][i].get("file_name", "")})

        # Test 2A: Qdrant + -Q Query
        v_q = [float(x) for x in list(q_model.embed([qtext]))[0]]
        q_res = qdrant.query_points(collection_name=temp_coll_2a, query=v_q, limit=8, with_payload=True)
        q_hits = []
        for pt in q_res.points:
            cid = pt.payload.get("_orig_id", str(pt.id))
            q_hits.append({"id": cid, "score": float(pt.score), "file": pt.payload.get("file_name", "")})

        # Compare metrics
        top_c_score = c_hits[0]["score"]
        top_q_score = q_hits[0]["score"]
        delta = abs(top_q_score - top_c_score)
        if delta > max_delta_2a:
            max_delta_2a = delta

        top1_match = (c_hits[0]["id"] == q_hits[0]["id"])
        c_ids = [h["id"] for h in c_hits]
        q_ids = [h["id"] for h in q_hits]
        overlap_8 = len(set(c_ids).intersection(set(q_ids)))
        if overlap_8 < 8:
            all_top8_identical_2a = False
        exact_rank_match = (c_ids == q_ids)

        # 0.40 threshold count
        c_above_040 = sum(1 for h in c_hits if h["score"] >= 0.40)
        q_above_040 = sum(1 for h in q_hits if h["score"] >= 0.40)

        # 0.15 relative cutoff count
        c_cutoff = top_c_score - 0.15
        q_cutoff = top_q_score - 0.15
        c_after_cutoff = sum(1 for h in c_hits if h["score"] >= c_cutoff and h["score"] >= 0.40)
        q_after_cutoff = sum(1 for h in q_hits if h["score"] >= q_cutoff and h["score"] >= 0.40)

        results_2a.append({
            "id": qid,
            "type": qtype,
            "top_c": top_c_score,
            "top_q": top_q_score,
            "delta": top_q_score - top_c_score,
            "top1_match": top1_match,
            "overlap_8": overlap_8,
            "exact_rank": exact_rank_match,
            "c_040": c_above_040,
            "q_040": q_above_040,
            "c_cut": c_after_cutoff,
            "q_cut": q_after_cutoff,
            "refused": top_q_score < 0.40,
        })

    # Print Table 2A
    print(f"{'ID':<3} | {'Type':<8} | {'Chroma Top':<10} | {'Qdrant Top':<10} | {'Delta':<8} | {'Top-1':<6} | {'Overlap':<8} | {'Rank Order':<10} | {'>=0.40 (C/Q)':<14} | {'Post-Cutoff':<12}")
    print("-" * 105)
    for r in results_2a:
        top1_s = "YES" if r["top1_match"] else "NO"
        rank_s = "IDENTICAL" if r["exact_rank"] else "SHIFTED"
        thresh_s = f"{r['c_040']} vs {r['q_040']}"
        cut_s = f"{r['c_cut']} vs {r['q_cut']}"
        print(f"{r['id']:<3} | {r['type']:<8} | {r['top_c']:<10.4f} | {r['top_q']:<10.4f} | {r['delta']:<+8.4f} | {top1_s:<6} | {r['overlap_8']}/8     | {rank_s:<10} | {thresh_s:<14} | {cut_s:<12}")

    qdrant.delete_collection(temp_coll_2a)
    print(f"\n2A Summary: Max Top-Score Delta = {max_delta_2a:.4f} (<= 0.02 is {max_delta_2a <= 0.02}), All Top-8 Identical = {all_top8_identical_2a}")

    # =========================================================================
    # TEST 2B: Full Quantized Pipeline (-Q for both Docs and Queries)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 2B: Re-embedding all 133 chunks with -Q model (Doc Embeddings + Query Embeddings)")
    print("=" * 80)

    temp_coll_2b = "parity_test_2b"
    if qdrant.collection_exists(temp_coll_2b):
        qdrant.delete_collection(temp_coll_2b)
    qdrant.create_collection(collection_name=temp_coll_2b, vectors_config=VectorParams(size=768, distance=Distance.COSINE))

    print("Re-embedding 133 local chunks using nomic-embed-text-v1.5-Q...")
    doc_texts = chroma_data["documents"]
    q_doc_vectors = list(q_model.embed(doc_texts))

    points_2b = []
    for idx, orig_id in enumerate(chroma_data["ids"]):
        meta = chroma_data["metadatas"][idx] or {}
        meta["_orig_id"] = orig_id
        meta["text"] = doc_texts[idx]
        points_2b.append(
            PointStruct(
                id=idx,
                vector=[float(x) for x in q_doc_vectors[idx]],  # -Q vectors
                payload=meta,
            )
        )
    qdrant.upsert(collection_name=temp_coll_2b, points=points_2b)
    time.sleep(1.0)
    print(f"Upserted 133 re-embedded points to '{temp_coll_2b}'.")

    results_2b = []
    for item in TEST_QUESTIONS:
        qid = item["id"]
        qtext = item["query"]
        qtype = item["type"]

        # Baseline: Chroma + Ollama
        v_ollama = ollama_emb.embed_text(qtext)
        c_res = chroma_coll.query(query_embeddings=[v_ollama], n_results=8, include=["metadatas", "distances"])
        c_hits = []
        for i in range(len(c_res["ids"][0])):
            cid = c_res["ids"][0][i]
            sim = 1.0 - c_res["distances"][0][i]
            c_hits.append({"id": cid, "score": sim, "file": c_res["metadatas"][0][i].get("file_name", "")})

        # Test 2B: Qdrant (-Q docs) + -Q Query
        v_q = [float(x) for x in list(q_model.embed([qtext]))[0]]
        q_res = qdrant.query_points(collection_name=temp_coll_2b, query=v_q, limit=8, with_payload=True)
        q_hits = []
        for pt in q_res.points:
            cid = pt.payload.get("_orig_id", str(pt.id))
            q_hits.append({"id": cid, "score": float(pt.score), "file": pt.payload.get("file_name", "")})

        top_c_score = c_hits[0]["score"]
        top_q_score = q_hits[0]["score"]
        top1_match = (c_hits[0]["id"] == q_hits[0]["id"])
        c_ids = [h["id"] for h in c_hits]
        q_ids = [h["id"] for h in q_hits]
        overlap_8 = len(set(c_ids).intersection(set(q_ids)))
        exact_rank_match = (c_ids == q_ids)

        c_above_040 = sum(1 for h in c_hits if h["score"] >= 0.40)
        q_above_040 = sum(1 for h in q_hits if h["score"] >= 0.40)

        c_cutoff = top_c_score - 0.15
        q_cutoff = top_q_score - 0.15
        c_after_cutoff = sum(1 for h in c_hits if h["score"] >= c_cutoff and h["score"] >= 0.40)
        q_after_cutoff = sum(1 for h in q_hits if h["score"] >= q_cutoff and h["score"] >= 0.40)

        results_2b.append({
            "id": qid,
            "type": qtype,
            "top_c": top_c_score,
            "top_q": top_q_score,
            "delta": top_q_score - top_c_score,
            "top1_match": top1_match,
            "overlap_8": overlap_8,
            "exact_rank": exact_rank_match,
            "c_040": c_above_040,
            "q_040": q_above_040,
            "c_cut": c_after_cutoff,
            "q_cut": q_after_cutoff,
            "refused": top_q_score < 0.40,
        })

    # Print Table 2B
    print(f"{'ID':<3} | {'Type':<8} | {'Chroma Top':<10} | {'-Q Full Top':<11} | {'Delta':<8} | {'Top-1':<6} | {'Overlap':<8} | {'Rank Order':<10} | {'>=0.40 (C/Q)':<14} | {'Post-Cutoff':<12}")
    print("-" * 105)
    for r in results_2b:
        top1_s = "YES" if r["top1_match"] else "NO"
        rank_s = "IDENTICAL" if r["exact_rank"] else "SHIFTED"
        thresh_s = f"{r['c_040']} vs {r['q_040']}"
        cut_s = f"{r['c_cut']} vs {r['q_cut']}"
        print(f"{r['id']:<3} | {r['type']:<8} | {r['top_c']:<10.4f} | {r['top_q']:<11.4f} | {r['delta']:<+8.4f} | {top1_s:<6} | {r['overlap_8']}/8     | {rank_s:<10} | {thresh_s:<14} | {cut_s:<12}")

    qdrant.delete_collection(temp_coll_2b)
    print("\nTemporary collections cleaned up successfully.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_quantized_parity_analysis()
