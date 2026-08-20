import logging
from typing import Optional

from src.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

FALLBACK_NO_INFO_RESPONSE = "I don't have information on that in your indexed files."

SYSTEM_PROMPT = """You are a precise, grounded AI assistant that answers questions based ONLY on the user's personal documents.

Strict Rules:
1. Answer the question using ONLY the provided context chunks below.
2. Do NOT use any outside training knowledge or make up facts.
3. Every factual claim in your answer must cite the source file it came from (e.g. [source: filename.pdf]).
4. If the provided context does not contain the answer, state clearly and honestly: "I don't have information on that in your indexed files."
5. Be direct, concise, and structured in your explanation."""


class PromptBuilder:
    """Constructs grounded prompts and formats context chunks with source citations."""

    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or SYSTEM_PROMPT

    def build_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> tuple[str, str, bool]:
        """Build system prompt, user prompt with context, and a flag indicating if context is present.
        
        Args:
            question: The user's input question.
            chunks: List of retrieved context chunks.
            
        Returns:
            Tuple of (system_prompt: str, user_prompt: str, has_context: bool)
        """
        clean_question = question.strip()

        if not chunks:
            # When no context is retrieved, provide short-circuit flag
            user_prompt = f"Question: {clean_question}\n\nContext: [No relevant context found in indexed files]"
            return self.system_prompt, user_prompt, False

        # Format context blocks
        context_blocks: list[str] = []
        for idx, chunk in enumerate(chunks, 1):
            block = (
                f"--- Context Block {idx} [Source: {chunk.file_name} | Chunk #{chunk.chunk_index} | Score: {chunk.score:.3f}] ---\n"
                f"{chunk.text.strip()}\n"
            )
            context_blocks.append(block)

        formatted_context = "\n".join(context_blocks)

        user_prompt = (
            f"Context from indexed documents:\n\n"
            f"{formatted_context}\n\n"
            f"Question: {clean_question}\n\n"
            f"Instructions: Provide an accurate answer based ONLY on the context blocks above. Cite the source document name(s)."
        )

        return self.system_prompt, user_prompt, True
