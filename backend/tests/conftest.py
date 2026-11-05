import pytest

from app.ai import llm
from app.services import supabase_store


@pytest.fixture(autouse=True)
def no_openai(monkeypatch):
    """Tests never call the real API, even when backend/.env holds a key."""
    monkeypatch.setattr(llm, "api_key", lambda: None)


@pytest.fixture(autouse=True)
def no_supabase(monkeypatch):
    monkeypatch.setattr(supabase_store, "enabled", lambda: False)
