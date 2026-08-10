from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str = "development-only-change-me"
    database_url: str = "sqlite:///./data/smartreco.db"
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_chat_model: str = "openai/gpt-4o-mini"
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    chroma_path: str = "./data/chroma_data"
    recommendation_event_threshold: int = 5
    recommendation_cooldown_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
