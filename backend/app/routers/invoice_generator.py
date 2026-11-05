"""Invoice generator: build an invoice PDF from typed-in details (clone of easyinvoicepdf)."""
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.invoice_generator import invoice_totals, render_generated_invoice

router = APIRouter(prefix="/api/invoice-generator", tags=["invoice generator"])


class ItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class InvoiceIn(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=40)
    seller: str = Field(min_length=1, max_length=120)
    buyer: str = Field(min_length=1, max_length=120)
    issue_date: date
    service_date: date
    payment_method: str = "Wire transfer"
    payment_date: date
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    gst_rate: float = Field(default=0.09, ge=0, le=1)
    items: list[ItemIn] = Field(min_length=1, max_length=100)


@router.get("/defaults")
def defaults():
    return {
        "invoice_number": "PO-2026-0141",
        "seller": "Hafele Hardware Asia",
        "buyer": "Buyer name",
        "issue_date": "2026-10-23",
        "service_date": "2026-10-31",
        "payment_method": "Wire transfer",
        "payment_date": "2026-11-06",
        "currency": "SGD",
        "gst_rate": 0.09,
        "items": [{"description": "", "quantity": 1, "unit_price": 0}],
    }


@router.post("/totals")
def totals(body: InvoiceIn):
    return invoice_totals([i.model_dump() for i in body.items], body.gst_rate)


@router.post("/pdf")
def pdf(body: InvoiceIn):
    data = body.model_dump(mode="json")
    return Response(
        render_generated_invoice(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{body.invoice_number}.pdf"'},
    )
