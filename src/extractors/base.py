from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractedDocument:
    """Represents text and metadata extracted from a file."""
    text: str
    file_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return not bool(self.text.strip())


class BaseExtractor(ABC):
    """Abstract base class for all file extractors."""

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractedDocument:
        """Extract text and metadata from the given file path.
        
        Args:
            file_path: Path to the target file.
            
        Returns:
            ExtractedDocument containing extracted text and metadata.
            
        Raises:
            Exception: If extraction fails due to formatting or I/O errors.
        """
        pass
