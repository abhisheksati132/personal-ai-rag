import logging
from pathlib import Path
from typing import Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from src.chunker import Chunk
from src.config import settings

logger = logging.getLogger(__name__)


def sanitize_metadata(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Ensure all metadata values are primitive types allowed by ChromaDB."""
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


class ChromaVectorStore:
    """ChromaDB persistent vector store manager."""

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        collection_name: Optional[str] = None,
    ):
        self.persist_dir = Path(persist_dir or settings.CHROMA_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or settings.COLLECTION_NAME

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
        )
        self.collection = self.client.get_or_create_collection(
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

        # Upsert into ChromaDB in batches if large
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
            logger.info(f"Deleted vector chunks for source: {source_str}")
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
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
