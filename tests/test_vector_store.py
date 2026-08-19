import shutil
import tempfile
import unittest
from pathlib import Path

from src.chunker import Chunk
from src.embeddings import MockEmbedder
from src.vector_store import ChromaVectorStore


class TestVectorStore(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.chroma_dir = self.test_dir / "chroma"
        self.vector_store = ChromaVectorStore(
            persist_dir=self.chroma_dir,
            collection_name="test_collection",
        )
        self.embedder = MockEmbedder(dimension=128)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_query_delete_chunks(self):
        chunks = [
            Chunk(
                text="Artificial Intelligence and Machine Learning models.",
                chunk_index=0,
                start_char=0,
                end_char=52,
                metadata={"source": "doc1.txt", "file_name": "doc1.txt"},
            ),
            Chunk(
                text="Vector databases store embeddings for similarity search.",
                chunk_index=1,
                start_char=53,
                end_char=109,
                metadata={"source": "doc1.txt", "file_name": "doc1.txt"},
            ),
            Chunk(
                text="Cooking recipes for Italian pasta and pizza dough.",
                chunk_index=0,
                start_char=0,
                end_char=50,
                metadata={"source": "doc2.txt", "file_name": "doc2.txt"},
            ),
        ]

        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_documents(texts)

        # Add chunks
        added = self.vector_store.add_chunks(chunks, embeddings)
        self.assertEqual(added, 3)
        self.assertEqual(self.vector_store.count(), 3)

        # Query vector
        query_vec = self.embedder.embed_text("Machine Learning models")
        results = self.vector_store.query_by_embedding(query_vec, top_k=2)

        self.assertGreater(len(results), 0)
        self.assertIn("score", results[0])
        self.assertIn("text", results[0])

        # Delete by source
        self.vector_store.delete_by_source("doc1.txt")
        self.assertEqual(self.vector_store.count(), 1)


if __name__ == "__main__":
    unittest.main()
