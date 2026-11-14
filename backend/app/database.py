"""Saves app.store to a database: SQLite locally, or Supabase Postgres.

Owner: Aeric (backend). The routers keep working on the in-memory dicts in app.store; this module
loads those dicts from the database at startup and writes back every collection that changed after
each API request (main.py's middleware calls persist()). A rewrite replaces that collection's rows
in one transaction, so the database never holds half an edit.

DATABASE_URL (environment, else backend/.env) picks the database:
  unset                                  SQLite file backend/koda.db
  sqlite:///path/to/file.db              another SQLite file
  postgresql://user:pass@host:5432/db    Postgres, e.g. Supabase (Project Settings > Database >
                                         Connection string; the session pooler works on IPv4)
  off                                    no database, in-memory only (edits reset on restart)

On Postgres the tables live in their own `workspace` schema: no clash with other tables in the
project, and Supabase's public REST API (anon key) cannot reach them.
"""
import json
import os
import threading
from pathlib import Path

from sqlalchemy import Engine, create_engine, delete, select, text
from sqlalchemy.orm import Session

from app import store
from app.models import (Base, CatalogItem, Demand, InboundDelivery, Material, Member, Order, Product, Project,
                        PurchaseOrder, SupplierInvoice, Task)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_URL = f"sqlite:///{(BACKEND_DIR / 'koda.db').as_posix()}"
PG_SCHEMA = "workspace"

# (store dict, key in it, model, shape). Shapes: "list" of records, "names" (list of strings),
# "by_sku" (dict of sku -> record).
COLLECTIONS = [
    ("erp", "purchase_orders", PurchaseOrder, "list"),
    ("erp", "invoices", SupplierInvoice, "list"),
    ("orders", "catalog", CatalogItem, "list"),
    ("orders", "orders", Order, "list"),
    ("projects", "members", Member, "names"),
    ("projects", "projects", Project, "list"),
    ("projects", "tasks", Task, "list"),
    ("planning", "products", Product, "by_sku"),
    ("planning", "materials", Material, "by_sku"),
    ("planning", "inbound", InboundDelivery, "list"),
    ("planning", "demand", Demand, "list"),
]
WHOLE_NUMBER_FIELDS = {"qty", "quantity", "on_hand"}  # 30.0 back to 30, as the mock data has it
INTERNAL = {"pk", "position", "extra"}

_engine: Engine | None = None
_saved: dict[str, str] = {}  # collection name -> snapshot last written, to skip unchanged ones
_lock = threading.Lock()


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if not value and ENV_FILE.exists():
        try:
            from dotenv import dotenv_values

            value = dotenv_values(ENV_FILE).get(name)
        except ImportError:
            pass
    return value.strip() or None if value else None


def database_url() -> str | None:
    """The SQLAlchemy URL to use, or None when the database is switched off."""
    url = _env("DATABASE_URL") or DEFAULT_URL
    if url.lower() in ("off", "none", "memory"):
        return None
    for prefix in ("postgres://", "postgresql://"):  # the form Supabase shows; use the psycopg 3 driver
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    engine = create_engine(
        url,
        pool_pre_ping=True,  # Supabase closes idle connections
        connect_args={"prepare_threshold": None},  # Supabase's transaction pooler has no prepared statements
    )
    with engine.begin() as conn:
        conn.execute(text(f'create schema if not exists "{PG_SCHEMA}"'))
    return engine.execution_options(schema_translate_map={None: PG_SCHEMA})


def active() -> bool:
    return _engine is not None


def backend_name() -> str:
    return _engine.dialect.name if _engine is not None else "memory"


# ---- converting between store records and rows ----

def _fields(model) -> list[str]:
    return [c.key for c in model.__table__.columns if c.key not in INTERNAL]


def _records(shape: str, value) -> list[dict]:
    if shape == "names":
        return [{"name": n} for n in value]
    if shape == "by_sku":
        return [{"sku": sku, **rec} for sku, rec in value.items()]
    return value


def _to_row(model, record: dict, position: int):
    fields = _fields(model)
    # Only keys the record has: an absent one gets the column default (e.g. lines -> []), not NULL.
    return model(position=position, extra={k: v for k, v in record.items() if k not in fields},
                 **{k: record[k] for k in fields if k in record})


def _from_row(row) -> dict:
    record = {}
    for field in _fields(type(row)):
        value = getattr(row, field)
        if field in WHOLE_NUMBER_FIELDS and isinstance(value, float) and value.is_integer():
            value = int(value)
        record[field] = value
    return record | (row.extra or {})


def _shape_back(shape: str, records: list[dict]):
    if shape == "names":
        return [r["name"] for r in records]
    if shape == "by_sku":
        return {r.pop("sku"): r for r in records}
    return records


def _snapshot(records: list[dict]) -> str:
    return json.dumps(records, sort_keys=True, default=str)


# ---- lifecycle ----

def init() -> str:
    """Connect, create missing tables, then load the store from the database (seeding an empty one
    with the mock data). Returns a status line. If the database cannot be reached, the app keeps
    running in memory and the line says why."""
    global _engine
    url = database_url()
    if url is None:
        return "Database off: in-memory store only"
    try:
        engine = _make_engine(url)
        Base.metadata.create_all(engine)
        _engine = engine
        _saved.clear()
        seeded = not load()
        if seeded:
            persist()
        return f"Database: {backend_name()} ({'seeded with mock data' if seeded else 'loaded'})"
    except Exception as exc:
        _engine = None
        return f"Database unavailable, using in-memory store: {type(exc).__name__}: {exc}"


def load() -> bool:
    """Replace the store's collections with the database's. False (store untouched) if the database is empty."""
    loaded = {}
    with Session(_engine) as session:
        for _, name, model, shape in COLLECTIONS:
            rows = session.scalars(select(model).order_by(model.position, model.pk)).all()
            loaded[name] = [_from_row(r) for r in rows]
    if not any(loaded.values()):
        return False
    for group, name, _, shape in COLLECTIONS:
        records = loaded[name]
        _saved[name] = _snapshot(records)
        getattr(store, group)[name] = _shape_back(shape, records)
    return True


def persist() -> list[str]:
    """Write every collection that changed since the last write. Returns their names."""
    if _engine is None:
        return []
    with _lock:
        changed = []
        for group, name, model, shape in COLLECTIONS:
            records = _records(shape, getattr(store, group).get(name, []))
            snap = _snapshot(records)
            if snap != _saved.get(name):
                changed.append((name, model, records, snap))
        if not changed:
            return []
        with Session(_engine) as session, session.begin():
            for name, model, records, _ in changed:
                session.execute(delete(model))
                session.add_all(_to_row(model, r, i) for i, r in enumerate(records))
        for name, _, _, snap in changed:
            _saved[name] = snap
        return [name for name, *_ in changed]


def close() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _saved.clear()
