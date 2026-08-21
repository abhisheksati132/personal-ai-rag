from pathlib import Path
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Optional[Path] = None
    DOCUMENTS_DIR: Optional[Path] = None
    CHROMA_DIR: Optional[Path] = None
    SQLITE_DB_PATH: Optional[Path] = None

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_MODEL: str = "llama3.2"
    LLM_TEMPERATURE: float = 0.1

    # Groq Cloud LLM Settings
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TIMEOUT: float = 30.0

    # Retrieval Configuration
    SIMILARITY_THRESHOLD: float = 0.40
    TOP_K: int = 8


    # Chunking Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    # ChromaDB Collection
    COLLECTION_NAME: str = "personal_brain"

    # Supported File Extensions
    SUPPORTED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".md"]

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        import os
        if self.DATA_DIR is None:
            self.DATA_DIR = self.BASE_DIR / "data"
        if self.DOCUMENTS_DIR is None:
            self.DOCUMENTS_DIR = self.DATA_DIR / "documents"
        if self.CHROMA_DIR is None:
            self.CHROMA_DIR = self.DATA_DIR / "chroma_db"
        if self.SQLITE_DB_PATH is None:
            self.SQLITE_DB_PATH = self.DATA_DIR / "brain.db"
        if not self.GROQ_API_KEY:
            self.GROQ_API_KEY = os.getenv("GROQ_API_KEY") or None
        return self


    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        if self.DATA_DIR:
            self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.DOCUMENTS_DIR:
            self.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        if self.CHROMA_DIR:
            self.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    class Config:
        env_prefix = "BRAIN_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()
settings.ensure_directories()

