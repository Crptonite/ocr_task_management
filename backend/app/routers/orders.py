"""Spectra: purchase / sales order extraction, validation, approval and export."""
from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import store
from app.ai.extractor import extract_order
from app.services.orders import koda_entry, orders_to_csv, validate_order

router = APIRouter(prefix="/api", tags=["orders (Spectra)"])


class LineIn(BaseModel):
    sku: str | None = None
    description: str | None = None
    quantity: float
    unit_price: float


class OrderPatch(BaseModel):
    order_number: str | None = None
    counterparty: str | None = None
    order_date: date | None = None
    delivery_date: date | None = None
    currency: str | None = None
    lines: list[LineIn] | None = None


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


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: str):
    order = find_order(order_id)
    if order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    validation = validate_order(order, store.orders["catalog"], store.orders["orders"])
    if validation["status"] != "ready":
        raise HTTPException(status_code=409, detail="Fix validation issues before approving")
    order["status"] = "approved"
    return with_validation(order)


@router.patch("/orders/{order_id}")
def update_order(order_id: str, body: OrderPatch):
    """Correct what the extractor got wrong. Amounts and total are recomputed from the lines."""
    order = find_order(order_id)
    if order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    changes = body.model_dump(exclude_unset=True)
    lines = changes.pop("lines", None)
    for key, value in changes.items():
        if isinstance(value, date):
            value = value.isoformat()
        order[key] = value.strip() if isinstance(value, str) and value.strip() else (None if value in ("", None) else value)
    if lines is not None:
        order["lines"] = [
            {**l, "quantity": int(l["quantity"]) if float(l["quantity"]).is_integer() else l["quantity"], "sku": (l["sku"] or "").strip().upper() or None, "description": l["description"] or "",
             "amount": round(l["quantity"] * l["unit_price"], 2)}
            for l in lines
        ]
        order["total"] = round(sum(l["amount"] for l in order["lines"]), 2)
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
    store.orders["orders"].append(order)
    return {"draft": draft, "validation": validation, "order": with_validation(order)}
