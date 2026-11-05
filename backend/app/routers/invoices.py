"""Koda: supplier invoices vs purchase orders."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response

from app import store
from app.ai.extractor import extract_invoice
from app.services.invoice_pdf import VARIANTS, invoice_from_po, render_invoice_pdf
from app.services import documents, supabase_store
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


def find_product(sku: str) -> tuple[dict, dict] | None:
    """(purchase order, line) for the first PO that lists this SKU."""
    for po in store.erp["purchase_orders"]:
        for line in po["lines"]:
            if line["sku"] == sku:
                return po, line
    return None


@router.get("/products")
def list_products():
    """Every product on a purchase order, for the invoice product dropdown."""
    return [
        {"sku": line["sku"], "description": line["description"], "unit_price": line["unit_price"],
         "ordered_qty": line["qty"], "supplier": po["supplier"], "currency": po["currency"], "po_number": po["po_number"]}
        for po in store.erp["purchase_orders"] for line in po["lines"]
    ]


@router.get("/products/{sku}/invoice.pdf")
def generate_product_invoice_pdf(sku: str, quantity: int | None = None, variant: str = "clean"):
    """Invoice PDF for one chosen product. Quantity defaults to what the PO ordered."""
    found = find_product(sku)
    if found is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if variant not in VARIANTS:
        raise HTTPException(status_code=422, detail=f"variant must be one of {', '.join(VARIANTS)}")
    if quantity is not None and quantity < 1:
        raise HTTPException(status_code=422, detail="quantity must be at least 1")
    po, line = found
    single = {**po, "lines": [{**line, "qty": quantity or line["qty"]}]}
    inv = invoice_from_po(single, variant)
    inv["invoice_number"] += f"-{sku}"  # distinct from the whole-PO invoice, so it is not flagged as a duplicate
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
    record = {k: draft[k] for k in INVOICE_FIELDS}
    saved, storage_error = False, None
    if supabase_store.enabled():  # keep the PDF and the row; a Supabase outage must not lose the upload
        path = None
        try:
            path = supabase_store.upload_file(draft["source_file"], content)
            record["file_path"] = path
            supabase_store.save_invoice(record, path)
            saved = True
        except Exception as exc:
            storage_error = str(exc)
            record.pop("file_path", None)
            if path:  # no row points at the file, so do not leave it orphaned
                try:
                    supabase_store.delete_file(path)
                except Exception:
                    pass
    store.erp["invoices"].append(record)
    documents.sync_csv()
    return {"draft": draft, "invoice": list_invoices()[-1], "saved": saved, "storage_error": storage_error}


@router.get("/invoices/{invoice_number}/file")
def open_invoice_file(invoice_number: str):
    """Redirects to a short-lived link for the uploaded PDF."""
    inv = next((i for i in store.erp["invoices"] if i["invoice_number"] == invoice_number), None)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not inv.get("file_path"):
        raise HTTPException(status_code=404, detail="No file was stored for this invoice")
    try:
        return RedirectResponse(supabase_store.signed_url(inv["file_path"]))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not open the file: {exc}")


@router.delete("/invoices/{invoice_number}", status_code=204)
def delete_invoice(invoice_number: str):
    invoices = store.erp["invoices"]
    match = next((i for i in invoices if i["invoice_number"] == invoice_number), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoices.remove(match)
    documents.sync_csv()
    if supabase_store.enabled() and (match.get("file_path") or match.get("source_file")):
        try:
            supabase_store.delete_invoice(invoice_number, match.get("file_path"))
        except Exception:
            pass  # the invoice is already gone from the queue; a stale row is reloaded as a duplicate at worst


@router.delete("/purchase-orders/{po_number}", status_code=204)
def delete_purchase_order(po_number: str):
    po = find_po(po_number)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    billed = [i["invoice_number"] for i in store.erp["invoices"] if i["po_number"] == po_number]
    if billed:
        raise HTTPException(status_code=409, detail=f"Delete invoice {', '.join(billed)} first")
    store.erp["purchase_orders"].remove(po)
    documents.sync_csv()
