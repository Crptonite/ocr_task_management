"""OpenAI document reading for invoices and customer POs.

Owner: Lucas (OCR & AI). Used when the PDF text layer is missing or the regexes
could not read every required field (scans, photos, unfamiliar supplier layouts).
Without OPENAI_API_KEY nothing here runs and the regex extractor is used alone.
"""
import base64
import os
from pathlib import Path

from pydantic import BaseModel

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

INVOICE_PROMPT = (
    "You extract data from supplier invoices for an accounts-payable team. Copy values exactly as printed; "
    "use null for anything not on the document. Never invent line items. Dates are YYYY-MM-DD, "
    "currency is an ISO 4217 code, tax_rate is a fraction (0.09 for 9%)."
)
ORDER_PROMPT = (
    "You extract customer purchase orders for ERP data entry. Copy values exactly as printed; "
    "use null for anything not on the document. Never invent line items. Dates are YYYY-MM-DD, "
    "currency is an ISO 4217 code. counterparty is the customer who placed the order."
)


class InvoiceLine(BaseModel):
    sku: str | None
    description: str | None
    qty: float
    unit_price: float


class InvoiceRead(BaseModel):
    invoice_number: str | None
    po_number: str | None
    supplier: str | None
    invoice_date: str | None
    currency: str | None
    tax_rate: float | None
    tax_amount: float | None
    lines: list[InvoiceLine]


class OrderLine(BaseModel):
    sku: str | None
    description: str | None
    quantity: float
    unit_price: float
    amount: float


class OrderRead(BaseModel):
    order_number: str | None
    counterparty: str | None
    order_date: str | None
    delivery_date: str | None
    currency: str | None
    total: float | None
    lines: list[OrderLine]


def api_key() -> str | None:
    """OPENAI_API_KEY from the environment, else from backend/.env (only that one key is read)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key and ENV_FILE.exists():
        try:
            from dotenv import dotenv_values

            key = dotenv_values(ENV_FILE).get("OPENAI_API_KEY")
        except ImportError:
            pass
    return key.strip() or None if key else None


def llm_enabled() -> bool:
    return api_key() is not None


def _document_block(content: bytes, filename: str) -> dict:
    if content.startswith(b"%PDF"):
        data_url = "data:application/pdf;base64," + base64.b64encode(content).decode()
        return {"type": "input_file", "filename": filename or "document.pdf", "file_data": data_url}
    mime = "image/jpeg" if content[:3] == b"\xff\xd8\xff" else "image/png"
    return {"type": "input_image", "image_url": f"data:{mime};base64," + base64.b64encode(content).decode(), "detail": "high"}


def read_document(prompt: str, schema: type[BaseModel], filename: str, content: bytes) -> BaseModel:
    """One structured-output call. Tests replace this function; raises on any API problem."""
    from openai import OpenAI

    response = OpenAI(api_key=api_key()).responses.parse(
        model=MODEL,
        instructions=prompt,
        input=[{"role": "user", "content": [_document_block(content, filename), {"type": "input_text", "text": "Extract this document."}]}],
        text_format=schema,
    )
    if response.output_parsed is None:
        raise ValueError("The model returned an unreadable result")
    return response.output_parsed


def _whole(n: float) -> float | int:
    return int(n) if float(n).is_integer() else n


def read_invoice(filename: str, content: bytes) -> dict:
    """Fields in the shape parse_invoice_text returns."""
    r = read_document(INVOICE_PROMPT, InvoiceRead, filename, content)
    return {
        "invoice_number": r.invoice_number,
        "po_number": r.po_number,
        "supplier": r.supplier,
        "invoice_date": r.invoice_date,
        "currency": r.currency,
        "tax_rate": r.tax_rate or 0.0,
        "tax_amount": r.tax_amount or 0.0,
        "lines": [
            {"sku": l.sku, "description": l.description, "qty": _whole(l.qty), "unit_price": l.unit_price}
            for l in r.lines
        ],
    }


def read_order(filename: str, content: bytes) -> dict:
    """Fields in the shape parse_order_text returns."""
    r = read_document(ORDER_PROMPT, OrderRead, filename, content)
    return {
        "order_number": r.order_number,
        "counterparty": r.counterparty,
        "order_date": r.order_date,
        "delivery_date": r.delivery_date,
        "currency": r.currency,
        "total": r.total,
        "lines": [
            {"sku": l.sku, "description": l.description, "quantity": _whole(l.quantity),
             "unit_price": l.unit_price, "amount": l.amount}
            for l in r.lines
        ],
    }
