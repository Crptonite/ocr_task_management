"""Spectra: purchase / sales order extraction, validation, approval and export."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import store
from app.ai.extractor import extract_order
from app.services.invoice_queue import new_invoice_draft, now_iso, transaction_id
from app.services.orders import koda_entry, orders_to_csv, validate_order

router = APIRouter(prefix="/api", tags=["orders (Spectra)"])


class LineIn(BaseModel):
    sku: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=200)  # the item name
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class OrderPatch(BaseModel):
    order_number: str | None = None
    counterparty: str | None = None
    order_date: date | None = None
    delivery_date: date | None = None
    currency: str | None = None
    type: Literal["sales", "purchase"] | None = None
    lines: list[LineIn] | None = Field(default=None, min_length=1, max_length=200)
    # Status change, applied after the edits. "extracted" (pending) reopens an approved or rejected order.
    status: Literal["extracted", "approved", "rejected"] | None = None
    updated_by: str = Field(default="Administrator", min_length=1, max_length=80)
    reason: str = Field(default="", max_length=500)


class OrderCreate(BaseModel):
    order_number: str = Field(min_length=1, max_length=40)
    type: Literal["sales", "purchase"] = "sales"
    counterparty: str = Field(min_length=1, max_length=120)
    order_date: date
    delivery_date: date | None = None
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    lines: list[LineIn] = Field(min_length=1, max_length=200)
    created_by: str = Field(default="Administrator", min_length=1, max_length=80)


class ApproveIn(BaseModel):
    approved_by: str = Field(default="Administrator", min_length=1, max_length=80)


class RejectIn(BaseModel):
    rejected_by: str = Field(default="Administrator", min_length=1, max_length=80)
    reason: str = Field(default="", max_length=500)


def with_validation(order: dict) -> dict:
    return {**order, "validation": validate_order(order, store.orders["catalog"], store.orders["orders"])}


def find_order(order_id: str) -> dict:
    order = next((o for o in store.orders["orders"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/catalog")
def list_catalog():
    return store.orders["catalog"]


@router.get("/orders")
def list_orders():
    return [with_validation(o) for o in store.orders["orders"]]


# Declared before /orders/{order_id} so "export.csv" is not read as an id.
@router.get("/orders/export.csv")
def export_orders():
    """Approved orders as CSV for ERP import. Exported orders are marked so they are not sent twice."""
    approved = [o for o in store.orders["orders"] if o["status"] == "approved"]
    csv_text = orders_to_csv(approved)
    for order in approved:
        order["status"] = "exported"
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="orders_export.csv"'},
    )


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    return with_validation(find_order(order_id))


@router.get("/orders/{order_id}/koda-entry")
def get_koda_entry(order_id: str):
    return koda_entry(find_order(order_id), store.orders["catalog"])


def log_status(order: dict, status: str, by: str, note: str = "") -> None:
    order.setdefault("status_history", []).append(
        {"status": status, "by": by, "at": now_iso(), **({"note": note} if note else {})})


def do_approve(order: dict, by: str) -> None:
    if order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    validation = validate_order(order, store.orders["catalog"], store.orders["orders"])
    if validation["status"] != "ready":
        raise HTTPException(status_code=409, detail="Fix validation issues before approving")
    order["status"] = "approved"
    order["approval"] = {"decision": "approved", "by": by, "at": now_iso()}
    order["invoice"] = new_invoice_draft(order, store.orders["catalog"])  # joins the Review Invoice Queue
    log_status(order, "approved", by)


def do_reject(order: dict, by: str, reason: str) -> None:
    if order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    order["status"] = "rejected"
    order["approval"] = {"decision": "rejected", "by": by, "at": now_iso(), "reason": reason}
    log_status(order, "rejected", by, reason)


def do_reopen(order: dict, by: str) -> None:
    """Back to pending so it can be edited. Not once its invoice is generated or it was exported."""
    if order["status"] == "extracted":
        return
    if order["status"] == "exported":
        raise HTTPException(status_code=409, detail="Order was already exported to the ERP")
    if order.get("invoice", {}).get("status") == "generated":
        raise HTTPException(status_code=409, detail="Its invoice was already generated")
    order["status"] = "extracted"
    order.pop("approval", None)
    order.pop("invoice", None)  # a fresh draft is made from the edited lines on re-approval
    log_status(order, "extracted", by, "reopened")


def build_lines(lines: list[dict]) -> list[dict]:
    """Amounts are always qty × price. A blank SKU is filled in when the item name matches the catalogue."""
    by_name = {item["name"].strip().lower(): item["sku"] for item in store.orders["catalog"]}
    out = []
    for l in lines:
        name = (l.get("description") or "").strip()
        sku = (l.get("sku") or "").strip().upper() or by_name.get(name.lower())
        qty = int(l["quantity"]) if float(l["quantity"]).is_integer() else l["quantity"]
        out.append({"sku": sku, "description": name, "quantity": qty, "unit_price": l["unit_price"],
                    "amount": round(l["quantity"] * l["unit_price"], 2)})
    return out


@router.post("/orders", status_code=201)
def create_order(body: OrderCreate):
    """Key in an order by hand. It joins the order queue as pending, like an uploaded one."""
    data = body.model_dump(mode="json")
    by = data.pop("created_by").strip()
    order = {"id": store.next_id("ord", store.orders["orders"]),
             **{k: v.strip() if isinstance(v, str) else v for k, v in data.items() if k != "lines"},
             "currency": data["currency"].upper(), "lines": build_lines(data["lines"]),
             "status": "extracted", "source_file": "manual entry", "created_by": by, "created_at": now_iso()}
    order["total"] = round(sum(l["amount"] for l in order["lines"]), 2)
    order["transaction_id"] = transaction_id(order)
    log_status(order, "extracted", by, "created")
    store.orders["orders"].append(order)
    return with_validation(order)


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: str, body: ApproveIn | None = None):
    """Approve the transaction; the order then joins the Review Invoice Queue."""
    body = body or ApproveIn()
    order = find_order(order_id)
    do_approve(order, body.approved_by.strip())
    return with_validation(order)


@router.post("/orders/{order_id}/reject")
def reject_order(order_id: str, body: RejectIn | None = None):
    """Reject the transaction. It stays on file but is never invoiced or exported."""
    body = body or RejectIn()
    order = find_order(order_id)
    do_reject(order, body.rejected_by.strip(), body.reason.strip())
    return with_validation(order)


@router.patch("/orders/{order_id}")
def update_order(order_id: str, body: OrderPatch):
    """Edit the existing record in place. Amounts and total are recomputed from the lines.

    Fields can only change while the order is pending; send status "extracted" in the same request
    to reopen an approved or rejected order first. A new status is applied after the edits.
    """
    order = find_order(order_id)
    changes = body.model_dump(exclude_unset=True)
    status = changes.pop("status", None)
    by = changes.pop("updated_by", body.updated_by).strip()
    reason = changes.pop("reason", "").strip()
    if status == "extracted":
        do_reopen(order, by)
    if changes and order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    # Validate everything before touching the record, so a rejected status change leaves no half-edit.
    if status == "approved":
        preview = {**order, **{k: v.isoformat() if isinstance(v, date) else v for k, v in changes.items()}}
        if "lines" in changes:
            preview["lines"] = build_lines(changes["lines"])
            preview["total"] = round(sum(l["amount"] for l in preview["lines"]), 2)
        others = [o for o in store.orders["orders"] if o is not order]
        if validate_order(preview, store.orders["catalog"], others)["status"] != "ready":
            raise HTTPException(status_code=409, detail="Fix validation issues before approving")
    lines = changes.pop("lines", None)
    for key, value in changes.items():
        if isinstance(value, date):
            value = value.isoformat()
        order[key] = value.strip() if isinstance(value, str) and value.strip() else (None if value in ("", None) else value)
    if lines is not None:
        order["lines"] = build_lines(lines)
        order["total"] = round(sum(l["amount"] for l in order["lines"]), 2)
    if changes or lines is not None:
        order["updated_by"], order["updated_at"] = by, now_iso()
    if status == "approved":
        do_approve(order, by)
    elif status == "rejected":
        do_reject(order, by, reason)
    return with_validation(order)


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: str):
    store.orders["orders"].remove(find_order(order_id))


@router.post("/orders/upload")
async def upload_order(file: UploadFile = File(...)):
    content = await file.read()
    draft = extract_order(file.filename or "upload", content)
    validation = validate_order(draft, store.orders["catalog"], store.orders["orders"])
    if draft["confidence"] == 0:  # nothing was read: do not queue an empty order
        return {"draft": draft, "validation": validation, "order": None}
    order = {"id": store.next_id("ord", store.orders["orders"]), **draft, "status": "extracted"}
    order["transaction_id"] = transaction_id(order)
    store.orders["orders"].append(order)
    return {"draft": draft, "validation": validation, "order": with_validation(order)}
