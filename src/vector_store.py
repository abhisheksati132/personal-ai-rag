from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.chunker import Chunk
from src.config import settings

logger = logging.getLogger(__name__)


def sanitize_metadata(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Ensure all metadata values are primitive types allowed by vector databases."""
    sanitized = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            sanitized[k] = v
        elif isinstance(v, Path):
            sanitized[k] = str(v)
        elif v is None:
            sanitized[k] = ""
        else:
            sanitized[k] = str(v)
    return sanitized


class BaseVectorStore(ABC):
    """Abstract base interface for vector databases (ChromaDB, Qdrant Cloud)."""

    @abstractmethod
    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        pass

    @abstractmethod
    def delete_by_source(self, source_path: str | Path) -> None:
        pass

    @abstractmethod
    def query_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def count(self) -> int:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB persistent vector store manager."""

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        collection_name: Optional[str] = None,
    ):
        self.persist_dir = Path(persist_dir or settings.CHROMA_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or settings.COLLECTION_NAME

    def _get_client(self) -> chromadb.PersistentClient:
        return chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
        )

    @property
    def collection(self):
        """Get fresh collection handle from client."""
        return self._get_client().get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """Add or update document chunks with their corresponding embedding vectors."""
        if not chunks:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch between chunks count ({len(chunks)}) and embeddings count ({len(embeddings)})")

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [
            sanitize_metadata({
                **chunk.metadata,
                "chunk_index": chunk.chunk_index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            })
            for chunk in chunks
        ]

        batch_size = 100
        total_added = 0
        for i in range(0, len(ids), batch_size):
            end_idx = i + batch_size
            self.collection.upsert(
                ids=ids[i:end_idx],
                embeddings=embeddings[i:end_idx],
                documents=documents[i:end_idx],
                metadatas=metadatas[i:end_idx],
            )
            total_added += len(ids[i:end_idx])

        return total_added

    def delete_by_source(self, source_path: str | Path) -> None:
        """Delete all chunks originating from a specific file."""
        source_str = str(source_path)
        try:
            self.collection.delete(where={"source": source_str})
            logger.info(f"Deleted Chroma chunks for source: {source_str}")
        except Exception as e:
            logger.warning(f"Failed or no chunks found to delete for {source_str}: {e}")

    def query_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Query top-k most similar chunks by query vector."""
        if self.count() == 0:
            return []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        formatted_results = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else []
            distances = results["distances"][0] if results.get("distances") else []

            for chunk_id, doc, meta, dist in zip(ids, docs, metas, distances):
                # Cosine similarity score = 1 - cosine distance
                score = round(1.0 - float(dist), 4) if dist is not None else 1.0
                formatted_results.append({
                    "id": chunk_id,
                    "text": doc or "",
                    "metadata": meta if meta is not None else {},
                    "distance": dist,
                    "score": score,
                })

        return formatted_results

    def count(self) -> int:
        """Total number of vectors in the collection."""
        return self.collection.count()

    def clear(self) -> None:
        """Reset the collection."""
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )


class QdrantVectorStore(BaseVectorStore):
    """Qdrant Cloud vector store manager."""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        dimension: int = 768,
    ):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

        self.url = url if url is not None else settings.QDRANT_URL
        self.api_key = api_key if api_key is not None else settings.QDRANT_API_KEY
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.dimension = dimension

        if self.url and self.url.strip():
            self.client = QdrantClient(url=self.url, api_key=self.api_key, timeout=30.0)
        else:
            self.client = QdrantClient(":memory:")

        # Ensure collection exists
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {self.collection_name} (dim={self.dimension}, distance=Cosine)")

        # Ensure 'source' keyword payload index exists for filtering / delete_by_source
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as e:
            err_msg = str(e).lower()
            if "already exists" in err_msg or "already indexed" in err_msg:
                pass
            else:
                logger.warning(f"Failed to create 'source' payload index on Qdrant collection {self.collection_name}: {e}")

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """Add or update document chunks with their corresponding embedding vectors."""
        if not chunks:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch between chunks count ({len(chunks)}) and embeddings count ({len(embeddings)})")

        from qdrant_client.models import PointStruct

        points = []
        for chunk, emb in zip(chunks, embeddings):
            # Deterministic UUIDv5 from chunk_id for idempotency
            point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))
            payload = sanitize_metadata({
                **chunk.metadata,
                "id": chunk.chunk_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            })
            points.append(
                PointStruct(
                    id=point_uuid,
                    vector=emb,
                    payload=payload,
                )
            )

        batch_size = 100
        total_added = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
            total_added += len(batch)

        logger.info(f"Upserted {total_added} points into Qdrant collection {self.collection_name}")
        return total_added

    def delete_by_source(self, source_path: str | Path) -> None:
        """Delete all chunks originating from a specific file."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        source_str = str(source_path)
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="source", match=MatchValue(value=source_str))
                    ]
                ),
            )
            logger.info(f"Deleted Qdrant points for source: {source_str}")
        except Exception as e:
            logger.warning(f"Failed to delete Qdrant points for {source_str}: {e}")

    def query_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Query top-k most similar chunks by query vector."""
        if self.count() == 0:
            return []

        q_filter = None
        if where:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            must_conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in where.items()
            ]
            q_filter = Filter(must=must_conditions)

        res = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k,
            query_filter=q_filter,
            with_payload=True,
        )

        formatted_results = []
        for hit in res.points:
            payload = hit.payload or {}
            # In Qdrant COSINE distance, score is cosine similarity directly (1.0 = identical, 0.0 = orthogonal)
            score = round(float(hit.score), 4)
            distance = round(1.0 - score, 4)
            formatted_results.append({
                "id": payload.get("id") or str(hit.id),
                "text": payload.get("text", "") or "",
                "metadata": payload,
                "distance": distance,
                "score": score,
            })

        return formatted_results

    def count(self) -> int:
        """Total number of vectors in the collection."""
        try:
            return self.client.count(collection_name=self.collection_name, exact=True).count
        except Exception as e:
            logger.warning(f"Error getting Qdrant count: {e}")
            return 0

    def clear(self) -> None:
        """Reset the collection."""
        from qdrant_client.models import Distance, VectorParams

        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
        )


def get_vector_store(
    collection_name: Optional[str] = None,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseVectorStore:
    """Factory to get the configured vector store (Qdrant if URL configured, else ChromaDB)."""
    qdrant_url = url or settings.QDRANT_URL
    if qdrant_url and qdrant_url.strip():
        return QdrantVectorStore(
            url=qdrant_url,
            api_key=api_key or settings.QDRANT_API_KEY,
            collection_name=collection_name or settings.QDRANT_COLLECTION,
        )
    return ChromaVectorStore(collection_name=collection_name or settings.COLLECTION_NAME)
