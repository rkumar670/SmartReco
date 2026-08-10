import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).parent / ".data"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["CHROMA_PATH"] = str(TEST_ROOT / "chroma")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    TEST_ROOT.mkdir(exist_ok=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
