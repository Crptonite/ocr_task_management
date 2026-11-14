"""In-memory store the routers read and edit.

At startup app.database loads it from the database (SQLite or Supabase Postgres, see
app/models.py) and writes changes back after every API request. reset() loads the mock JSON,
which seeds an empty database and gives tests a clean start.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


erp: dict = {}
orders: dict = {}
projects: dict = {}
planning: dict = {}


def reset() -> None:
    """(Re)load all mock data. Tests call this to start clean."""
    erp.clear()
    erp.update(_load("mock_erp.json"))
    orders.clear()
    orders.update(_load("mock_orders.json"))
    for i, order in enumerate(orders["orders"], start=1):
        order.setdefault("id", f"ord-{i}")
        order.setdefault("transaction_id", f"TXN-{i:05d}")
    projects.clear()
    projects.update(_load("mock_projects.json"))
    planning.clear()
    planning.update(_load("mock_planning.json"))


def next_id(prefix: str, items: list[dict]) -> str:
    nums = [int(i["id"].split("-")[1]) for i in items if i["id"].startswith(prefix + "-")]
    return f"{prefix}-{max(nums, default=0) + 1}"


reset()
