import unittest
from src.chunker import RecursiveChunker


class TestChunker(unittest.TestCase):

    def setUp(self):
        self.chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)

    def test_empty_text(self):
        chunks = self.chunker.chunk_text("")
        self.assertEqual(len(chunks), 0)

        chunks = self.chunker.chunk_text("   \n\n  ")
        self.assertEqual(len(chunks), 0)

    def test_short_text_single_chunk(self):
        text = "This is a short sentence."
        chunks = self.chunker.chunk_text(text, base_metadata={"source": "test.txt"})

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[0].end_char, len(text))
        self.assertEqual(chunks[0].metadata["source"], "test.txt")
        self.assertTrue(chunks[0].chunk_id)

    def test_long_text_multiple_chunks_with_overlap(self):
        paragraphs = [
            "Paragraph one introduces the main subject of this document with enough words to fill space.",
            "Paragraph two goes into deeper technical details regarding vector embeddings and chunking.",
            "Paragraph three concludes with observations about local-first AI system architectures.",
        ]
        full_text = "\n\n".join(paragraphs)

        chunks = self.chunker.chunk_text(full_text, base_metadata={"file_name": "test.txt"})
        self.assertGreater(len(chunks), 1)

        # Verify each chunk size does not exceed chunk_size excessively
        for c in chunks:
            self.assertLessEqual(len(c.text), 150)
            self.assertIn("file_name", c.metadata)

    def test_invalid_overlap_raises(self):
        with self.assertRaises(ValueError):
            RecursiveChunker(chunk_size=100, chunk_overlap=100)


if __name__ == "__main__":
    unittest.main()
