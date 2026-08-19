import logging
from pathlib import Path

from src.extractors.base import BaseExtractor, ExtractedDocument

logger = logging.getLogger(__name__)


class TextExtractor(BaseExtractor):
    """Extracts text from plain text and Markdown files (.txt, .md)."""

    ENCODINGS_TO_TRY = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    def extract(self, file_path: Path) -> ExtractedDocument:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw_bytes = file_path.read_bytes()
        text = None
        used_encoding = None

        for encoding in self.ENCODINGS_TO_TRY:
            try:
                text = raw_bytes.decode(encoding)
                used_encoding = encoding
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            # Fallback with replacement characters
            text = raw_bytes.decode("utf-8", errors="replace")
            used_encoding = "utf-8-replaced"
            logger.warning(f"Could not decode {file_path} cleanly; used utf-8 with replacement chars.")

        meta = {
            "file_name": file_path.name,
            "extension": file_path.suffix.lower(),
            "line_count": len(text.splitlines()),
            "encoding": used_encoding,
        }

        return ExtractedDocument(
            text=text.strip(),
            file_path=file_path,
            metadata=meta
        )
