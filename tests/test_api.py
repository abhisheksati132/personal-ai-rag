import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src import api
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
    @patch.object(api, "_llm")
    def test_query_success_with_context(self, mock_llm, mock_retrieval):
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

        response = self.client.post("/query", json={"question": "What is phase 1?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "Lexical analysis is the first phase [source: compiler.pdf].")
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["file"], "compiler.pdf")
        self.assertEqual(data["sources"][0]["chunk_index"], 0)
        self.assertEqual(data["sources"][0]["score"], 0.82)

    @patch.object(api, "_retrieval_service")
    def test_query_fallback_when_no_context(self, mock_retrieval):
        mock_retrieval.retrieve.return_value = []

        response = self.client.post("/query", json={"question": "What is the recipe for cookies?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], FALLBACK_NO_INFO_RESPONSE)
        self.assertEqual(len(data["sources"]), 0)

    @patch.object(api, "_retrieval_service")
    def test_query_ollama_unreachable_returns_503(self, mock_retrieval):
        from src.llm import OllamaConnectionError
        mock_retrieval.retrieve.side_effect = OllamaConnectionError("Ollama is down")

        response = self.client.post("/query", json={"question": "What is phase 1?"})
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertIn("Ollama is down", data["detail"])


if __name__ == "__main__":
    unittest.main()
