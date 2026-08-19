from abc import ABC, abstractmethod
import hashlib
import logging
import math
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
            # models_res is a ListResponse or dict
            model_names = []
            if hasattr(models_res, "models"):
                model_names = [m.model for m in models_res.models]
            elif isinstance(models_res, dict) and "models" in models_res:
                model_names = [m.get("name", "") for m in models_res["models"]]
            
            # Check if our embedding model is in the list
            found = any(self.model_name in name for name in model_names)
            return found
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


class MockEmbedder(BaseEmbedder):
    """Deterministic mock embedder for offline tests and development without Ollama."""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension

    def _hash_to_vector(self, text: str) -> list[float]:
        # Generate pseudo-random deterministic vector from text hash
        vec = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{text}_{i}".encode("utf-8")).digest()
            val = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 - 1
            vec.append(val)
        
        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_text(self, text: str) -> list[float]:
        return self._hash_to_vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def get_embedder(use_mock: bool = False) -> BaseEmbedder:
    """Factory function to get an embedder, falling back to mock if requested."""
    if use_mock:
        return MockEmbedder()
    return OllamaEmbedder()
