from dataclasses import dataclass, field
import logging
from typing import Any, Optional

from src.config import settings
from src.embeddings import BaseEmbedder, get_embedder
from src.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """Represents a retrieved document chunk with relevance scoring and source attribution."""
    text: str
    file_name: str
    source_path: str
    chunk_index: int
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalService:
    """Handles query embedding, ChromaDB vector search, and similarity threshold filtering."""

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        embedder: Optional[BaseEmbedder] = None,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        score_drop_threshold: Optional[float] = None,
    ):
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedder = embedder or get_embedder()
        self.top_k = top_k if top_k is not None else settings.TOP_K
        self.min_score = min_score if min_score is not None else settings.SIMILARITY_THRESHOLD
        self.score_drop_threshold = (
            score_drop_threshold
            if score_drop_threshold is not None
            else getattr(settings, "SCORE_DROP_THRESHOLD", 0.15)
        )

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        score_drop_threshold: Optional[float] = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks from vector store filtered by similarity threshold and score cutoff.
        
        Args:
            query: The user's search query string.
            top_k: Maximum number of chunks to fetch (defaults to self.top_k).
            min_score: Minimum similarity score threshold (defaults to self.min_score).
            score_drop_threshold: Maximum allowed score drop below rank #1 chunk.
            
        Returns:
            List of RetrievedChunk objects meeting or exceeding the similarity and cutoff thresholds.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        limit = top_k if top_k is not None else self.top_k
        threshold = min_score if min_score is not None else self.min_score

        if self.vector_store.count() == 0:
            logger.warning("Vector database is empty; returning 0 chunks.")
            return []

        # 1. Generate query embedding
        query_embedding = self.embedder.embed_text(clean_query)

        # 2. Vector search in ChromaDB
        raw_results = self.vector_store.query_by_embedding(query_embedding, top_k=limit)

        # 3. Map and filter results by absolute threshold
        retrieved_chunks: list[RetrievedChunk] = []
        for r in raw_results:
            meta = r.get("metadata") or {}
            score = float(r.get("score") or 0.0)

            # Apply relevance threshold filter
            if score < threshold:
                logger.debug(
                    f"Discarding chunk from {meta.get('file_name', 'unknown')} (score {score:.4f} < threshold {threshold:.4f})"
                )
                continue

            chunk = RetrievedChunk(
                text=r.get("text", "") or "",
                file_name=meta.get("file_name") or "unknown",
                source_path=meta.get("source") or meta.get("file_path") or "unknown",
                chunk_index=int(meta.get("chunk_index") or 0),
                score=score,
                metadata=meta,
            )
            retrieved_chunks.append(chunk)

        # 4. Apply score-aware relative cutoff (removes steep cliff filler chunks)
        relative_cutoff = (
            score_drop_threshold
            if score_drop_threshold is not None
            else self.score_drop_threshold
        )
        if relative_cutoff > 0.0 and retrieved_chunks:
            top_score = retrieved_chunks[0].score
            cutoff_score = top_score - relative_cutoff
            filtered_chunks = [c for c in retrieved_chunks if c.score >= cutoff_score]
            if len(filtered_chunks) < len(retrieved_chunks):
                logger.info(
                    f"Score-aware cutoff (margin={relative_cutoff:.2f}) pruned "
                    f"{len(retrieved_chunks) - len(filtered_chunks)} filler chunk(s) scoring < {cutoff_score:.3f} "
                    f"(kept {len(filtered_chunks)}/{len(retrieved_chunks)})"
                )
                retrieved_chunks = filtered_chunks

        logger.info(
            f"Query '{clean_query[:50]}' -> retrieved {len(retrieved_chunks)} relevant chunks (threshold={threshold:.2f}, drop_margin={relative_cutoff:.2f})"
        )
        return retrieved_chunks

