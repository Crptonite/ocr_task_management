"""In-memory store for the mock data.

Edits (approvals, new tasks, status changes) live until the server restarts.
Replace with SQLAlchemy + Supabase Postgres once the schema is agreed.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


erp: dict = {}
orders: dict = {}
projects: dict = {}


def reset() -> None:
    """(Re)load all mock data. Tests call this to start clean."""
    erp.clear()
    erp.update(_load("mock_erp.json"))
    orders.clear()
    orders.update(_load("mock_orders.json"))
    for i, order in enumerate(orders["orders"], start=1):
        order.setdefault("id", f"ord-{i}")
    projects.clear()
    projects.update(_load("mock_projects.json"))


def next_id(prefix: str, items: list[dict]) -> str:
    nums = [int(i["id"].split("-")[1]) for i in items if i["id"].startswith(prefix + "-")]
    return f"{prefix}-{max(nums, default=0) + 1}"


reset()
