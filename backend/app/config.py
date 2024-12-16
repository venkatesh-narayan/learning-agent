from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_uri: Optional[str] = None
    openai_api_key: Optional[str] = None
    gcs_bucket: str = "scraped-financial-data"
    cors_origins: List[str] = ["http://localhost:3000"]
    environment: str = "development"
    engine_name: str = "gpt-4o"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
