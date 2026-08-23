from abc import ABC, abstractmethod
import logging
from typing import Optional
import httpx
import ollama

from src.config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# LLM Exceptions
# ==============================================================================

class LLMError(Exception):
    """Base exception for all LLM errors."""
    pass


class OllamaLLMError(LLMError):
    """Base exception for Ollama LLM errors."""
    pass


class OllamaConnectionError(OllamaLLMError):
    """Raised when Ollama server cannot be reached."""
    pass


class OllamaModelError(OllamaLLMError):
    """Raised when the specified Ollama model is not available or encounters an error."""
    pass


class GroqLLMError(LLMError):
    """Base exception for Groq cloud LLM errors."""
    pass


class GroqAuthError(GroqLLMError):
    """Raised when GROQ_API_KEY is missing or invalid (401)."""
    pass


class GroqRateLimitError(GroqLLMError):
    """Raised when Groq API rate limits are exceeded (429)."""
    pass


class GroqAPIError(GroqLLMError):
    """Raised when Groq encounters upstream or server errors (5xx, timeouts)."""
    pass


# ==============================================================================
# Abstract Base LLM Interface
# ==============================================================================

class BaseLLM(ABC):
    """Abstract interface for local and cloud language models."""

    provider_name: str = "local"
    model_name: str = ""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response for the given prompt and optional system prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if LLM backend and model are reachable/configured."""
        pass


# ==============================================================================
# Local Provider: Ollama
# ==============================================================================

class OllamaLLM(BaseLLM):
    """Local LLM generator using Ollama chat endpoint."""

    provider_name: str = "local"

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
            err_str = str(e).lower()
            if "connect" in err_str or "connection" in err_str or "refused" in err_str:
                logger.error(f"Cannot connect to Ollama at {self.base_url}: {e}")
                raise OllamaConnectionError(
                    f"Ollama server unreachable at {self.base_url}. Please ensure Ollama is running."
                ) from e
            logger.error(f"Unexpected LLM generation error: {e}", exc_info=True)
            raise OllamaLLMError(f"LLM generation failed: {e}") from e


# ==============================================================================
# Cloud Provider: Groq (OpenAI-Compatible)
# ==============================================================================

class GroqLLM(BaseLLM):
    """Cloud LLM generator using Groq's fast, free-tier OpenAI-compatible API."""

    provider_name: str = "cloud"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self.model_name = model_name or settings.GROQ_MODEL
        self.base_url = (base_url or settings.GROQ_BASE_URL).rstrip("/")

        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.timeout = timeout or settings.GROQ_TIMEOUT

    def is_available(self) -> bool:
        """Check if Groq API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response via Groq chat completions API."""
        if not self.is_available():
            raise GroqAuthError(
                "Groq API key not configured. Set GROQ_API_KEY in your .env file or environment. "
                "You can obtain a free API key at https://console.groq.com/keys"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Personal-AI-Brain/1.0",
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        try:
            logger.info(
                f"Dispatching query to Groq Cloud ({self.model_name}) at {url} "
                f"[messages={len(messages)}, system_len={len(system_prompt or '')}, user_len={len(prompt)}]"
            )
            logger.debug(f"Groq Request Messages: {messages}")
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)


            if response.status_code == 401:
                logger.error(f"Groq API key authentication failed (401): {response.text}")
                raise GroqAuthError("Invalid Groq API key. Please check your GROQ_API_KEY setting.")

            if response.status_code == 429:
                logger.warning(f"Groq rate limit exceeded (429): {response.text}")
                raise GroqRateLimitError(
                    "Groq cloud rate limit exceeded. Please wait a moment before querying again, or switch to Local Ollama."
                )

            if response.is_error:
                logger.error(f"Groq API returned HTTP {response.status_code}: {response.text}")
                raise GroqAPIError(f"Groq Cloud error ({response.status_code}): {response.text}")

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise GroqAPIError("Groq returned an empty choice list.")

            content = choices[0].get("message", {}).get("content", "")
            return content.strip()

        except (GroqAuthError, GroqRateLimitError, GroqAPIError):
            raise

        except httpx.TimeoutException as e:
            logger.error(f"Groq request timed out after {self.timeout}s: {e}")
            raise GroqAPIError(f"Groq Cloud request timed out ({self.timeout}s).") from e

        except httpx.RequestError as e:
            logger.error(f"Network error connecting to Groq Cloud ({self.base_url}): {e}")
            raise GroqAPIError(f"Failed to connect to Groq Cloud: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error calling Groq Cloud: {e}", exc_info=True)
            raise GroqLLMError(f"Groq Cloud generation error: {e}") from e


# ==============================================================================
# Mock Provider for Unit Tests & Offline Dev
# ==============================================================================

class MockLLM(BaseLLM):
    """Deterministic mock LLM for unit tests and offline testing."""

    def __init__(
        self,
        provider_name: str = "local",
        model_name: str = "mock-model",
        response_text: str = "This is a mock grounded answer. [source: sample.pdf]",
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.response_text = response_text

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if "No relevant context found" in prompt:
            return "I don't have information on that in your indexed files."
        return self.response_text


# ==============================================================================
# LLM Provider Factory
# ==============================================================================

def get_llm(
    provider: str = "local",
    use_mock: bool = False,
    model_name: Optional[str] = None,
) -> BaseLLM:
    """Factory function to instantiate an LLM provider ('local' or 'cloud')."""
    if use_mock:
        return MockLLM(provider_name=provider, model_name=model_name or "mock-model")

    if provider == "cloud":
        return GroqLLM(model_name=model_name)

    return OllamaLLM(model_name=model_name)
