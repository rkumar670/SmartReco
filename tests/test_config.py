import os

from app.config import Settings, load_observability_environment


def test_observability_settings_are_loaded():
    settings = Settings(
        logfire_token="logfire-test-token",
        logfire_send_to_logfire=True,
        langsmith_tracing=True,
        langsmith_api_key="langsmith-test-key",
        langsmith_project="smartreco-test",
    )

    assert settings.logfire_token == "logfire-test-token"
    assert settings.logfire_send_to_logfire is True
    assert settings.langsmith_tracing is True
    assert settings.langsmith_api_key == "langsmith-test-key"
    assert settings.langsmith_project == "smartreco-test"


def test_langsmith_settings_are_exported(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key="langsmith-test-key",
        langsmith_project="smartreco-test",
    )

    load_observability_environment(settings)

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "langsmith-test-key"
    assert os.environ["LANGSMITH_PROJECT"] == "smartreco-test"
