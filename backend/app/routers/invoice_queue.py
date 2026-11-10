"""Spectra: Review Invoice Queue. Approved sales orders wait here until their invoice is generated."""
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import store
from app.services.invoice_generator import render_generated_invoice
from app.services.invoice_queue import now_iso, pdf_payload, queue_entry, with_totals

router = APIRouter(prefix="/api/invoice-queue", tags=["invoice queue (Spectra)"])

SELLER = "Spectra Pte Ltd"


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=300)
    email: str = Field(default="", max_length=120)


class ItemIn(BaseModel):
    sku: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=300)
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class InvoiceEdit(BaseModel):
    edited_by: str = Field(default="Administrator", min_length=1, max_length=80)
    invoice_number: str | None = Field(default=None, min_length=1, max_length=40)
    customer: CustomerIn | None = None
    issue_date: date | None = None
    tax_rate: float | None = Field(default=None, ge=0, le=1)
    items: list[ItemIn] | None = Field(default=None, min_length=1, max_length=100)


class GenerateIn(BaseModel):
    generated_by: str = Field(default="Administrator", min_length=1, max_length=80)


def find_invoiced_order(order_id: str) -> dict:
    order = next((o for o in store.orders["orders"] if o["id"] == order_id), None)
    if order is None or "invoice" not in order:
        raise HTTPException(status_code=404, detail="No invoice draft for this order")
    return order


def pending(order: dict) -> dict:
    if order["invoice"]["status"] != "pending":
        raise HTTPException(status_code=409, detail="Invoice was already generated")
    return order


@router.get("")
def list_queue(status: str | None = None):
    """Approved orders with an invoice draft. `status=pending` for those still awaiting generation."""
    return [queue_entry(o) for o in store.orders["orders"]
            if "invoice" in o and (status is None or o["invoice"]["status"] == status)]


@router.get("/{order_id}")
def get_entry(order_id: str):
    return queue_entry(find_invoiced_order(order_id))


@router.post("/recalculate")
def recalculate(body: InvoiceEdit):
    """Totals for unsaved edits, so the editor can preview without saving."""
    if body.items is None:
        raise HTTPException(status_code=422, detail="items are required")
    return with_totals({"items": [i.model_dump() for i in body.items], "tax_rate": body.tax_rate or 0})


@router.put("/{order_id}")
def edit_invoice(order_id: str, body: InvoiceEdit):
    """Edit the draft. Only sent fields change; totals are recomputed from the items."""
    order = pending(find_invoiced_order(order_id))
    inv = order["invoice"]
    full = body.model_dump(mode="json")  # nested defaults filled in
    changes = {k: full[k] for k in body.model_fields_set if k != "edited_by"}
    editor = body.edited_by.strip()
    if changes.get("items") is not None:
        changes["items"] = [{**i, "name": i["name"].strip(), "description": i["description"].strip(),
                             "sku": (i["sku"] or "").strip().upper() or None} for i in changes["items"]]
    if changes.get("customer") is not None:
        changes["customer"] = {k: v.strip() for k, v in changes["customer"].items()}
    changes = {k: v for k, v in changes.items() if v is not None}
    inv.update(changes)
    inv["updated_at"], inv["updated_by"] = now_iso(), editor
    return queue_entry(order)


@router.post("/{order_id}/generate")
def generate_invoice(order_id: str, body: GenerateIn | None = None):
    """Finalise the invoice. It leaves the pending queue and can no longer be edited."""
    body = body or GenerateIn()
    order = pending(find_invoiced_order(order_id))
    inv = order["invoice"]
    inv["status"] = "generated"
    inv["generated_at"], inv["generated_by"] = now_iso(), body.generated_by.strip()
    return queue_entry(order)


@router.get("/{order_id}/invoice.pdf")
def invoice_pdf(order_id: str):
    order = find_invoiced_order(order_id)
    if order["invoice"]["status"] != "generated":
        raise HTTPException(status_code=409, detail="Generate the invoice first")
    number = order["invoice"]["invoice_number"]
    return Response(
        render_generated_invoice(pdf_payload(order, SELLER)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{number}.pdf"'},
    )
