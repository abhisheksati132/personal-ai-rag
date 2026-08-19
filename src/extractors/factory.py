from pathlib import Path
from typing import Optional

from src.extractors.base import BaseExtractor
from src.extractors.docx_extractor import DocxExtractor
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.text_extractor import TextExtractor


class ExtractorFactory:
    """Factory for obtaining the appropriate extractor based on file type."""

    _EXTRACTORS: dict[str, type[BaseExtractor]] = {
        ".pdf": PDFExtractor,
        ".docx": DocxExtractor,
        ".txt": TextExtractor,
        ".md": TextExtractor,
    }

    @classmethod
    def supports(cls, file_path: Path) -> bool:
        """Check if file extension is supported."""
        suffix = Path(file_path).suffix.lower()
        return suffix in cls._EXTRACTORS

    @classmethod
    def get_extractor(cls, file_path: Path) -> BaseExtractor:
        """Get the extractor instance for the given file."""
        suffix = Path(file_path).suffix.lower()
        extractor_cls = cls._EXTRACTORS.get(suffix)

        if not extractor_cls:
            supported = ", ".join(cls._EXTRACTORS.keys())
            raise ValueError(f"Unsupported file type '{suffix}' for {file_path}. Supported: {supported}")

        return extractor_cls()

    @classmethod
    def register_extractor(cls, extension: str, extractor_cls: type[BaseExtractor]) -> None:
        """Allow registering additional custom extractors."""
        cls._EXTRACTORS[extension.lower()] = extractor_cls
