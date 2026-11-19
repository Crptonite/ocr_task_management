"""6b Part 2: 3-Way Match (invoice vs PO vs hard-copy receipt), discrepancy tasks & dept-head approval (Qizhi).

GET  /api/three-way-match/users                        demo identities (header X-User picks who is acting)
GET  /api/three-way-match/scenarios                    demo invoices + receipt text, incl. the error cases
GET  /api/three-way-match/invoices                     invoices already in the Review Queue
POST /api/three-way-match/receipts/extract             receipt PDF / photo -> text + parsed lines
POST /api/three-way-match/match                        3-way match + auto-create suggested tasks
GET  /api/three-way-match/matches/{invoice_no}         last stored match result
GET  /api/three-way-match/tasks                        task board data (?status= &department= &invoice_no=)
PATCH /api/three-way-match/tasks/{id}                  status / assignee
POST /api/three-way-match/tasks/{id}/request-approval  ask the department head
POST /api/three-way-match/tasks/{id}/decision          dept head approves / rejects
GET  /api/three-way-match/audit, /audit/verify         hash-chained audit trail + integrity check
"""
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from qizhi.pdf_extract import ExtractError, extract_receipt_text, sniff_kind
from qizhi.receipt_parser import parse_receipt_text, receipt_to_json
from qizhi.sample_data import SCENARIOS
from qizhi.service import erp_invoices, run_match, store
from qizhi.store import STATUSES, USERS, StoreError

router = APIRouter(prefix="/api/three-way-match", tags=["three-way match (Koda 6b Part 2)"])

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 20_000


def _guarded(action, *args):
    """Run a store action, turning its rule violations into HTTP errors."""
    try:
        return action(*args)
    except StoreError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc))


def current_user(x_user: str = Header(default="alex")) -> dict:
    user = USERS.get(x_user.lower())
    if not user:
        raise HTTPException(status_code=401, detail=f"Unknown user '{x_user}'.")
    return {**user, "id": x_user.lower()}


class LineIn(BaseModel):
    sku: str | None = Field(default="", max_length=40)
    description: str = Field(min_length=1, max_length=200)
    qty: float = Field(ge=0, le=1_000_000)
    unit_price: float | None = Field(default=None, ge=0, le=10_000_000)
    line_total: float | None = Field(default=None, ge=0, le=100_000_000)


class InvoiceIn(BaseModel):
    invoice_no: str = Field(min_length=1, max_length=40)
    vendor: str = Field(default="", max_length=120)
    po_number: str | None = Field(default="", max_length=40)
    date: str | None = Field(default=None, max_length=40)
    lines: list[LineIn] = Field(min_length=1, max_length=200)
    subtotal: float | None = Field(default=None, ge=0, le=100_000_000)
    tax_rate: float | None = Field(default=None, ge=0, le=1)
    tax: float | None = Field(default=None, ge=0, le=100_000_000)
    total: float | None = Field(default=None, ge=0, le=100_000_000)


class MatchIn(BaseModel):
    invoice: InvoiceIn
    receipt_text: str | None = Field(default=None, max_length=MAX_TEXT)
    create_tasks: bool = True


class TaskPatch(BaseModel):
    status: Literal["open", "in_progress", "resolved"] | None = None
    assignee: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=300)


class ApprovalIn(BaseModel):
    proposed_resolution: str = Field(min_length=3, max_length=500)


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=500)


@router.get("/users")
def list_users():
    return [{"id": k, **v} for k, v in USERS.items()]


@router.get("/scenarios")
def list_scenarios():
    return [{"id": k, "label": v["label"], "invoice": v["invoice"], "receipt_text": v["receipt_text"]}
            for k, v in SCENARIOS.items()]


@router.get("/invoices")
def list_review_queue_invoices():
    return erp_invoices()


@router.post("/receipts/extract")
async def extract_receipt(file: UploadFile = File(...)):
    """PDF / photo of a hard-copy receipt -> text + parsed lines, so a person can check before matching."""
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is over 10 MB.")
    if sniff_kind(data) is None:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload a PDF, PNG or JPG receipt.")
    try:
        out = await run_in_threadpool(extract_receipt_text, data)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not out["text"].strip():
        raise HTTPException(status_code=422, detail="No text could be read from the receipt. Paste it instead.")
    return {"text": out["text"], "method": out["method"], "parsed": receipt_to_json(parse_receipt_text(out["text"]))}


@router.post("/match")
def match(body: MatchIn, user: dict = Depends(current_user)):
    return run_match(body.invoice.model_dump(), body.receipt_text, user, body.create_tasks)


@router.get("/matches/{invoice_no}")
def last_match(invoice_no: str):
    result = store.results.get(invoice_no)
    if not result:
        raise HTTPException(status_code=404, detail="No match has been run for this invoice yet.")
    return result


@router.get("/tasks")
def list_tasks(status: str | None = None, department: str | None = None, invoice_no: str | None = None):
    tasks = [t for t in store.tasks.values()
             if (not status or t["status"] == status) and (not department or t["department"] == department)
             and (not invoice_no or t["invoice_no"] == invoice_no)]
    tasks.sort(key=lambda t: (t["priority"], t["created_at"]))
    return {"columns": STATUSES, "tasks": tasks}


@router.patch("/tasks/{task_id}")
def patch_task(task_id: str, body: TaskPatch, user: dict = Depends(current_user)):
    return _guarded(store.update_task, user, task_id, body.status, body.assignee, body.note)


@router.post("/tasks/{task_id}/request-approval")
def request_approval(task_id: str, body: ApprovalIn, user: dict = Depends(current_user)):
    return _guarded(store.request_approval, user, task_id, body.proposed_resolution)


@router.post("/tasks/{task_id}/decision")
def decide(task_id: str, body: DecisionIn, user: dict = Depends(current_user)):
    return _guarded(store.decide, user, task_id, body.decision, body.comment)


@router.get("/audit")
def audit(invoice_no: str | None = None, task_id: str | None = None):
    return store.audit_for(task_id=task_id, invoice_no=invoice_no)


@router.get("/audit/verify")
def audit_verify():
    return store.verify_audit()
