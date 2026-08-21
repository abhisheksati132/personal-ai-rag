import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src import api
from src.llm import GroqAuthError, GroqRateLimitError, OllamaConnectionError
from src.prompt import FALLBACK_NO_INFO_RESPONSE
from src.retrieval import RetrievedChunk


class TestAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(api.app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("ollama_connected", data)
        self.assertIn("groq_configured", data)
        self.assertIn("indexed_files", data)

    def test_stats_endpoint(self):
        response = self.client.get("/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_files", data)

    def test_files_endpoint(self):
        response = self.client.get("/files")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_query_validation_empty_string(self):
        response = self.client.post("/query", json={"question": ""})
        self.assertEqual(response.status_code, 422)

    def test_query_validation_whitespace_only(self):
        response = self.client.post("/query", json={"question": "   "})
        self.assertEqual(response.status_code, 422)

    @patch.object(api, "_retrieval_service")
    @patch.object(api, "_llm_local")
    def test_query_success_with_context_local_default(self, mock_llm, mock_retrieval):
        mock_retrieval.retrieve.return_value = [
            RetrievedChunk(
                text="Lexical Analysis is phase 1.",
                file_name="compiler.pdf",
                source_path="/docs/compiler.pdf",
                chunk_index=0,
                score=0.82,
            )
        ]
        mock_llm.generate.return_value = "Lexical analysis is the first phase [source: compiler.pdf]."
        mock_llm.model_name = "llama3.2"

        response = self.client.post("/query", json={"question": "What is phase 1?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "Lexical analysis is the first phase [source: compiler.pdf].")
        self.assertEqual(data["provider"], "local")
        self.assertEqual(data["model"], "llama3.2")
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["file"], "compiler.pdf")
        self.assertEqual(data["sources"][0]["chunk_index"], 0)
        self.assertEqual(data["sources"][0]["score"], 0.82)

    @patch.object(api, "_retrieval_service")
    @patch.object(api, "_llm_local")
    def test_query_success_with_context_local_explicit(self, mock_llm, mock_retrieval):
        mock_retrieval.retrieve.return_value = [
            RetrievedChunk(
                text="Lexical Analysis is phase 1.",
                file_name="compiler.pdf",
                source_path="/docs/compiler.pdf",
                chunk_index=0,
                score=0.82,
            )
        ]
        mock_llm.generate.return_value = "Grounded local response."
        mock_llm.model_name = "llama3.2"

        response = self.client.post("/query", json={"question": "What is phase 1?", "provider": "local"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "local")
        self.assertEqual(data["answer"], "Grounded local response.")

    @patch("src.api.get_llm")
    @patch.object(api, "_retrieval_service")
    def test_query_success_cloud_provider(self, mock_retrieval, mock_get_llm):
        mock_retrieval.retrieve.return_value = [
            RetrievedChunk(
                text="Lexical Analysis is phase 1.",
                file_name="compiler.pdf",
                source_path="/docs/compiler.pdf",
                chunk_index=0,
                score=0.82,
            )
        ]
        mock_cloud_llm = MagicMock()
        mock_cloud_llm.generate.return_value = "Groq cloud synthesized answer."
        mock_cloud_llm.model_name = "llama-3.3-70b-versatile"
        mock_get_llm.return_value = mock_cloud_llm

        response = self.client.post("/query", json={"question": "What is phase 1?", "provider": "cloud"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "cloud")
        self.assertEqual(data["model"], "llama-3.3-70b-versatile")
        self.assertEqual(data["answer"], "Groq cloud synthesized answer.")
        mock_get_llm.assert_called_with(provider="cloud")

    @patch("src.api.get_llm")
    @patch.object(api, "_retrieval_service")
    def test_query_cloud_missing_key_returns_400(self, mock_retrieval, mock_get_llm):
        mock_retrieval.retrieve.return_value = [
            RetrievedChunk(
                text="Some text",
                file_name="doc.txt",
                source_path="/docs/doc.txt",
                chunk_index=0,
                score=0.75,
            )
        ]
        mock_cloud_llm = MagicMock()
        mock_cloud_llm.generate.side_effect = GroqAuthError("Groq API key not configured. Set GROQ_API_KEY...")
        mock_get_llm.return_value = mock_cloud_llm

        response = self.client.post("/query", json={"question": "What is this?", "provider": "cloud"})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Groq API key not configured", data["detail"])

    @patch("src.api.get_llm")
    @patch.object(api, "_retrieval_service")
    def test_query_cloud_rate_limited_returns_429(self, mock_retrieval, mock_get_llm):
        mock_retrieval.retrieve.return_value = [
            RetrievedChunk(
                text="Some text",
                file_name="doc.txt",
                source_path="/docs/doc.txt",
                chunk_index=0,
                score=0.75,
            )
        ]
        mock_cloud_llm = MagicMock()
        mock_cloud_llm.generate.side_effect = GroqRateLimitError("Groq cloud rate limit exceeded.")
        mock_get_llm.return_value = mock_cloud_llm

        response = self.client.post("/query", json={"question": "What is this?", "provider": "cloud"})
        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertIn("rate limit exceeded", data["detail"])

    @patch.object(api, "_retrieval_service")
    def test_query_fallback_when_no_context(self, mock_retrieval):
        mock_retrieval.retrieve.return_value = []

        response = self.client.post("/query", json={"question": "What is the recipe for cookies?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], FALLBACK_NO_INFO_RESPONSE)
        self.assertEqual(data["provider"], "local")
        self.assertEqual(len(data["sources"]), 0)

    @patch.object(api, "_retrieval_service")
    def test_query_ollama_unreachable_returns_503(self, mock_retrieval):
        mock_retrieval.retrieve.side_effect = OllamaConnectionError("Ollama is down")

        response = self.client.post("/query", json={"question": "What is phase 1?"})
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertIn("Ollama is down", data["detail"])


if __name__ == "__main__":
    unittest.main()
