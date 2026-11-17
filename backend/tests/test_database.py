"""Database persistence: store <-> SQLite round trip, seeding, and edits surviving a restart."""
import pytest
from fastapi.testclient import TestClient

from app import database, store
from app.main import app


@pytest.fixture
def db(monkeypatch, tmp_path):
    """A fresh SQLite file; init() seeds it from the mock data."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    store.reset()
    status = database.init()
    assert database.active(), status
    return tmp_path


def restart():
    """Simulate a server restart: wipe memory back to the mock data, then load from the database."""
    database.close()
    store.reset()
    for group in (store.erp, store.orders, store.projects, store.planning):
        for key in group:
            group[key] = type(group[key])()  # empty, so anything left must come from the database
    status = database.init()
    assert "loaded" in status, status


def test_url_forms(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/postgres")
    assert database.database_url() == "postgresql+psycopg://u:p@host:5432/postgres"
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    assert database.database_url().startswith("postgresql+psycopg://")
    monkeypatch.setenv("DATABASE_URL", "off")
    assert database.database_url() is None
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setattr(database, "ENV_FILE", database.BACKEND_DIR / "no-such.env")
    assert database.database_url() == database.DEFAULT_URL


def test_seed_then_reload_gives_identical_store(db):
    before = {name: getattr(store, group)[name] for group, name, *_ in database.COLLECTIONS}
    restart()
    for group, name, *_ in database.COLLECTIONS:
        after = getattr(store, group)[name]
        if isinstance(after, list) and after and isinstance(after[0], dict):
            # columns a record did not carry come back as None; nothing else changes
            after = [{k: v for k, v in r.items() if v is not None or k in b} for r, b in zip(after, before[name])]
        assert after == before[name], name


def test_persist_writes_only_changed_collections(db):
    assert database.persist() == []
    store.projects["tasks"][0]["status"] = "in_progress"
    assert database.persist() == ["tasks"]
    assert database.persist() == []


def test_api_edits_survive_restart(db):
    client = TestClient(app)
    assert client.get("/api/health").json()["database"] == "sqlite"

    task = client.post("/api/projects/prj-1/tasks", json={"title": "Order spare parts"}).json()
    client.patch("/api/tasks/tsk-1", json={"status": "in_progress"})
    assert client.post("/api/orders/ord-2/approve").status_code == 200  # ord-2 is the valid mock order
    client.delete("/api/invoices/HHE-30551")

    restart()

    tasks = {t["id"]: t for t in store.projects["tasks"]}
    assert tasks[task["id"]]["title"] == "Order spare parts"
    assert tasks["tsk-1"]["status"] == "in_progress"
    assert all(i["invoice_number"] != "HHE-30551" for i in store.erp["invoices"])
    # nested workflow data (approval, invoice draft, history) comes back too
    saved = next(o for o in store.orders["orders"] if o["id"] == "ord-2")
    assert saved["status"] == "approved"
    assert saved["approval"]["decision"] == "approved"
    assert saved["invoice"]["status"] == "pending"
    assert saved["status_history"][-1]["status"] == "approved"
    assert client.get("/api/projects/prj-1").status_code == 200
    assert client.get("/api/planning").status_code == 200


def test_unreachable_database_falls_back_to_memory(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none?connect_timeout=1")
    status = database.init()
    assert not database.active()
    assert "in-memory" in status
    assert database.persist() == []
