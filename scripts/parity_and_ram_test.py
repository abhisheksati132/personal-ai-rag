#!/usr/bin/env python3
"""Embedder Parity and Memory Footprint Diagnostic Tool.

1. Tests 10 real questions (8 in-domain, 2 out-of-domain refusal).
2. Compares local Chroma+Ollama against Qdrant Cloud parity_test+FastEmbed.
3. Quantifies rank differences, score differences, and threshold crossings.
4. Measures backend RSS memory with FastEmbed loaded to evaluate Render free tier (512MB).
5. Cleans up parity_test collection afterwards.
"""

import os
import sys
import time
import uuid
import gc
from pathlib import Path
from dotenv import load_dotenv
import numpy as np

# Set UTF-8 encoding for Windows output
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

from src.embeddings import OllamaEmbedder, FastEmbedder

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


def run_parity_test():
    qdrant_url = os.getenv("QDRANT_URL") or os.getenv("BRAIN_QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY") or os.getenv("BRAIN_QDRANT_API_KEY")

    if not qdrant_url or not qdrant_key:
        print("[ERROR] QDRANT_URL and QDRANT_API_KEY must be set in .env")
        return

    temp_collection = "parity_test"
    print("=" * 70)
    print("STEP 2: EMBEDDER PARITY TEST (Ollama nomic vs FastEmbed nomic v1.5)")
    print("=" * 70)

    # 1. Load ChromaDB
    print("\n[1/5] Loading 133 local vectors from data/chroma_db...")
    chroma_client = chromadb.PersistentClient(path=str(ROOT_DIR / "data" / "chroma_db"))
    chroma_coll = chroma_client.get_collection("personal_brain")
    chroma_data = chroma_coll.get(include=["embeddings", "documents", "metadatas"])
    total_vecs = len(chroma_data["ids"])
    print(f"  Loaded {total_vecs} vectors from local ChromaDB.")

    # 2. Connect to Qdrant Cloud & Create parity_test collection
    print(f"\n[2/5] Creating temporary Qdrant collection '{temp_collection}'...")
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=30.0)
    if qdrant.collection_exists(temp_collection):
        qdrant.delete_collection(temp_collection)
    
    qdrant.create_collection(
        collection_name=temp_collection,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

    # Convert Chroma string IDs to integer or UUID for Qdrant
    id_map = {}  # int_id -> original_str_id
    points = []
    for idx, orig_id in enumerate(chroma_data["ids"]):
        id_map[idx] = orig_id
        meta = chroma_data["metadatas"][idx] or {}
        meta["_orig_id"] = orig_id
        meta["text"] = chroma_data["documents"][idx]
        points.append(
            PointStruct(
                id=idx,
                vector=[float(x) for x in chroma_data["embeddings"][idx]],
                payload=meta,
            )
        )

    print(f"\n[3/5] Upserting {len(points)} vectors to Qdrant '{temp_collection}'...")
    qdrant.upsert(collection_name=temp_collection, points=points)
    time.sleep(1.0)
    qdrant_count = qdrant.count(collection_name=temp_collection, exact=True).count
    print(f"  Verified {qdrant_count} vectors in Qdrant '{temp_collection}'.")

    # 3. Initialize embedders
    print("\n[4/5] Initializing OllamaEmbedder (local) & FastEmbedder (cloud)...")
    ollama_emb = OllamaEmbedder()
    fast_emb = FastEmbedder()

    # 4. Compare 10 Questions
    print("\n[5/5] Running 10 comparative queries (Top-8, Threshold=0.40, Drop Cutoff=0.15)...\n")
    
    comparison_results = []
    
    for item in TEST_QUESTIONS:
        qid = item["id"]
        qtext = item["query"]
        qtype = item["type"]
        
        # A. Chroma + Ollama query
        v_ollama = ollama_emb.embed_text(qtext)
        chroma_res = chroma_coll.query(
            query_embeddings=[v_ollama],
            n_results=8,
            include=["documents", "metadatas", "distances"],
        )
        # Chroma cosine distance -> cosine similarity = 1 - distance
        chroma_hits = []
        for i in range(len(chroma_res["ids"][0])):
            cid = chroma_res["ids"][0][i]
            dist = chroma_res["distances"][0][i]
            sim = 1.0 - dist
            meta = chroma_res["metadatas"][0][i]
            chroma_hits.append({
                "id": cid,
                "score": sim,
                "file": meta.get("file_name", "unknown"),
                "chunk": meta.get("chunk_index", 0),
            })

        # B. Qdrant + FastEmbed query
        v_fast = fast_emb.embed_text(qtext)
        qdrant_res = qdrant.query_points(
            collection_name=temp_collection,
            query=v_fast,
            limit=8,
            with_payload=True,
        )
        qdrant_hits = []
        for pt in qdrant_res.points:
            cid = pt.payload.get("_orig_id", str(pt.id))
            sim = float(pt.score)
            meta = pt.payload
            qdrant_hits.append({
                "id": cid,
                "score": sim,
                "file": meta.get("file_name", "unknown"),
                "chunk": meta.get("chunk_index", 0),
            })

        # Compute metrics
        top_chroma_score = chroma_hits[0]["score"] if chroma_hits else 0.0
        top_qdrant_score = qdrant_hits[0]["score"] if qdrant_hits else 0.0
        score_diff = top_qdrant_score - top_chroma_score

        # Check top-1 match agreement
        top1_match = (chroma_hits[0]["id"] == qdrant_hits[0]["id"]) if (chroma_hits and qdrant_hits) else False
        
        # Check top-8 set overlap (Jaccard similarity of top 8 retrieved chunk IDs)
        chroma_ids = set(h["id"] for h in chroma_hits)
        qdrant_ids = set(h["id"] for h in qdrant_hits)
        overlap_count = len(chroma_ids.intersection(qdrant_ids))

        # Check threshold crossings (chunks >= 0.40)
        chroma_above_040 = sum(1 for h in chroma_hits if h["score"] >= 0.40)
        qdrant_above_040 = sum(1 for h in qdrant_hits if h["score"] >= 0.40)
        threshold_discrepancy = (chroma_above_040 != qdrant_above_040)

        # Refusal check: should have top_score < 0.40
        chroma_refused = top_chroma_score < 0.40
        qdrant_refused = top_qdrant_score < 0.40

        comparison_results.append({
            "id": qid,
            "query": qtext,
            "type": qtype,
            "top_chroma_score": top_chroma_score,
            "top_qdrant_score": top_qdrant_score,
            "score_diff": score_diff,
            "top1_match": top1_match,
            "overlap_8": overlap_count,
            "chroma_above_040": chroma_above_040,
            "qdrant_above_040": qdrant_above_040,
            "threshold_discrepancy": threshold_discrepancy,
            "chroma_refused": chroma_refused,
            "qdrant_refused": qdrant_refused,
            "chroma_top_file": chroma_hits[0]["file"] if chroma_hits else "None",
            "qdrant_top_file": qdrant_hits[0]["file"] if qdrant_hits else "None",
        })

    # Print Table
    print(f"{'ID':<3} | {'Type':<8} | {'Chroma Top':<10} | {'Qdrant Top':<10} | {'Diff':<8} | {'Top-1':<6} | {'Top-8 Overlap':<13} | {'>=0.40 (Chr/Qdr)':<16} | {'Status':<10}")
    print("-" * 105)
    for r in comparison_results:
        top1_str = "YES" if r["top1_match"] else "NO"
        diff_str = f"{r['score_diff']:+.4f}"
        thresh_str = f"{r['chroma_above_040']}/8 vs {r['qdrant_above_040']}/8"
        status = "REFUSED" if r["qdrant_refused"] else "PASSED"
        print(f"{r['id']:<3} | {r['type']:<8} | {r['top_chroma_score']:<10.4f} | {r['top_qdrant_score']:<10.4f} | {diff_str:<8} | {top1_str:<6} | {r['overlap_8']}/8 match   | {thresh_str:<16} | {status:<10}")

    # 5. Cleanup parity_test
    print(f"\nDeleting temporary Qdrant collection '{temp_collection}'...")
    qdrant.delete_collection(temp_collection)
    print("  Temporary collection deleted successfully.")
    print("=" * 70 + "\n")


def measure_ram_footprint():
    import psutil
    print("=" * 70)
    print("STEP 3: BACKEND PROCESS RAM FOOTPRINT MEASUREMENT")
    print("=" * 70)

    process = psutil.Process(os.getpid())
    gc.collect()
    baseline_mb = process.memory_info().rss / (1024 * 1024)
    print(f"Baseline Python Process RSS Memory: {baseline_mb:.1f} MB")

    print("\nLoading FastAPI and FastEmbed model into process memory...")
    from src.embeddings import FastEmbedder
    fe = FastEmbedder()
    # Trigger model warm-up inference
    _ = fe.embed_text("Memory benchmark warmup query test string.")
    
    gc.collect()
    peak_mb = process.memory_info().rss / (1024 * 1024)
    model_delta_mb = peak_mb - baseline_mb

    print(f"Loaded FastEmbed Model ONNX in memory.")
    print(f"Peak Process RSS Memory: {peak_mb:.1f} MB")
    print(f"Model Memory Footprint: {model_delta_mb:.1f} MB")
    print(f"Render Free Tier Limit: 512.0 MB")
    print(f"Headroom Remaining: {512.0 - peak_mb:.1f} MB ({((512.0 - peak_mb) / 512.0) * 100:.1f}%)")

    fits_render = peak_mb < 350.0  # Safe safety buffer
    print(f"Fits within 512 MB Free Tier comfortably: {'YES' if fits_render else 'NO'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_parity_test()
    measure_ram_footprint()
