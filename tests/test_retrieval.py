import shutil
import tempfile
import unittest
from pathlib import Path

from src.chunker import Chunk
from src.embeddings import MockEmbedder
from src.retrieval import RetrievalService
from src.vector_store import ChromaVectorStore


class TestRetrieval(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.chroma_dir = self.test_dir / "chroma"
        self.vector_store = ChromaVectorStore(
            persist_dir=self.chroma_dir,
            collection_name="test_retrieval",
        )
        self.embedder = MockEmbedder(dimension=64)

        # Add sample chunks
        chunks = [
            Chunk(
                text="Lexical analysis breaks input source code into tokens.",
                chunk_index=0,
                start_char=0,
                end_char=55,
                metadata={"file_name": "compiler.pdf", "source": "compiler.pdf"},
            ),
            Chunk(
                text="Full mesh topology requires n*(n-1)/2 links for n nodes.",
                chunk_index=1,
                start_char=0,
                end_char=58,
                metadata={"file_name": "networks.pdf", "source": "networks.pdf"},
            ),
        ]
        embeddings = self.embedder.embed_documents([c.text for c in chunks])
        self.vector_store.add_chunks(chunks, embeddings)

        self.retrieval_service = RetrievalService(
            vector_store=self.vector_store,
            embedder=self.embedder,
            top_k=5,
            min_score=-1.0,  # MockEmbedder generates cosine scores around 0
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_retrieve_returns_chunks(self):
        chunks = self.retrieval_service.retrieve("Lexical tokens", top_k=2)
        self.assertEqual(len(chunks), 2)
        self.assertIn(chunks[0].file_name, ["compiler.pdf", "networks.pdf"])
        self.assertIsInstance(chunks[0].score, float)
        self.assertTrue(len(chunks[0].text) > 0)

    def test_retrieve_empty_query_returns_empty_list(self):
        chunks = self.retrieval_service.retrieve("   ")
        self.assertEqual(len(chunks), 0)

    def test_similarity_threshold_filters_out_chunks(self):
        # Set an impossibly high threshold (e.g. 0.99 for mock vectors)
        chunks = self.retrieval_service.retrieve("random text", min_score=0.99)
        self.assertEqual(len(chunks), 0)


if __name__ == "__main__":
    unittest.main()
