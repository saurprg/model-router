import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    gateway_api_key: str
    models_config_path: Path = Path("config/models.yaml")
    connect_timeout_s: float = 3.0
    read_timeout_s: float = 120.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_provider_api_key(env_name: str) -> str | None:
    value = os.environ.get(env_name, "").strip()
    return value or None
