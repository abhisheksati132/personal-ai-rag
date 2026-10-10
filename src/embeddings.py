from abc import ABC, abstractmethod
import hashlib
import logging
import math
from pathlib import Path
from typing import Optional
# pyrefly: ignore [missing-import]
import ollama

from src.config import settings

logger = logging.getLogger(__name__)


class BaseEmbedder(ABC):
    """Abstract interface for generating embeddings."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single string."""
        pass

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of strings."""
        pass


class OllamaEmbedder(BaseEmbedder):
    """Generates embeddings using local Ollama model (e.g., nomic-embed-text)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        batch_size: int = 16,
    ):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.batch_size = batch_size
        self.client = ollama.Client(host=self.base_url)

    def is_available(self) -> bool:
        """Check if Ollama server is reachable and model is available."""
        try:
            models_res = self.client.list()
            model_names = []
            if hasattr(models_res, "models"):
                model_names = [m.model for m in models_res.models]
            elif isinstance(models_res, dict) and "models" in models_res:
                model_names = [m.get("name", "") for m in models_res["models"]]
            
            return any(self.model_name in name for name in model_names)
        except Exception as e:
            logger.debug(f"Ollama healthcheck failed: {e}")
            return False

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text using Ollama."""
        clean_text = text.strip() or " "
        try:
            res = self.client.embeddings(model=self.model_name, prompt=clean_text)
            if hasattr(res, "embedding"):
                return res.embedding
            return res["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding with Ollama for text: {e}")
            raise

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings in batches."""
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            for text in batch:
                embeddings.append(self.embed_text(text))
        return embeddings


class FastEmbedder(BaseEmbedder):
    """Generates embeddings using CPU-based FastEmbed (default: nomic-ai/nomic-embed-text-v1.5-Q, 768 dimensions).
    Ideal for cloud deployments (Render) where Ollama is not running on the container host.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        doc_prefix: Optional[str] = None,
        query_prefix: Optional[str] = None,
        cache_dir: Optional[Path | str] = None,
    ):
        self.model_name = model_name or getattr(settings, "FASTEMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5-Q")
        self.doc_prefix = doc_prefix if doc_prefix is not None else getattr(settings, "EMBED_DOC_PREFIX", "")
        self.query_prefix = query_prefix if query_prefix is not None else getattr(settings, "EMBED_QUERY_PREFIX", "")
        self.cache_dir = Path(cache_dir or getattr(settings, "FASTEMBED_CACHE_DIR", settings.BASE_DIR / ".fastembed_cache"))
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir))
        return self._model

    def is_available(self) -> bool:
        try:
            return self.model is not None
        except Exception:
            return False

    def embed_text(self, text: str) -> list[float]:
        clean_text = text.strip() or " "
        formatted = f"{self.query_prefix}{clean_text}" if self.query_prefix else clean_text
        embeddings = list(self.model.embed([formatted]))
        return [float(x) for x in embeddings[0]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        formatted = [f"{self.doc_prefix}{t}" for t in texts] if self.doc_prefix else texts
        embeddings = list(self.model.embed(formatted))
        return [[float(x) for x in vec] for vec in embeddings]


class MockEmbedder(BaseEmbedder):
    """Deterministic mock embedder for offline tests and development without Ollama."""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension

    def _hash_to_vector(self, text: str) -> list[float]:
        vec = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{text}_{i}".encode("utf-8")).digest()
            val = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 - 1
            vec.append(val)
        
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_text(self, text: str) -> list[float]:
        return self._hash_to_vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def get_embedder(use_mock: bool = False, provider: Optional[str] = None) -> BaseEmbedder:
    """Factory function to get an embedder.
    Supports 'auto', 'ollama', 'fastembed', 'mock'.
    In 'auto' mode: uses Ollama if available; otherwise falls back to FastEmbedder.
    """
    prov = (provider or getattr(settings, "EMBEDDING_PROVIDER", "auto")).lower()
    if use_mock or prov == "mock":
        return MockEmbedder()
    if prov == "fastembed":
        return FastEmbedder()
    if prov == "ollama":
        return OllamaEmbedder()

    # 'auto': Try Ollama first; if unavailable, seamlessly fall back to FastEmbedder
    ollama_embedder = OllamaEmbedder()
    if ollama_embedder.is_available():
        return ollama_embedder
    logger.info("Ollama unavailable for embeddings; defaulting to FastEmbedder (nomic-ai/nomic-embed-text-v1.5)")
    return FastEmbedder()
