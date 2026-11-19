"""Receipt (hard-copy / POS) OCR text -> structured lines.

Why a POS receipt needs its own parser:
1. It prints the LINE TOTAL on each row, not the unit price, so unit = line_total / qty.
2. Long descriptions wrap onto several lines; lines are buffered until an amount appears.
3. OCR turns the decimal point into a comma ("$158,44"); decimal commas vs thousands are normalised.
4. Derived unit prices carry rounding, so matching uses a rounding-aware tolerance.
"""
import re
from datetime import datetime
from decimal import Decimal

from qizhi.money import D, q2, s2

# OCR often inserts stray spaces around the decimal mark ("$158 ,44"), so allow \s? either side of it
AMOUNT_END = re.compile(r"(?<![\d.,])\$?\s?(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\s?[.,]\s?\d{2})\s*$")
QTY_START = re.compile(r"^(\d+)\s*[xX]?\s+(?=\S)")
SEPARATOR = re.compile(r"^[-=_*\s]{6,}$")


def parse_amount(token: str):
    """'$158,44' -> 158.44 ; '1,234.56' -> 1234.56 ; '24.13' -> 24.13"""
    t = token.replace("$", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{2}", t):
        t = t.replace(",", "")
    elif re.fullmatch(r"\d+,\d{2}", t):
        t = t.replace(",", ".")
    return D(t)


def _after(label_re, lines):
    for ln in lines:
        m = re.match(label_re, ln, re.I)
        if m:
            return ln[m.end():].strip()
    return None


def _amount_in(text):
    if not text:
        return None
    m = AMOUNT_END.search(text.strip())
    return parse_amount(m.group(1)) if m else None


def parse_receipt_text(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines()]
    warnings, checks = [], []

    # --- locate the item block: after the cashier line (or 2nd separator) until SUBTOTAL
    start = next((i + 1 for i, ln in enumerate(lines) if re.search(r"cashier", ln, re.I)), None)
    if start is None:
        seps = [i for i, ln in enumerate(lines) if SEPARATOR.match(ln)]
        start = seps[1] + 1 if len(seps) > 1 else 0
    end = next((i for i, ln in enumerate(lines) if re.match(r"sub\s*-?\s*total", ln, re.I)), len(lines))

    items, buf = [], []
    for ln in lines[start:end]:
        if not ln or SEPARATOR.match(ln):
            continue
        buf.append(ln)
        m = AMOUNT_END.search(ln)
        if not m:
            continue                                   # description wraps onto next line
        total = parse_amount(m.group(1))
        joined = AMOUNT_END.sub("", " ".join(buf)).strip()
        qm = QTY_START.match(joined)
        qty, assumed = (Decimal(qm.group(1)), False) if qm else (Decimal(1), True)
        if qty == 0:
            warnings.append(f"Line {len(items) + 1}: quantity 0 read, skipped.")
            buf = []
            continue
        desc = re.sub(r"\s+", " ", joined[qm.end():] if qm else joined).strip()
        unit = total / qty
        items.append({
            "line_no": len(items) + 1,
            "description": desc,
            "qty": qty,
            "line_total": total,
            "unit_price": unit,                         # full precision, derived
            "unit_price_2dp": q2(unit),
            "unit_is_derived": True,
            "qty_assumed": assumed,
        })
        if assumed:
            warnings.append(f"Line {len(items)}: no quantity printed, assumed 1.")
        buf = []
    if buf:
        warnings.append(f"Unparsed trailing text before SUBTOTAL: {' '.join(buf)!r}")

    # --- footer totals
    footer = lines[end:]
    subtotal = _amount_in(_after(r"sub\s*-?\s*total", footer))
    tax_line = next((ln for ln in footer if re.match(r"tax", ln, re.I)), "")
    tax = _amount_in(tax_line)
    rate_m = re.search(r"\((\d+(?:[.,]\d+)?)\s*%\)", tax_line)
    tax_rate = D(rate_m.group(1).replace(",", ".")) / 100 if rate_m else None
    total = _amount_in(next((ln for ln in footer if re.match(r"total\b", ln, re.I)), ""))

    # --- arithmetic self-checks: tells us whether OCR itself is trustworthy
    line_sum = sum((i["line_total"] for i in items), Decimal(0))
    if subtotal is not None:
        checks.append({"name": "lines_sum_to_subtotal", "ok": q2(line_sum) == subtotal,
                       "detail": f"lines {s2(line_sum)} vs subtotal {s2(subtotal)}"})
    if subtotal is not None and tax_rate is not None and tax is not None:
        exp = q2(subtotal * tax_rate)
        checks.append({"name": "tax_matches_rate", "ok": abs(exp - tax) <= Decimal("0.01"),
                       "detail": f"{tax_rate*100}% of {s2(subtotal)} = {s2(exp)}, printed {s2(tax)}"})
    if None not in (subtotal, tax, total):
        checks.append({"name": "total_is_subtotal_plus_tax", "ok": q2(subtotal + tax) == total,
                       "detail": f"{s2(subtotal)} + {s2(tax)} = {s2(subtotal + tax)}, printed {s2(total)}"})

    # --- date sanity (header date vs transaction date)
    hdr = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", "\n".join(lines[:8]))
    txn = re.search(r"date/time\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    header_date = txn_date = None
    try:
        header_date = datetime.strptime(hdr.group(1), "%d %B %Y").date() if hdr else None
        txn_date = datetime.strptime(txn.group(1), "%m/%d/%Y").date() if txn else None
    except ValueError:
        pass
    if header_date and txn_date and header_date != txn_date:
        warnings.append(f"Receipt header date {header_date} differs from transaction date {txn_date}. "
                        "Verify the receipt is genuine / correctly scanned.")

    merchant = next((ln for ln in lines[:12] if ln and not SEPARATOR.match(ln)
                     and not re.search(r"receipt|\d{4}|^\d{1,2}:\d{2}", ln, re.I)), None)
    ref = re.search(r"reference\s*#\s*(\S+)", text, re.I)
    return {
        "merchant": merchant,
        "header_date": str(header_date) if header_date else None,
        "transaction_date": str(txn_date) if txn_date else None,
        "reference": ref.group(1) if ref else None,
        "items": items,
        "subtotal": subtotal, "tax_rate": tax_rate, "tax": tax, "total": total,
        "checks": checks, "warnings": warnings,
        "ocr_trusted": all(c["ok"] for c in checks) if checks else False,
    }


def receipt_to_json(r: dict) -> dict:
    """JSON-safe version (Decimals -> strings)."""
    out = dict(r)
    for k in ("subtotal", "tax", "total"):
        out[k] = s2(r[k])
    out["tax_rate"] = str(r["tax_rate"]) if r["tax_rate"] is not None else None
    out["items"] = [{**i, "qty": str(int(i["qty"])), "line_total": s2(i["line_total"]),
                     "unit_price": str(i["unit_price"].quantize(Decimal("0.0001"))),
                     "unit_price_2dp": s2(i["unit_price_2dp"])} for i in r["items"]]
    return out
