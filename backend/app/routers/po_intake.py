"""6a PO Intake & Validation API (Aeric).

POST /api/po-intake            read a PO (file or pasted text) and validate it
POST /api/po-intake/validate   re-check an edited PO (inline editor)
POST /api/po-intake/email      buyer clarification email for the flagged fields / SKUs
POST /api/po-intake/submit     send a clean PO to the order queue
GET  /api/po-intake/samples    demo POs, including the edge cases
"""
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import store
from app.ai.po_parser import parse_po
from app.services import documents
from app.services.invoice_queue import now_iso, transaction_id
from app.services.po_intake import SAMPLES, clarification_email, validate_po

router = APIRouter(prefix="/api/po-intake", tags=["po intake (Koda 6a)"])

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 100_000
ALLOWED = {".pdf", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".webp"}


class POLine(BaseModel):
    sku: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    unit_price: float | None = Field(default=None, ge=0, le=10_000_000)


class POIn(BaseModel):
    po_number: str | None = Field(default=None, max_length=40)
    buyer: str | None = Field(default=None, max_length=120)
    buyer_email: str | None = Field(default=None, max_length=120)
    port: str | None = Field(default=None, max_length=120)
    order_date: str | None = Field(default=None, max_length=40)
    delivery_date: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=3)
    lines: list[POLine] = Field(default_factory=list, max_length=200)


class SubmitIn(POIn):
    created_by: str = Field(default="Order desk", min_length=1, max_length=80)
    source: str | None = Field(default=None, max_length=120)


def _clean(body: POIn) -> dict:
    data = body.model_dump(exclude={"created_by", "source"})
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = value.strip() or None
    if data.get("currency"):
        data["currency"] = data["currency"].upper()
    return data


def _check(po: dict) -> dict:
    return validate_po(po, store.orders["catalog"], store.orders["orders"])


@router.get("/samples")
def list_samples():
    return [{"id": k, "label": v["label"], "hint": v["hint"], "text": v["text"]} for k, v in SAMPLES.items()]


@router.post("")
async def intake(file: UploadFile | None = File(default=None), text: str | None = Form(default=None)):
    """Read and validate a customer PO. Send a file (PDF, CSV, TXT or image) or pasted text."""
    started = time.perf_counter()
    text = (text or "").strip() or None
    content, filename = None, "pasted text"
    if file is not None and file.filename:
        filename = Path(file.filename).name
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED:
            raise HTTPException(status_code=415, detail=f"{ext or 'This file type'} is not supported. Use PDF, CSV, TXT, PNG, JPG or WEBP.")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"{filename} is empty.")
        if len(content) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File is larger than 10 MB.")
        if ext == ".pdf" and not content.startswith(b"%PDF"):
            raise HTTPException(status_code=415, detail=f"{filename} is not a valid PDF.")
    elif not text:
        raise HTTPException(status_code=400, detail="Upload a PO file or paste the PO text.")
    if text and len(text) > MAX_TEXT:
        raise HTTPException(status_code=413, detail="Pasted text is too long (100,000 characters max).")

    po, meta = parse_po(filename, content=content, text=None if content is not None else text)
    result = _check(po)
    if meta["input"] == "image" and not result["lines"] and not any(result["po"].get(k) for k in ("po_number", "buyer")):
        meta["note"] = meta.get("note") or "Nothing could be read from this image."
    meta.update(source=filename, elapsed_ms=round((time.perf_counter() - started) * 1000, 1))
    return {**result, "meta": meta}


@router.post("/validate")
def revalidate(body: POIn):
    """Re-run every check on the edited PO (called after inline edits)."""
    return _check(_clean(body))


@router.post("/email")
def email(body: POIn):
    result = _check(_clean(body))
    return clarification_email(result)


@router.post("/submit", status_code=201)
def submit(body: SubmitIn):
    """Create a pending order in the order queue. Refused while any error remains."""
    po = _clean(body)
    result = _check(po)
    if not result["can_submit"]:
        errors = [i["message"] for i in result["issues"] if i["level"] == "error"]
        raise HTTPException(status_code=409, detail="Fix before sending: " + "; ".join(errors[:4]) + (" …" if len(errors) > 4 else ""))

    from app.routers.orders import build_lines, log_status, with_validation  # avoid import cycle at load time

    by = body.created_by.strip()
    clean = result["po"]
    order = {
        "id": store.next_id("ord", store.orders["orders"]),
        "order_number": clean["po_number"], "type": "sales", "counterparty": clean["buyer"],
        "order_date": clean["order_date"], "delivery_date": clean["delivery_date"],
        "currency": clean["currency"] or "USD", "port": clean["port"], "buyer_email": clean["buyer_email"],
        "lines": build_lines(clean["lines"]), "status": "extracted",
        "source_file": f"PO intake · {body.source or 'manual'}", "created_by": by, "created_at": now_iso(),
    }
    order["total"] = round(sum(l["amount"] for l in order["lines"]), 2)
    order["transaction_id"] = transaction_id(order)
    log_status(order, "extracted", by, "PO intake")
    store.orders["orders"].append(order)
    documents.sync_csv()
    return {"order": with_validation(order)}

