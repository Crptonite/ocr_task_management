import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.ai.extractor import extract_invoice
from app.services.matching import match_invoice

DATA_FILE = Path(__file__).parent / "data" / "mock_erp.json"
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Koda Invoice Check API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def load_data() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def find_po(data: dict, po_number: str | None) -> dict | None:
    return next((po for po in data["purchase_orders"] if po["po_number"] == po_number), None)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/purchase-orders")
def list_purchase_orders():
    return load_data()["purchase_orders"]


@app.get("/api/invoices")
def list_invoices():
    data = load_data()
    results, seen = [], set()
    for inv in data["invoices"]:
        result = match_invoice(inv, find_po(data, inv["po_number"]), seen)
        seen.add(inv["invoice_number"])
        total = result.get("subtotal", 0) + inv.get("tax_amount", 0)
        results.append({**inv, "total": round(total, 2), "match": result})
    return results


@app.get("/api/invoices/{invoice_number}")
def get_invoice(invoice_number: str):
    for inv in list_invoices():
        if inv["invoice_number"] == invoice_number:
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")


@app.post("/api/invoices/upload")
async def upload_invoice(file: UploadFile = File(...)):
    content = await file.read()
    return {"draft": extract_invoice(file.filename or "upload", content)}


# Serve the static frontend at / (keep this last so /api routes win).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

