import unittest

from src.prompt import FALLBACK_NO_INFO_RESPONSE, PromptBuilder
from src.retrieval import RetrievedChunk


class TestPromptBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = PromptBuilder()

    def test_build_prompt_with_chunks(self):
        chunks = [
            RetrievedChunk(
                text="A compiler transforms source code into intermediate representation.",
                file_name="compiler_intro.pdf",
                source_path="/docs/compiler_intro.pdf",
                chunk_index=0,
                score=0.75,
            )
        ]

        system_prompt, user_prompt, has_context = self.builder.build_prompt(
            question="What does a compiler do?",
            chunks=chunks,
        )

        self.assertTrue(has_context)
        self.assertIn("compiler_intro.pdf", user_prompt)
        self.assertIn("What does a compiler do?", user_prompt)
        self.assertIn("Strict Rules", system_prompt)

    def test_build_prompt_empty_chunks(self):
        system_prompt, user_prompt, has_context = self.builder.build_prompt(
            question="What is the weather today?",
            chunks=[],
        )

        self.assertFalse(has_context)
        self.assertEqual(FALLBACK_NO_INFO_RESPONSE, "I don't have information on that in your indexed files.")


if __name__ == "__main__":
    unittest.main()
