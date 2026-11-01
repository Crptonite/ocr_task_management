"""Project tracker rules (EM Services): progress and overdue work.

Owner: Aeric (backend).
"""
from datetime import date

TASK_STATUSES = ("todo", "in_progress", "done")


def is_overdue(task: dict, today: date) -> bool:
    return task["status"] != "done" and bool(task.get("due_date")) and date.fromisoformat(task["due_date"]) < today


def project_summary(project: dict, tasks: list[dict], today: date) -> dict:
    done = sum(1 for t in tasks if t["status"] == "done")
    overdue = sum(1 for t in tasks if is_overdue(t, today))
    if overdue:
        health = "at_risk"
    elif tasks and done == len(tasks):
        health = "complete"
    else:
        health = "on_track"
    return {
        **project,
        "task_count": len(tasks),
        "done_count": done,
        "overdue_count": overdue,
        "progress": round(done / len(tasks), 2) if tasks else 0.0,
        "health": health,
    }


def summarize_overdue(project: dict, tasks: list[dict], today: date) -> dict:
    """Plain-language overdue summary. Template-based until an LLM is wired in (see app.ai)."""
    overdue = sorted((t for t in tasks if is_overdue(t, today)), key=lambda t: t["due_date"])
    if not overdue:
        return {"overdue": [], "summary": f"Nothing overdue on {project['name']}."}

    items = []
    for t in overdue:
        days = (today - date.fromisoformat(t["due_date"])).days
        items.append({**t, "days_late": days})
    by_owner: dict[str, int] = {}
    for t in items:
        by_owner[t["owner"] or "Unassigned"] = by_owner.get(t["owner"] or "Unassigned", 0) + 1
    worst = items[0]
    owners = ", ".join(f"{o} ({n})" for o, n in sorted(by_owner.items(), key=lambda kv: -kv[1]))
    summary = (
        f"{len(items)} task(s) overdue on {project['name']}. "
        f"Most urgent: \"{worst['title']}\" ({worst['owner'] or 'unassigned'}), {worst['days_late']} day(s) late. "
        f"Follow up with: {owners}."
    )
    return {"overdue": items, "summary": summary}
