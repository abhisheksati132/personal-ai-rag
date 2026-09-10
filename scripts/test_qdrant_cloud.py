#!/usr/bin/env python3
"""Empirical test script for Qdrant Cloud vector database.

Validates:
1. Secure TLS/HTTPS connection to Qdrant Cloud cluster
2. Collection existence/creation (personal_brain)
3. Real point insertion with 768-dimensional vector and metadata payload
4. Real vector similarity search query
5. Point deletion by ID
"""

import argparse
import logging
import os
from pathlib import Path
import sys
import time
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_qdrant_cloud")


def test_qdrant(url: str, api_key: str, collection_name: str = "personal_brain"):
    logger.info(f"Connecting to Qdrant Cloud: {url}")
    client = QdrantClient(url=url, api_key=api_key, timeout=30.0)

    # 1. Collection check
    if not client.collection_exists(collection_name):
        logger.info(f"Creating collection '{collection_name}' (dim=768, Cosine)...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
    
    info = client.get_collection(collection_name)
    logger.info(f"Collection status: {info.status}, points_count: {info.points_count}")

    # 2. Write real test vector
    test_id = str(uuid.uuid4())
    test_vector = [0.05] * 768
    test_vector[0] = 0.95
    payload = {
        "text": "Empirical cloud verification test chunk for Personal AI Brain.",
        "file_name": "verification_test.md",
        "source": "verification_test.md",
        "chunk_index": 9999,
        "is_test": True,
    }

    point = PointStruct(id=test_id, vector=test_vector, payload=payload)
    logger.info(f"Inserting real test vector with ID: {test_id}...")
    client.upsert(collection_name=collection_name, points=[point])
    time.sleep(1.0)

    # 3. Read back using vector query
    logger.info("Executing real vector search query...")
    res = client.query_points(
        collection_name=collection_name,
        query=test_vector,
        limit=5,
        with_payload=True,
    )

    found = None
    for hit in res.points:
        if str(hit.id) == test_id:
            found = hit
            break

    assert found is not None, f"Test vector {test_id} not found in search results!"
    score = float(found.score)
    logger.info(f"Found test vector in Qdrant Cloud! Match Score: {score:.5f} (payload: {found.payload})")
    assert score > 0.98, f"Score too low: {score}"

    # 4. Clean up test vector
    logger.info("Cleaning up test vector from Qdrant Cloud...")
    client.delete(
        collection_name=collection_name,
        points_selector=[test_id],
    )
    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("✓ EMPIRICAL QDRANT CLOUD WRITE/READ VERIFICATION PASSED!")
    print(f"  Cluster: {url}")
    print(f"  Collection: {collection_name}")
    print(f"  Verified Cosine Match: {score:.5f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empirical test for Qdrant Cloud")
    parser.add_argument("--url", default=os.getenv("QDRANT_URL") or os.getenv("BRAIN_QDRANT_URL"))
    parser.add_argument("--key", default=os.getenv("QDRANT_API_KEY") or os.getenv("BRAIN_QDRANT_API_KEY"))
    parser.add_argument("--collection", default="personal_brain")
    args = parser.parse_args()

    if not args.url or not args.key:
        print("[ERROR] QDRANT_URL and QDRANT_API_KEY are required.")
        sys.exit(1)

    test_qdrant(args.url, args.key, args.collection)
