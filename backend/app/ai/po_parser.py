"""Hybrid customer-PO parser for 6a PO Intake.

Owner: Aeric (6a Part 1). Rules first, AI only when the rules come up short:

1. CSV exports and "Label: value" text are parsed deterministically (no tokens, ~1 ms).
2. PDFs with a text layer go through the same rules.
3. Only scans/photos, or text where the rules found no line items or too few header
   fields, are sent to the LLM (OPENAI_API_KEY). Without a key the rules result is kept
   and the response says why, so the user knows to fill the gaps by hand.
"""
import csv
import io
import re
from datetime import datetime

from pydantic import BaseModel

from app.ai import llm
from app.ai.extractor import pdf_text

HEADER_FIELDS = ("po_number", "buyer", "port", "order_date", "delivery_date")
PLACEHOLDERS = {"", "-", "--", "n/a", "na", "tbc", "tba", "tbd", "none", "null", "?", "pending"}

LABELS = {
    "po_number": r"(?:customer\s*)?(?:p\.?\s?o\.?|purchase\s*order)\s*(?:no\.?|number|num|ref(?:erence)?|#)?",
    "buyer": r"(?:buyer|customer|bill\s*to|sold\s*to|company|from)",
    "buyer_email": r"(?:buyer\s*)?e-?mail",
    "port": r"(?:port\s*of\s*(?:destination|discharge|delivery|entry)|destination\s*port|discharge\s*port|port|pod)",
    "order_date": r"(?:order|po|issue|issued)\s*date|date\s*issued|date",
    "delivery_date": r"(?:(?:requested\s*)?(?:delivery|ship(?:ment|ping)?|required|due|ex-?factory|etd|eta)\s*(?:date|by)?)",
    "currency": r"currency",
}
LABEL_LINE = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z .#/-]{1,40}?)\s*[:=]\s*(?P<value>.*)$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
SKU = r"[A-Z]{2,}[A-Z0-9]*(?:-[A-Z0-9]+)+"
SKU_TOKEN = re.compile(rf"^{SKU}$")
NUM = r"\d[\d,]*(?:\.\d+)?"
# "KD-CH-2047  Ashby oak dining chair  120  145.00  17400.00" (whitespace table / PDF text)
WS_ROW = re.compile(rf"^(?P<sku>{SKU})\s+(?P<desc>.+?)\s+(?P<qty>\d+)\s*(?:pcs|units|ea|sets)?\s+"
                    rf"(?:[A-Z]{{3}}\s*)?\$?(?P<price>{NUM})(?:\s+\$?(?P<amount>{NUM}))?$", re.IGNORECASE)
# "40 x KD-LC-7105 lounge chairs at USD 540" (emails, free text)
LOOSE_ROW = re.compile(rf"(?P<qty>\d+)\s*(?:x|pcs|units|nos|sets)?\s+(?:of\s+)?(?P<sku>{SKU})\b(?P<desc>[^@\n]*?)"
                       rf"\s*(?:@|at)\s*(?:[A-Z]{{3}}|\$)?\s*(?P<price>{NUM})", re.IGNORECASE)
CURRENCY = re.compile(r"\b(USD|SGD|EUR|GBP|AUD|MYR|VND|CNY|JPY)\b")
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
                "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d %b, %Y", "%b %d, %Y", "%B %d, %Y")

AI_PROMPT = (
    "You extract customer purchase orders for a furniture manufacturer's order desk. Copy values exactly "
    "as written; use null for anything not stated (never guess a port or date). Dates are YYYY-MM-DD, "
    "currency is an ISO 4217 code. buyer is the customer company placing the order. port is the port of "
    "destination / discharge. Never invent line items."
)


class AILine(BaseModel):
    sku: str | None
    description: str | None
    quantity: float | None
    unit_price: float | None


class AIRead(BaseModel):
    po_number: str | None
    buyer: str | None
    buyer_email: str | None
    port: str | None
    order_date: str | None
    delivery_date: str | None
    currency: str | None
    lines: list[AILine]


def empty_po() -> dict:
    return {"po_number": None, "buyer": None, "buyer_email": None, "port": None, "order_date": None,
            "delivery_date": None, "currency": None, "lines": []}


def clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip(",;").strip()
    return None if text.lower() in PLACEHOLDERS else text


def normalize_date(raw) -> str | None:
    text = clean(raw)
    if not text:
        return None
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text).replace(",", ", ").replace("  ", " ").strip()
    for candidate in (text, text.replace(", ", " ")):
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _num(raw) -> float | None:
    try:
        return float(str(raw).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _which_label(label: str) -> str | None:
    label = label.strip().lower()
    # delivery before order_date: "Delivery Date" must not be read as a plain "Date".
    for key in ("buyer_email", "delivery_date", "port", "po_number", "order_date", "currency", "buyer"):
        if re.fullmatch(LABELS[key], label, re.IGNORECASE):
            return key
    return None


def _line(sku, desc, qty, price, amount=None) -> dict:
    q, p = _num(qty), _num(price)
    return {"sku": clean(sku), "description": clean(desc), "quantity": q, "unit_price": p,
            "amount": _num(amount) if amount not in (None, "") else (round(q * p, 2) if q is not None and p is not None else None)}


def _split_row(row: str) -> list[str] | None:
    for sep in ("|", "\t", ";"):
        if row.count(sep) >= 2:
            return [c.strip() for c in row.strip(sep + " ").split(sep)]
    return None


def _row_to_line(cells: list[str]) -> dict | None:
    cells = [c for c in cells if c != ""]
    if len(cells) < 3 or not SKU_TOKEN.match(cells[0].upper()):
        return None
    numbers = [c for c in cells[1:] if _num(c) is not None]
    words = [c for c in cells[1:] if _num(c) is None]
    if len(numbers) < 2:
        return None
    qty, price = numbers[0], numbers[1]
    amount = numbers[2] if len(numbers) > 2 else None
    return _line(cells[0].upper(), " ".join(words) or None, qty, price, amount)


def parse_text(text: str) -> dict:
    """'Label: value' headers plus table rows (pipe/tab/whitespace) or loose 'qty x SKU @ price' mentions."""
    po = empty_po()
    rows = [ln.rstrip() for ln in text.splitlines()]
    for row in rows:
        m = LABEL_LINE.match(row)
        if not m:
            continue
        key = _which_label(m.group("label"))
        if key and po.get(key) is None:
            po[key] = clean(m.group("value"))
            if key == "buyer_email":
                found = EMAIL.search(m.group("value"))
                po[key] = found.group(0) if found else None

    for row in rows:
        stripped = row.strip()
        if not stripped:
            continue
        cells = _split_row(stripped)
        line = _row_to_line(cells) if cells else None
        if line is None:
            m = WS_ROW.match(stripped)
            if m:
                line = _line(m["sku"].upper(), m["desc"], m["qty"], m["price"], m["amount"])
        if line:
            po["lines"].append(line)

    if not po["lines"]:
        for m in LOOSE_ROW.finditer(text):
            po["lines"].append(_line(m["sku"].upper(), m["desc"].strip(" -,") or None, m["qty"], m["price"]))

    if not po["buyer_email"]:
        found = EMAIL.search(text)
        po["buyer_email"] = found.group(0) if found else None
    if not po["currency"]:
        found = CURRENCY.search(text)
        po["currency"] = found.group(1) if found else None
    if not po["buyer"]:
        first = next((r.strip() for r in rows if r.strip() and not LABEL_LINE.match(r) and not _split_row(r.strip())), None)
        if first and len(first) <= 80 and not re.match(r"^(hi|hello|dear)\b", first, re.IGNORECASE):
            po["buyer"] = re.split(r"\s+[—–-]\s+", first)[0].strip()
    return po


def looks_like_csv(text: str) -> bool:
    head = "\n".join(text.strip().splitlines()[:30]).lower()
    return head.count(",") >= 4 and "sku" in head and not _split_row(head.splitlines()[0])


def parse_csv(text: str) -> dict:
    """Metadata rows ('PO Number,PB-1') followed by a table whose header row contains 'sku'."""
    po = empty_po()
    rows = list(csv.reader(io.StringIO(text.strip())))
    header_idx = next((i for i, r in enumerate(rows) if any(c.strip().lower() in ("sku", "item code", "item no") for c in r)), None)
    for r in rows[: header_idx if header_idx is not None else len(rows)]:
        if len(r) >= 2:
            key = _which_label(r[0])
            if key:
                po[key] = clean(r[1])
    if header_idx is None:
        return po
    cols = [c.strip().lower() for c in rows[header_idx]]

    def col(*names):
        return next((cols.index(n) for n in names if n in cols), None)

    i_sku, i_desc = col("sku", "item code", "item no"), col("description", "item", "product", "name")
    i_qty, i_price = col("qty", "quantity", "units"), col("unit price", "unit_price", "price", "unit cost")
    i_amt = col("amount", "total", "line total")
    for r in rows[header_idx + 1:]:
        if not any(c.strip() for c in r):
            continue
        get = lambda i: r[i].strip() if i is not None and i < len(r) else None
        if not (get(i_sku) or get(i_desc)):
            continue
        po["lines"].append(_line((get(i_sku) or "").upper() or None, get(i_desc), get(i_qty), get(i_price), get(i_amt)))
    return po


def _ai_read(filename: str, content: bytes | None, text: str | None) -> dict:
    """One structured-output call. Raises on any API problem; tests never reach it."""
    from openai import OpenAI

    parts = [llm._document_block(content, filename)] if content else []
    parts.append({"type": "input_text", "text": text or "Extract this purchase order."})
    response = OpenAI(api_key=llm.api_key()).responses.parse(
        model=llm.MODEL, instructions=AI_PROMPT, input=[{"role": "user", "content": parts}], text_format=AIRead,
    )
    r = response.output_parsed
    if r is None:
        raise ValueError("The model returned an unreadable result")
    usage = getattr(response, "usage", None)
    po = {**r.model_dump(exclude={"lines"}),
          "lines": [_line((l.sku or "").upper() or None, l.description, l.quantity, l.unit_price) for l in r.lines]}
    return {"po": po, "tokens": getattr(usage, "total_tokens", None)}


def _score(po: dict) -> float:
    found = sum(1 for k in HEADER_FIELDS if po.get(k)) + (2 if po["lines"] else 0)
    return round(found / (len(HEADER_FIELDS) + 2), 2)


def _needs_ai(po: dict) -> bool:
    return not po["lines"] or sum(1 for k in HEADER_FIELDS if po.get(k)) < 2


def parse_po(filename: str, content: bytes | None = None, text: str | None = None) -> tuple[dict, dict]:
    """Returns (po, meta). meta explains which path ran so the UI can show it."""
    method, text_in = "text", text
    if content is not None:
        if content.startswith(b"%PDF"):
            text_in, method = pdf_text(content), "pdf-text"
        elif filename.lower().endswith((".csv", ".txt")) or not _is_image(content):
            text_in = content.decode("utf-8-sig", errors="replace")
            method = "text"
        else:
            text_in, method = None, "image"

    po = empty_po()
    if text_in and text_in.strip():
        if looks_like_csv(text_in):
            po, method = parse_csv(text_in), "csv"
        else:
            po = parse_text(text_in)
    rules_found = bool(po["lines"]) or any(po.get(k) for k in HEADER_FIELDS)

    meta = {"method": "rules", "input": method, "ai_used": False, "tokens": 0, "note": None}
    if method == "image" or _needs_ai(po):
        if llm.llm_enabled():
            try:
                read = _ai_read(filename, content if method in ("image", "pdf-text") else None,
                                text_in if method != "image" else None)
                ai_po = read["po"]
                # Keep whatever the rules already read; the model fills only the gaps.
                for key, value in ai_po.items():
                    if key == "lines":
                        if not po["lines"]:
                            po["lines"] = value
                    elif not po.get(key):
                        po[key] = value
                meta.update(method="hybrid" if rules_found else "ai", ai_used=True,
                            tokens=read["tokens"] or max(1, len(text_in or "") // 4 + 400))
            except Exception as exc:  # network, auth, quota: keep the rules result
                meta["note"] = f"AI read failed ({type(exc).__name__}); showing what the rules found."
        else:
            meta["note"] = ("Scanned image: set OPENAI_API_KEY to read it, or paste the PO text."
                            if method == "image" else
                            "Rules could not read every part of this PO and the AI parser is off (no OPENAI_API_KEY). "
                            "Fill the highlighted fields by hand.")

    po["order_date"] = normalize_date(po.get("order_date")) or (None if not po.get("order_date") else po["order_date"])
    po["delivery_date"] = normalize_date(po.get("delivery_date")) or (None if not po.get("delivery_date") else po["delivery_date"])
    for key in ("po_number", "buyer", "port", "currency", "buyer_email"):
        po[key] = clean(po.get(key))
    if po["currency"]:
        po["currency"] = po["currency"].upper()[:3]
    meta["confidence"] = _score(po)
    return po, meta


def _is_image(content: bytes) -> bool:
    return content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n" or content[:4] == b"RIFF" or content[:6] in (b"GIF87a", b"GIF89a")

