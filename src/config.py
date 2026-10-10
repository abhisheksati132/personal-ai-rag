import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings

# Load .env from project root
_BASE_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BASE_DIR / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=True)


class Settings(BaseSettings):
    # Base Directories
    BASE_DIR: Path = _BASE_DIR
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
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TIMEOUT: float = 30.0

    # Retrieval Configuration
    SIMILARITY_THRESHOLD: float = 0.40
    TOP_K: int = 8
    SCORE_DROP_THRESHOLD: float = 0.15



    # Chunking Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    # ChromaDB Collection
    COLLECTION_NAME: str = "personal_brain"

    # Cloud Storage & Database Settings
    DATABASE_URL: Optional[str] = None
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "personal_brain"
    EMBEDDING_PROVIDER: str = "auto"
    FASTEMBED_MODEL: str = "nomic-ai/nomic-embed-text-v1.5-Q"
    FASTEMBED_CACHE_DIR: Optional[Path] = None
    EMBED_DOC_PREFIX: str = ""
    EMBED_QUERY_PREFIX: str = ""

    # Single-User Authentication Gate & Security Hardening
    APP_PASSWORD: Optional[str] = None
    AUTH_SECRET_KEY: Optional[str] = None
    AUTH_TOKEN_EXPIRE_SECONDS: int = 30 * 24 * 3600
    BRAIN_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def allowed_origins(self) -> list[str]:
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        origins: list[str] = []
        for orig in self.CORS_ORIGINS.split(","):
            o = orig.strip()
            if o:
                origins.append(o)
                if not (o.startswith("http://") or o.startswith("https://")):
                    origins.append(f"https://{o}")
                    origins.append(f"http://{o}")
        return origins if origins else ["*"]

    # Chrome Bookmarks Settings
    CHROME_BOOKMARKS_PATH: Optional[Path] = None
    CHROME_PROFILE: str = "Default"
    BOOKMARK_FETCH_TIMEOUT: float = 15.0
    BOOKMARK_MAX_CONCURRENCY: int = 4
    BOOKMARK_REQUEST_DELAY: float = 0.3
    BOOKMARK_WATCH_INTERVAL: float = 30.0

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        if self.DATA_DIR is None:
            self.DATA_DIR = self.BASE_DIR / "data"
        if self.DOCUMENTS_DIR is None:
            self.DOCUMENTS_DIR = self.DATA_DIR / "documents"
        if self.CHROMA_DIR is None:
            self.CHROMA_DIR = self.DATA_DIR / "chroma_db"
        if self.SQLITE_DB_PATH is None:
            self.SQLITE_DB_PATH = self.DATA_DIR / "brain.db"
        if self.FASTEMBED_CACHE_DIR is None:
            raw_cache = os.getenv("FASTEMBED_CACHE_DIR") or os.getenv("BRAIN_FASTEMBED_CACHE_DIR")
            if raw_cache:
                p = Path(raw_cache)
                self.FASTEMBED_CACHE_DIR = p if p.is_absolute() else (self.BASE_DIR / p)
            else:
                self.FASTEMBED_CACHE_DIR = self.BASE_DIR / ".fastembed_cache"
        if not self.GROQ_API_KEY:
            self.GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("BRAIN_GROQ_API_KEY") or None
        if not self.DATABASE_URL:
            self.DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("BRAIN_DATABASE_URL") or None
        if not self.QDRANT_URL:
            self.QDRANT_URL = os.getenv("QDRANT_URL") or os.getenv("BRAIN_QDRANT_URL") or None
        if not self.QDRANT_API_KEY:
            self.QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or os.getenv("BRAIN_QDRANT_API_KEY") or None
        if not self.APP_PASSWORD:
            self.APP_PASSWORD = os.getenv("APP_PASSWORD") or os.getenv("BRAIN_APP_PASSWORD") or None
        if not self.AUTH_SECRET_KEY:
            self.AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY") or os.getenv("BRAIN_AUTH_SECRET_KEY") or None


        # Auto-detect Chrome Bookmarks path if not explicitly configured
        if self.CHROME_BOOKMARKS_PATH is None:
            local_appdata = os.getenv("LOCALAPPDATA")
            if local_appdata:
                profile_dir = Path(local_appdata) / "Google" / "Chrome" / "User Data" / self.CHROME_PROFILE
                # Check Bookmarks then AccountBookmarks
                if (profile_dir / "Bookmarks").exists():
                    self.CHROME_BOOKMARKS_PATH = profile_dir / "Bookmarks"
                elif (profile_dir / "AccountBookmarks").exists():
                    self.CHROME_BOOKMARKS_PATH = profile_dir / "AccountBookmarks"
                else:
                    # Default path even if created later
                    self.CHROME_BOOKMARKS_PATH = profile_dir / "Bookmarks"
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

