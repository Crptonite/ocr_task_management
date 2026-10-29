"""Spectra: purchase / sales order extraction, validation, approval and export."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app import store
from app.ai.extractor import extract_order
from app.services.orders import orders_to_csv, validate_order

router = APIRouter(prefix="/api", tags=["orders (Spectra)"])


def with_validation(order: dict) -> dict:
    return {**order, "validation": validate_order(order, store.orders["catalog"])}


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


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: str):
    order = find_order(order_id)
    if order["status"] != "extracted":
        raise HTTPException(status_code=409, detail=f"Order is already {order['status']}")
    validation = validate_order(order, store.orders["catalog"])
    if validation["status"] != "ready":
        raise HTTPException(status_code=409, detail="Fix validation issues before approving")
    order["status"] = "approved"
    return with_validation(order)


@router.post("/orders/upload")
async def upload_order(file: UploadFile = File(...)):
    content = await file.read()
    return {"draft": extract_order(file.filename or "upload", content)}
