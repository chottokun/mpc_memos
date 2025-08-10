from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    API_KEY: Optional[str] = None
    NO_AUTH: bool = False
    CHROMA_PATH: str = "./chroma_db"
    EMBED_MODEL: str = "cl-nagoya/ruri-v3-30m"
    DEVICE: str = "cpu"
    MAX_CHUNK_CHARS: int = 2000
    N_RESULTS_DEFAULT: int = 5
    EMBED_THREAD_WORKERS: int = 2

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
