from pathlib import Path
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DOCUMENTS_DIR: Path = DATA_DIR / "documents"
    CHROMA_DIR: Path = DATA_DIR / "chroma_db"
    SQLITE_DB_PATH: Path = DATA_DIR / "brain.db"

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_MODEL: str = "llama3.1:8b"

    # Chunking Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    # ChromaDB Collection
    COLLECTION_NAME: str = "personal_brain"

    # Supported File Extensions
    SUPPORTED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".md"]

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        self.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    class Config:
        env_prefix = "BRAIN_"
        env_file = ".env"
        extra = "ignore"


settings = Settings()
settings.ensure_directories()
