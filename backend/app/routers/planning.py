"""Production planning: material requirements, shortages and build priorities."""
from datetime import date

from fastapi import APIRouter, HTTPException

from app import store
from app.services.planning import plan

router = APIRouter(prefix="/api", tags=["planning"])


@router.get("/planning")
def get_plan(as_of: str | None = None):
    """Full plan. `as_of` (YYYY-MM-DD) overrides today, handy for demos and tests."""
    try:
        today = date.fromisoformat(as_of) if as_of else None
    except ValueError:
        raise HTTPException(status_code=422, detail="as_of must be YYYY-MM-DD")
    return plan(store.planning, today)
