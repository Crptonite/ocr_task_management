"""Owner: Wesley (testing). EM Services project tracker."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import store
from app.ai.task_suggester import suggest_tasks
from app.main import app
from app.services.projects import is_overdue, project_summary

client = TestClient(app)
TODAY = "2026-10-29"


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def test_overdue_ignores_done_tasks():
    today = date(2026, 10, 29)
    assert is_overdue({"status": "todo", "due_date": "2026-10-01"}, today)
    assert not is_overdue({"status": "done", "due_date": "2026-10-01"}, today)
    assert not is_overdue({"status": "todo", "due_date": "2026-11-01"}, today)
    assert not is_overdue({"status": "todo", "due_date": None}, today)


def test_project_summary_progress_and_health():
    tasks = [{"status": "done", "due_date": None}, {"status": "todo", "due_date": "2026-10-01"}]
    summary = project_summary({"id": "p"}, tasks, date(2026, 10, 29))
    assert summary["progress"] == 0.5
    assert summary["health"] == "at_risk"


def test_list_projects():
    projects = client.get(f"/api/projects?today={TODAY}").json()
    assert len(projects) == 3
    assert projects[0]["overdue_count"] == 2  # permit + contractor schedule


def test_task_crud():
    created = client.post(
        f"/api/projects/prj-3/tasks?today={TODAY}",
        json={"title": "Install LED panels", "owner": "Priya", "due_date": "2026-10-01"},
    )
    assert created.status_code == 201
    task = created.json()
    assert task["overdue"] is True

    updated = client.patch(f"/api/tasks/{task['id']}?today={TODAY}", json={"status": "done"}).json()
    assert updated["status"] == "done" and updated["overdue"] is False

    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).status_code == 404


def test_rejects_bad_status_and_blank_title():
    assert client.patch("/api/tasks/tsk-1", json={"status": "blocked"}).status_code == 422
    assert client.post("/api/projects/prj-1/tasks", json={"title": "  "}).status_code == 422


def test_overdue_summary_names_owners():
    body = client.get(f"/api/projects/prj-1/overdue-summary?today={TODAY}").json()
    assert [t["id"] for t in body["overdue"]] == ["tsk-2", "tsk-3"]
    assert "Farah" in body["summary"] and "Marcus" in body["summary"]


def test_suggestions_skip_existing_tasks():
    titles = [s["title"] for s in suggest_tasks("Lift upgrade with contractor", ["Book lift contractor"])]
    assert "Book lift contractor" not in titles
    assert "Notify residents of lift downtime" in titles
    assert client.post("/api/projects/prj-2/suggest-tasks", json={}).json()


def test_unknown_project_404():
    assert client.get("/api/projects/nope").status_code == 404
