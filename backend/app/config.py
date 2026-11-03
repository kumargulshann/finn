from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite:///./data/finn.db"
    frontend_origin: str = "http://localhost:3000"
    market_cache_ttl_seconds: int = 900
    auto_refresh_hours: float = 0  # >0 starts a background NSE filings refresh loop (enabled in Docker)

    model_config = SettingsConfigDict(
        env_prefix="FINN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

