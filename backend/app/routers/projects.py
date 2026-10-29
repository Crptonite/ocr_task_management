"""EM Services: projects, task board and AI helpers."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.ai.task_suggester import suggest_tasks
from app.services.projects import is_overdue, project_summary, summarize_overdue

router = APIRouter(prefix="/api", tags=["projects (EM Services)"])

Status = Literal["todo", "in_progress", "done"]


class TaskIn(BaseModel):
    title: str
    owner: str | None = None
    due_date: date | None = None
    status: Status = "todo"


class TaskPatch(BaseModel):
    title: str | None = None
    owner: str | None = None
    due_date: date | None = None
    status: Status | None = None


class BriefIn(BaseModel):
    brief: str | None = None


def find_project(project_id: str) -> dict:
    project = next((p for p in store.projects["projects"] if p["id"] == project_id), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def find_task(task_id: str) -> dict:
    task = next((t for t in store.projects["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def tasks_for(project_id: str) -> list[dict]:
    return [t for t in store.projects["tasks"] if t["project_id"] == project_id]


def with_overdue(task: dict, today: date) -> dict:
    return {**task, "overdue": is_overdue(task, today)}


@router.get("/members")
def list_members():
    return store.projects["members"]


# `today` is a query param so demos and tests can pin the date; it defaults to the real date.
@router.get("/projects")
def list_projects(today: date | None = None):
    today = today or date.today()
    return [project_summary(p, tasks_for(p["id"]), today) for p in store.projects["projects"]]


@router.get("/projects/{project_id}")
def get_project(project_id: str, today: date | None = None):
    today = today or date.today()
    project = find_project(project_id)
    tasks = tasks_for(project_id)
    return {**project_summary(project, tasks, today), "tasks": [with_overdue(t, today) for t in tasks]}


@router.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: str, body: TaskIn, today: date | None = None):
    find_project(project_id)
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    task = {
        "id": store.next_id("tsk", store.projects["tasks"]),
        "project_id": project_id,
        "title": body.title.strip(),
        "owner": body.owner,
        "due_date": body.due_date.isoformat() if body.due_date else None,
        "status": body.status,
    }
    store.projects["tasks"].append(task)
    return with_overdue(task, today or date.today())


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskPatch, today: date | None = None):
    task = find_task(task_id)
    changes = body.model_dump(exclude_unset=True)
    if "due_date" in changes and changes["due_date"] is not None:
        changes["due_date"] = changes["due_date"].isoformat()
    task.update(changes)
    return with_overdue(task, today or date.today())


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    store.projects["tasks"].remove(find_task(task_id))


@router.get("/projects/{project_id}/overdue-summary")
def overdue_summary(project_id: str, today: date | None = None):
    return summarize_overdue(find_project(project_id), tasks_for(project_id), today or date.today())


@router.post("/projects/{project_id}/suggest-tasks")
def suggest(project_id: str, body: BriefIn):
    project = find_project(project_id)
    existing = [t["title"] for t in tasks_for(project_id)]
    return suggest_tasks(body.brief or project["brief"], existing)
