#!/usr/bin/env python3
"""Measure Peak Process Memory (RSS) for Personal AI Brain Backend with FastEmbed."""

import os
import sys
import gc
import time
from pathlib import Path
from dotenv import load_dotenv
import psutil

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

def measure():
    process = psutil.Process(os.getpid())
    
    # Baseline
    gc.collect()
    baseline_mb = process.memory_info().rss / (1024 * 1024)
    print("=" * 60)
    print("STEP 3: BACKEND PROCESS RAM MEASUREMENT (FastEmbed)")
    print("=" * 60)
    print(f"1. Python Process Baseline RSS:       {baseline_mb:.2f} MB")

    # Import and instantiate FastEmbed
    print("2. Importing FastEmbed & loading ONNX model into memory...")
    from src.embeddings import FastEmbedder
    fe = FastEmbedder()
    # Trigger model warm-up inference (both single text and batch)
    _ = fe.embed_text("Benchmark test query for memory usage estimation.")
    _ = fe.embed_documents(["Document chunk 1 text", "Document chunk 2 text", "Document chunk 3 text"])
    
    gc.collect()
    post_embed_mb = process.memory_info().rss / (1024 * 1024)
    embed_delta = post_embed_mb - baseline_mb
    print(f"   Memory with FastEmbed Loaded:      {post_embed_mb:.2f} MB (+{embed_delta:.2f} MB model)")

    # Load FastAPI App components
    print("3. Loading FastAPI application stack...")
    import fastapi
    import uvicorn
    import pydantic
    import qdrant_client
    import psycopg
    
    gc.collect()
    peak_rss_mb = process.memory_info().rss / (1024 * 1024)
    print(f"4. Total Peak Backend RSS Memory:      {peak_rss_mb:.2f} MB")
    print("-" * 60)
    print(f"   Render Free Tier Limit:            512.00 MB")
    print(f"   Free Tier Headroom Remaining:      {512.00 - peak_rss_mb:.2f} MB ({(512.00 - peak_rss_mb)/512.00 * 100:.1f}%)")
    print(f"   Safe Operating Buffer (< 350 MB):  {'YES (SAFE)' if peak_rss_mb < 350 else 'TIGHT'}")
    print("=" * 60)

if __name__ == "__main__":
    measure()
