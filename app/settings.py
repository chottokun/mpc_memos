"""
Application Configuration Management.

This module uses Pydantic's BaseSettings to manage application configuration
through environment variables. It allows for easy setup and modification of
key parameters like API keys, database paths, and model configurations.

A `.env` file can be used to store these variables locally during development.
"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """
    Defines the application's configuration settings.

    Pydantic automatically reads these settings from environment variables.
    For example, the value for `API_KEY` will be read from the environment
    variable `API_KEY`.

    Attributes:
        API_KEY: The secret key for API authentication. If not set, auth may be disabled.
        NO_AUTH: If True, disables API key authentication globally.
        CHROMA_PATH: The local filesystem path for the ChromaDB persistent store.
        EMBED_MODEL: The name of the sentence-transformers model to use.
        DEVICE: The device to run the embedding model on (e.g., 'cpu', 'cuda').
        MAX_CHUNK_CHARS: The maximum number of characters for a single text chunk.
        N_RESULTS_DEFAULT: The default number of search results to return.
        EMBED_THREAD_WORKERS: The number of worker threads for blocking tasks.
        MEMO_TTL_DAYS: The number of days after which a memo is considered expired.
    """
    API_KEY: Optional[str] = None
    NO_AUTH: bool = False
    CHROMA_PATH: str = "./chroma_db"
    EMBED_MODEL: str = "cl-nagoya/ruri-v3-30m"
    DEVICE: str = "cpu"
    MAX_CHUNK_CHARS: int = 2000
    N_RESULTS_DEFAULT: int = 5
    EMBED_THREAD_WORKERS: int = 2
    MEMO_TTL_DAYS: int = 30

    class Config:
        """Pydantic configuration options."""
        env_file = ".env"
        env_file_encoding = "utf-8"

# Create a single, importable instance of the settings
settings = Settings()
