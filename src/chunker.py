from dataclasses import dataclass, field
import hashlib
from typing import Any, Optional


@dataclass
class Chunk:
    """Represents a discrete slice of text from a document with positional and source metadata."""
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self):
        if not self.chunk_id:
            # Generate deterministic chunk ID based on source and index
            source = str(self.metadata.get("source", "doc"))
            content_hash = hashlib.md5(self.text.encode("utf-8")).hexdigest()[:8]
            self.chunk_id = f"{Path_safe_name(source)}_{self.chunk_index}_{content_hash}"


def Path_safe_name(source: str) -> str:
    """Generate a clean identifier from a file path."""
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", source)
    return cleaned[-40:]  # Keep last 40 chars to avoid excessively long IDs


class RecursiveChunker:
    """Recursively splits text into overlapping chunks respecting natural semantic boundaries."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        separators: Optional[list[str]] = None,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap ({chunk_overlap}) must be smaller than chunk_size ({chunk_size})")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

    def chunk_text(self, text: str, base_metadata: Optional[dict[str, Any]] = None) -> list[Chunk]:
        """Split a raw text string into a list of Chunk objects."""
        if not text or not text.strip():
            return []

        base_metadata = base_metadata or {}
        raw_splits = self._split_recursive(text, self.separators)

        # Merge splits into chunks of desired size with overlap
        chunks: list[Chunk] = []
        current_pieces: list[str] = []
        current_len = 0
        chunk_index = 0
        char_search_offset = 0

        import re
        section_pattern = re.compile(
            r"^(?:\n\s*|\A)(?:[a-zA-Z]\)|Question\s+\d+|#+\s+|\d+\.\s+|[A-Z\s]{4,}:)",
            re.MULTILINE,
        )

        for piece in raw_splits:
            piece_len = len(piece)
            is_new_section = bool(section_pattern.search(piece[:60]))

            # Flush if size exceeded OR if a distinct new section starts and current chunk is substantial
            should_flush = (current_len + piece_len > self.chunk_size) or (
                is_new_section and current_len >= min(250, int(self.chunk_size * 0.4))
            )

            if should_flush and current_pieces:
                # Flush current chunk
                chunk_str = "".join(current_pieces).strip()
                if chunk_str:
                    start_char = text.find(chunk_str, char_search_offset)
                    if start_char == -1:
                        start_char = 0
                    end_char = start_char + len(chunk_str)
                    char_search_offset = max(0, start_char)

                    chunk_meta = {**base_metadata, "chunk_index": chunk_index}
                    chunks.append(
                        Chunk(
                            text=chunk_str,
                            chunk_index=chunk_index,
                            start_char=start_char,
                            end_char=end_char,
                            metadata=chunk_meta,
                        )
                    )
                    chunk_index += 1

                # Retain overlap pieces from end of current_pieces unless starting a brand new top-level section
                overlap_pieces: list[str] = []
                if not is_new_section:
                    overlap_len = 0
                    for p in reversed(current_pieces):
                        if overlap_len + len(p) <= self.chunk_overlap:
                            overlap_pieces.insert(0, p)
                            overlap_len += len(p)
                        else:
                            break

                current_pieces = overlap_pieces
                current_len = sum(len(p) for p in current_pieces)

            current_pieces.append(piece)
            current_len += piece_len

        # Flush final remaining pieces
        if current_pieces:
            chunk_str = "".join(current_pieces).strip()
            if chunk_str:
                start_char = text.find(chunk_str, char_search_offset)
                if start_char == -1:
                    start_char = 0
                end_char = start_char + len(chunk_str)

                chunk_meta = {**base_metadata, "chunk_index": chunk_index}
                chunks.append(
                    Chunk(
                        text=chunk_str,
                        chunk_index=chunk_index,
                        start_char=start_char,
                        end_char=end_char,
                        metadata=chunk_meta,
                    )
                )

        return chunks

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text by separators until pieces fit within chunk_size."""
        if not separators:
            return [text]

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator == "":
            # Character-level fallback
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

        parts = text.split(separator)
        pieces: list[str] = []

        for i, part in enumerate(parts):
            # Reattach separator except for last part
            full_part = part + separator if i < len(parts) - 1 else part
            if not full_part:
                continue

            if len(full_part) <= self.chunk_size:
                pieces.append(full_part)
            else:
                if remaining_separators:
                    sub_pieces = self._split_recursive(full_part, remaining_separators)
                    pieces.extend(sub_pieces)
                else:
                    # Hard truncate fallback
                    for j in range(0, len(full_part), self.chunk_size):
                        pieces.append(full_part[j : j + self.chunk_size])

        return pieces
