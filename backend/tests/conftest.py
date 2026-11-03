import pytest

from app.ai import llm


@pytest.fixture(autouse=True)
def no_openai(monkeypatch):
    """Tests never call the real API, even when backend/.env holds a key."""
    monkeypatch.setattr(llm, "api_key", lambda: None)
