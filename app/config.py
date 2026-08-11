import os
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
    recommendation_cooldown_seconds: int = 30
    logfire_token: str = ""
    logfire_send_to_logfire: bool = False
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "smartreco"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_observability_environment(settings: Settings) -> None:
    os.environ["LANGSMITH_TRACING"] = str(settings.langsmith_tracing).lower()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
