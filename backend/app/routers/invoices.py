"""Koda: supplier invoices vs purchase orders."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app import store
from app.ai.extractor import extract_invoice
from app.services.invoice_pdf import VARIANTS, invoice_from_po, render_invoice_pdf
from app.services.matching import match_invoice

router = APIRouter(prefix="/api", tags=["invoices (Koda)"])


def find_po(po_number: str | None) -> dict | None:
    return next((po for po in store.erp["purchase_orders"] if po["po_number"] == po_number), None)


@router.get("/purchase-orders")
def list_purchase_orders():
    return store.erp["purchase_orders"]


@router.get("/invoices")
def list_invoices():
    results, seen = [], set()
    for inv in store.erp["invoices"]:
        result = match_invoice(inv, find_po(inv["po_number"]), seen)
        seen.add(inv["invoice_number"])
        total = result.get("subtotal", 0) + inv.get("tax_amount", 0)
        results.append({**inv, "total": round(total, 2), "match": result})
    return results


@router.get("/invoices/{invoice_number}")
def get_invoice(invoice_number: str):
    for inv in list_invoices():
        if inv["invoice_number"] == invoice_number:
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")


@router.get("/invoice-variants")
def list_invoice_variants():
    return VARIANTS


@router.get("/purchase-orders/{po_number}/invoice.pdf")
def generate_invoice_pdf(po_number: str, variant: str = "clean"):
    """A supplier-style invoice PDF for this PO, for testing the upload flow."""
    po = find_po(po_number)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if variant not in VARIANTS:
        raise HTTPException(status_code=422, detail=f"variant must be one of {', '.join(VARIANTS)}")
    inv = invoice_from_po(po, variant)
    return Response(
        render_invoice_pdf(inv),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}.pdf"'},
    )


INVOICE_FIELDS = ("invoice_number", "po_number", "supplier", "invoice_date", "currency", "tax_rate", "tax_amount", "lines", "source_file")


@router.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...)):
    """Extract the file. If every required field was read, the invoice joins the review queue."""
    content = await file.read()
    draft = extract_invoice(file.filename or "upload", content)
    if draft["confidence"] < 1:
        return {"draft": draft, "invoice": None}
    store.erp["invoices"].append({k: draft[k] for k in INVOICE_FIELDS})
    return {"draft": draft, "invoice": list_invoices()[-1]}
