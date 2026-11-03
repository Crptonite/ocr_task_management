"""Invoice extraction (OCR / LLM).

Owner: Lucas (OCR & AI). Step 1: read the PDF text layer and pull fields out with
regexes. Step 2: when that leaves fields missing (or there is no text layer, as with
scans and photos) and OPENAI_API_KEY is set, an OpenAI pass reads the document
instead (app.ai.llm). Keep the return shape the same so the matching engine and
frontend keep working.
"""
import io
import re
from datetime import datetime

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ai import llm

REQUIRED = ("invoice_number", "po_number", "supplier", "invoice_date", "currency", "lines")

FIELD_PATTERNS = {
    "invoice_number": r"Invoice\s*(?:No\.?|Number|#)\s*:?\s*([A-Z0-9][A-Z0-9-]+)",
    "invoice_date": r"Invoice\s*Date\s*:?\s*(\d{4}-\d{2}-\d{2})",
    "po_number": r"(?:PO\s*(?:Reference|Ref\.?|Number|No\.?)|Purchase\s*Order)\s*:?\s*(PO-[A-Z0-9-]+)",
    "currency": r"Currency\s*:?\s*([A-Z]{3})\b",
}
# SKU, description, qty, unit price, amount: one table row per text line.
LINE_PATTERN = re.compile(r"^([A-Z0-9][A-Z0-9-]{2,})\s+(.+?)\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$")
TAX_PATTERN = re.compile(r"(?:GST|VAT|Tax)\s*\((\d+(?:\.\d+)?)%\)\s*:?\s*([\d,]+\.\d{2})")


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def pdf_text(content: bytes) -> str | None:
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError):
        return None


def parse_invoice_text(text: str) -> dict:
    fields: dict = {}
    for key, pattern in FIELD_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        fields[key] = m.group(1).strip() if m else None

    rows = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fields["supplier"] = rows[0] if rows else None  # letterhead is the first line

    fields["lines"] = []
    for row in rows:
        m = LINE_PATTERN.match(row)
        if m:
            sku, desc, qty, unit, _amount = m.groups()
            fields["lines"].append({"sku": sku, "description": desc, "qty": int(qty), "unit_price": _num(unit)})

    tax = TAX_PATTERN.search(text)
    fields["tax_rate"] = round(float(tax.group(1)) / 100, 4) if tax else 0.0
    fields["tax_amount"] = _num(tax.group(2)) if tax else 0.0
    return fields


def _try_llm(read, filename: str, content: bytes) -> tuple[dict | None, str | None]:
    """(fields, None) on success; (None, reason) when the LLM is off or the call failed."""
    if not llm.llm_enabled():
        return None, None
    try:
        return read(filename, content), None
    except Exception as exc:  # network, auth, quota, unreadable file: keep the regex result
        return None, f"OpenAI read failed ({type(exc).__name__})"


def extract_invoice(filename: str, content: bytes) -> dict:
    draft = {
        "invoice_number": None,
        "po_number": None,
        "supplier": None,
        "invoice_date": None,
        "currency": None,
        "tax_rate": 0.0,
        "tax_amount": 0.0,
        "lines": [],
        "source_file": filename,
        "size_bytes": len(content),
    }
    text = pdf_text(content) if content.startswith(b"%PDF") else None
    has_text = bool(text and text.strip())
    if has_text:
        draft.update(parse_invoice_text(text))
    source = "PDF text layer"
    problem = None

    if not has_text or any(not draft[k] for k in REQUIRED):
        fields, problem = _try_llm(llm.read_invoice, filename, content)
        if fields is not None:
            draft.update(fields)
            source = "OpenAI"

    if not has_text and source != "OpenAI":
        return {**draft, "confidence": 0.0, "missing": list(REQUIRED),
                "note": problem or "No text layer found (scan or image). Set OPENAI_API_KEY to read these."}

    missing = [k for k in REQUIRED if not draft[k]]
    note = f"Read by {source}" if source == "OpenAI" else "Read from PDF text layer"
    return {
        **draft,
        "confidence": round((len(REQUIRED) - len(missing)) / len(REQUIRED), 2),
        "missing": missing,
        "note": note + (f"; missing {', '.join(missing)}" if missing else "") + (f"; {problem}" if problem else ""),
    }


ORDER_FIELD_PATTERNS = {
    "order_number": r"(?:Purchase\s*Order|PO|Order)\s*(?:No\.?|Number|#)\s*:?\s*([A-Z0-9][A-Z0-9-]+)",
    "order_date": r"Order\s*Date\s*:?\s*([^\n]+)",
    "delivery_date": r"(?:Delivery|Required|Due)\s*(?:Date|By)\s*:?\s*([^\n]+)",
    "currency": r"Currency\s*:?\s*([A-Z]{3})\b",
}
TOTAL_PATTERN = re.compile(r"^(?:Grand\s*)?Total\s*(?:\([A-Z]{3}\))?\s*:?\s*([\d,]+\.\d{2})$", re.IGNORECASE | re.MULTILINE)
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")
ORDER_REQUIRED = ("order_number", "counterparty", "order_date", "delivery_date", "lines")


def normalize_date(raw: str | None) -> str | None:
    """Return an ISO date, or None when the text is not a date we recognise."""
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_order_text(text: str) -> dict:
    fields: dict = {}
    for key, pattern in ORDER_FIELD_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        fields[key] = m.group(1).strip() if m else None
    fields["order_date"] = normalize_date(fields["order_date"])
    fields["delivery_date"] = normalize_date(fields["delivery_date"])

    rows = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fields["counterparty"] = rows[0] if rows else None  # the customer's letterhead is the first line

    fields["lines"] = []
    for row in rows:
        m = LINE_PATTERN.match(row)
        if m:
            sku, desc, qty, unit, amount = m.groups()
            fields["lines"].append(
                {"sku": sku, "description": desc, "quantity": int(qty), "unit_price": _num(unit), "amount": _num(amount)}
            )
    total = TOTAL_PATTERN.search(text)
    fields["total"] = _num(total.group(1)) if total else None
    return fields


def extract_order(filename: str, content: bytes) -> dict:
    """Customer PO -> the order schema used by app.services.orders.validate_order."""
    draft = {
        "order_number": None,
        "type": "sales",  # a customer PO is a sales order from Koda's side
        "counterparty": None,
        "order_date": None,
        "delivery_date": None,
        "currency": None,
        "total": None,
        "lines": [],
        "source_file": filename,
        "size_bytes": len(content),
    }
    text = pdf_text(content) if content.startswith(b"%PDF") else None
    has_text = bool(text and text.strip())
    if has_text:
        draft.update(parse_order_text(text))
    source = "PDF text layer"
    problem = None

    if not has_text or any(not draft[k] for k in ORDER_REQUIRED):
        fields, problem = _try_llm(llm.read_order, filename, content)
        if fields is not None:
            draft.update(fields)
            draft["order_date"] = normalize_date(draft["order_date"])
            draft["delivery_date"] = normalize_date(draft["delivery_date"])
            source = "OpenAI"

    if not has_text and source != "OpenAI":
        return {**draft, "confidence": 0.0, "missing": list(ORDER_REQUIRED),
                "note": problem or "No text layer found (scan or image). Set OPENAI_API_KEY to read these."}

    missing = [k for k in ORDER_REQUIRED if not draft[k]]
    note = f"Read by {source}" if source == "OpenAI" else "Read from PDF text layer"
    return {
        **draft,
        "confidence": round((len(ORDER_REQUIRED) - len(missing)) / len(ORDER_REQUIRED), 2),
        "missing": missing,
        "note": note + (f"; missing {', '.join(missing)}" if missing else "") + (f"; {problem}" if problem else ""),
    }
