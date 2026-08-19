import logging
from pathlib import Path
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.extractors.base import BaseExtractor, ExtractedDocument

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """Extracts text and page-level metadata from PDF documents."""

    def extract(self, file_path: Path) -> ExtractedDocument:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            reader = PdfReader(str(file_path))
        except PdfReadError as e:
            logger.error(f"Corrupted or invalid PDF {file_path}: {e}")
            raise

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:
                raise ValueError(f"Encrypted PDF cannot be read without password: {file_path}") from e

        page_texts: list[str] = []
        total_pages = len(reader.pages)

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    page_texts.append(page_text.strip())
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num} of {file_path}: {e}")

        full_text = "\n\n".join(page_texts)

        # Extract document metadata if present
        pdf_meta = reader.metadata or {}
        meta = {
            "file_name": file_path.name,
            "extension": file_path.suffix.lower(),
            "total_pages": total_pages,
            "title": str(pdf_meta.get("/Title", "") or ""),
            "author": str(pdf_meta.get("/Author", "") or ""),
        }

        return ExtractedDocument(
            text=full_text,
            file_path=file_path,
            metadata=meta
        )
