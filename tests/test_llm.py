import unittest
from unittest.mock import MagicMock, patch

from src.llm import (
    BaseLLM,
    GroqAPIError,
    GroqAuthError,
    GroqLLM,
    GroqRateLimitError,
    MockLLM,
    OllamaLLM,
    get_llm,
)


class TestLLM(unittest.TestCase):

    def test_mock_llm(self):
        mock_llm = MockLLM(provider_name="cloud", response_text="Custom mock answer")
        self.assertEqual(mock_llm.provider_name, "cloud")
        self.assertTrue(mock_llm.is_available())
        ans = mock_llm.generate("Hello world")
        self.assertEqual(ans, "Custom mock answer")

    def test_factory_returns_correct_providers(self):
        local_llm = get_llm(provider="local")
        self.assertIsInstance(local_llm, OllamaLLM)
        self.assertEqual(local_llm.provider_name, "local")

        cloud_llm = get_llm(provider="cloud")
        self.assertIsInstance(cloud_llm, GroqLLM)
        self.assertEqual(cloud_llm.provider_name, "cloud")

        mock_llm = get_llm(provider="local", use_mock=True)
        self.assertIsInstance(mock_llm, MockLLM)

    def test_groq_missing_api_key_raises_auth_error(self):
        groq_llm = GroqLLM(api_key="")
        self.assertFalse(groq_llm.is_available())
        with self.assertRaises(GroqAuthError) as ctx:
            groq_llm.generate("Test prompt")
        self.assertIn("Groq API key not configured", str(ctx.exception))

    @patch("httpx.Client")
    def test_groq_successful_generation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Groq answer text"}}]
        }
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        groq_llm = GroqLLM(api_key="gsk_test_123")
        self.assertTrue(groq_llm.is_available())
        ans = groq_llm.generate("Explain transformers", system_prompt="You are an expert")
        self.assertEqual(ans, "Groq answer text")

    @patch("httpx.Client")
    def test_groq_auth_failure_raises_groq_auth_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid API key"
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        groq_llm = GroqLLM(api_key="gsk_invalid_123")
        with self.assertRaises(GroqAuthError) as ctx:
            groq_llm.generate("Test prompt")
        self.assertIn("Invalid Groq API key", str(ctx.exception))

    @patch("httpx.Client")
    def test_groq_rate_limit_raises_groq_rate_limit_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit reached"
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        groq_llm = GroqLLM(api_key="gsk_test_123")
        with self.assertRaises(GroqRateLimitError) as ctx:
            groq_llm.generate("Test prompt")
        self.assertIn("rate limit exceeded", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
