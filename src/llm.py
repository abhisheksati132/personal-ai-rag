from abc import ABC, abstractmethod
import logging
from typing import Optional
import ollama

from src.config import settings

logger = logging.getLogger(__name__)


class OllamaLLMError(Exception):
    """Base exception for Ollama LLM errors."""
    pass


class OllamaConnectionError(OllamaLLMError):
    """Raised when Ollama server cannot be reached."""
    pass


class OllamaModelError(OllamaLLMError):
    """Raised when the specified model is not available or encounters an internal error."""
    pass


class BaseLLM(ABC):
    """Abstract interface for local language models."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response for the given prompt and optional system prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if LLM backend and model are reachable."""
        pass


class OllamaLLM(BaseLLM):
    """Local LLM generator using Ollama chat endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: float = 60.0,
    ):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model_name = model_name or settings.LLM_MODEL
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.timeout = timeout
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
        except Exception:
            return False

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response via Ollama chat API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                options={"temperature": self.temperature},
            )

            if hasattr(response, "message") and hasattr(response.message, "content"):
                return response.message.content.strip()
            elif isinstance(response, dict) and "message" in response:
                return response["message"].get("content", "").strip()
            else:
                return str(response).strip()

        except ollama.ResponseError as e:
            logger.error(f"Ollama returned model error: {e}")
            raise OllamaModelError(f"Model '{self.model_name}' error: {e.error}") from e

        except Exception as e:
            # Handle connection / network failures gracefully
            err_str = str(e).lower()
            if "connect" in err_str or "connection" in err_str or "refused" in err_str:
                logger.error(f"Cannot connect to Ollama at {self.base_url}: {e}")
                raise OllamaConnectionError(
                    f"Ollama server unreachable at {self.base_url}. Please ensure Ollama is running."
                ) from e
            logger.error(f"Unexpected LLM generation error: {e}", exc_info=True)
            raise OllamaLLMError(f"LLM generation failed: {e}") from e


class MockLLM(BaseLLM):
    """Deterministic mock LLM for unit tests and offline testing."""

    def __init__(self, response_text: str = "This is a mock grounded answer. [source: sample.pdf]"):
        self.response_text = response_text

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if "No relevant context found" in prompt:
            return "I don't have information on that in your indexed files."
        return self.response_text


def get_llm(use_mock: bool = False, model_name: Optional[str] = None) -> BaseLLM:
    """Factory function to instantiate an LLM provider."""
    if use_mock:
        return MockLLM()
    return OllamaLLM(model_name=model_name)
