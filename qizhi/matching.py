"""3-way invoice matching: Invoice vs Purchase Order vs Receipt.

Output feeds (a) the side-by-side diff matrix in the UI and (b) the task suggester.
Edge cases covered: price mismatch, qty mismatch (over/under billed), missing PO, PO not found,
line not on PO, ordered-but-not-billed, vendor mismatch, arithmetic / tax / total errors,
receipt rounding (derived unit prices).
"""
import hashlib
import os
import re
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher

from app.ai.extractor import normalize_date
from qizhi.money import D, q2, s2, sq

CFG = {
    "price_tol": Decimal("0.01"),       # absolute per-unit tolerance
    "header_tol": Decimal("0.02"),      # tolerance on subtotal / tax / total
    "critical": Decimal("500"),         # |variance| >= -> critical
    "high": Decimal("100"),
    "medium": Decimal("10"),
    "fuzzy": 0.55,                      # description similarity needed to pair lines
    "late_days": int(os.getenv("INVOICE_LATE_DAYS", "90")),   # invoice this long after the PO date = stale
}

# fixed severity for checks that have no money variance
KIND_SEVERITY = {"INVOICE_BEFORE_PO": "high", "PO_EXPIRED": "high", "INVOICE_DATE_FUTURE": "high",
                 "INVOICE_LATE": "medium", "INVOICE_DATE_MISSING": "medium"}
ORDER = ["low", "medium", "high", "critical"]


def parse_date(v):
    """Accepts ISO, DD/MM/YYYY (Singapore style), '30 September 2025'. Returns a date or None.
    NOTE: 03/04/2026 is read as 3 April (day first). Send ISO dates to avoid any doubt."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    iso = normalize_date(str(v)) if v else None
    return date.fromisoformat(iso) if iso else None


# ----------------------------------------------------------------- normalisation
def norm_line(raw: dict, idx: int) -> dict:
    qty, unit, total = D(raw.get("qty")), D(raw.get("unit_price")), D(raw.get("line_total"))
    derived = bool(raw.get("unit_is_derived"))
    if total is None and qty is not None and unit is not None:
        total = q2(qty * unit)
    if unit is None and total is not None and qty:
        unit, derived = total / qty, True
    return {"idx": idx, "sku": (raw.get("sku") or "").strip().upper() or None,
            "description": raw.get("description", ""), "qty": qty, "unit": unit,
            "total": total, "derived": derived}


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", s.lower().replace("-", " ")))


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    jac = len(ta & tb) / len(ta | tb) if ta and tb else 0
    seq = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return max(jac, seq)


def pair_lines(base: list, other: list) -> dict:
    """base idx -> other idx. SKU first, then best fuzzy description (greedy, 1:1)."""
    pairs, used = {}, set()
    for b in base:
        if b["sku"]:
            o = next((o for o in other if o["sku"] == b["sku"] and o["idx"] not in used), None)
            if o:
                pairs[b["idx"]] = o["idx"]
                used.add(o["idx"])
    cands = sorted(((similarity(b["description"], o["description"]), b["idx"], o["idx"])
                    for b in base if b["idx"] not in pairs for o in other if o["idx"] not in used),
                   reverse=True)
    for score, bi, oi in cands:
        if score >= CFG["fuzzy"] and bi not in pairs and oi not in used:
            pairs[bi] = oi
            used.add(oi)
    return pairs


# ----------------------------------------------------------------- comparisons
def price_differs(a: dict, b: dict) -> bool:
    """Unit price comparison with rounding awareness.
    A unit price derived from a printed line total (receipt) can be off by up to half a cent
    divided by the quantity, so widen the tolerance by that much."""
    tol = CFG["price_tol"]
    for x in (a, b):
        if x["derived"] and x["qty"]:
            tol += Decimal("0.005") / x["qty"]
    return abs(a["unit"] - b["unit"]) > tol


def severity(variance: Decimal, kind: str = "") -> str:
    if kind in ("MISSING_PO", "PO_NOT_FOUND"):
        return "critical"
    if kind in KIND_SEVERITY:
        return KIND_SEVERITY[kind]
    v = abs(variance or 0)
    if kind == "LINE_NOT_ON_PO":
        return "critical" if v >= CFG["critical"] else "high"
    if v >= CFG["critical"]:
        return "critical"
    if v >= CFG["high"]:
        return "high"
    if v >= CFG["medium"]:
        return "medium"
    return "low"


def _fp(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def disc(inv_no, kind, source, line_key, field, expected, actual, variance, message, line_no=None):
    return {"id": _fp(inv_no, kind, source, line_key, field), "type": kind, "source": source,
            "line_key": line_key, "line_no": line_no, "field": field,
            "expected": expected, "actual": actual,
            "variance": s2(variance) if variance is not None else None,
            "severity": severity(variance or Decimal(0), kind), "message": message}


def _cell(x):
    return None if x is None else {"qty": sq(x["qty"]), "unit": s2(x["unit"]), "total": s2(x["total"]),
                                   "derived": x["derived"], "description": x["description"]}


# ----------------------------------------------------------------- date checks
def date_checks(inv_no, invoice, po, today=None):
    """Invoice date vs PO date. Returns (header_rows, discrepancies)."""
    today, rows, out = today or date.today(), [], []
    raw = invoice.get("date")
    inv_d = parse_date(raw)
    if inv_d is None:
        out.append(disc(inv_no, "INVOICE_DATE_MISSING", "invoice", "header", "date", "a valid date",
                        str(raw) if raw else "blank", None,
                        "Invoice date is missing or could not be read, so it cannot be checked against the PO."))
        return rows, out
    if inv_d > today:
        out.append(disc(inv_no, "INVOICE_DATE_FUTURE", "invoice", "header", "date", f"on or before {today}",
                        str(inv_d), None, f"Invoice is dated {inv_d}, which is in the future."))
    po_d = parse_date((po or {}).get("po_date") or (po or {}).get("date"))
    if po and po_d:
        days = (inv_d - po_d).days
        ok = 0 <= days <= CFG["late_days"]
        rows.append({"name": "invoice_vs_po_date", "label": "Invoice date vs PO date", "kind": "date",
                     "invoice": str(inv_d), "other": str(po_d), "ok": ok})
        if days < 0:
            out.append(disc(inv_no, "INVOICE_BEFORE_PO", "po", "header", "date", f"on or after {po_d}", str(inv_d),
                            None, f"Invoice is dated {-days} day(s) before PO {po.get('po_number', '')} was raised. "
                                  "The work may have been ordered after the fact."))
        elif days > CFG["late_days"]:
            out.append(disc(inv_no, "INVOICE_LATE", "po", "header", "date", f"within {CFG['late_days']} days of {po_d}",
                            str(inv_d), None, f"Invoice arrived {days} days after the PO date "
                                              f"(limit {CFG['late_days']} days)."))
    valid_until = parse_date((po or {}).get("valid_until"))
    if po and valid_until:
        ok = inv_d <= valid_until
        rows.append({"name": "invoice_vs_po_expiry", "label": "Invoice date vs PO valid-until", "kind": "date",
                     "invoice": str(inv_d), "other": str(valid_until), "ok": ok})
        if not ok:
            out.append(disc(inv_no, "PO_EXPIRED", "po", "header", "valid_until", f"on or before {valid_until}",
                            str(inv_d), None, f"PO expired on {valid_until}; the invoice is dated {inv_d}."))
    return rows, out


# ----------------------------------------------------------------- main entry
def match_invoice(invoice: dict, po: dict | None, receipt: dict | None, today: date | None = None) -> dict:
    inv_no = invoice.get("invoice_no") or "UNKNOWN"
    po_ref = (invoice.get("po_number") or "").strip()
    discs, header = [], []

    inv_lines = [norm_line(l, i) for i, l in enumerate(invoice.get("lines", []))]
    po_lines = [norm_line(l, i) for i, l in enumerate((po or {}).get("lines", []))]
    rc_lines = [norm_line(l, i) for i, l in enumerate((receipt or {}).get("items", []))]

    # ---- edge case: missing PO
    if not po_ref:
        discs.append(disc(inv_no, "MISSING_PO", "po", "header", "po_number", "a PO number", "blank", None,
                          "Invoice carries no PO number, so it cannot be matched or posted to the ERP."))
    elif po is None:
        discs.append(disc(inv_no, "PO_NOT_FOUND", "po", "header", "po_number", po_ref, "not in ERP", None,
                          f"PO {po_ref} was quoted on the invoice but does not exist in the PO register."))
    elif similarity(invoice.get("vendor", ""), po.get("vendor", "")) < 0.6:
        discs.append(disc(inv_no, "VENDOR_MISMATCH", "po", "header", "vendor", po.get("vendor"),
                          invoice.get("vendor"), None, "Vendor on invoice differs from vendor on the PO."))

    p_pairs = pair_lines(inv_lines, po_lines) if po else {}
    r_pairs = pair_lines(inv_lines, rc_lines) if receipt else {}
    po_by, rc_by = {l["idx"]: l for l in po_lines}, {l["idx"]: l for l in rc_lines}

    rows = []
    for il in inv_lines:
        key = il["sku"] or f"L{il['idx']+1}"
        pl, rl = po_by.get(p_pairs.get(il["idx"])), rc_by.get(r_pairs.get(il["idx"]))
        diff = {"po_qty": "na", "po_price": "na", "rc_qty": "na", "rc_price": "na"}
        flags = []

        # invoice internal arithmetic
        if il["qty"] is not None and il["unit"] is not None and il["total"] is not None and not il["derived"]:
            if abs(q2(il["qty"] * il["unit"]) - il["total"]) > CFG["header_tol"]:
                d = disc(inv_no, "LINE_MATH", "invoice", key, "line_total", s2(il["qty"] * il["unit"]),
                         s2(il["total"]), il["total"] - il["qty"] * il["unit"],
                         f"{il['description']}: qty x unit price does not equal the line total.", il["idx"] + 1)
                discs.append(d)
                flags.append(d["id"])

        if po and not pl:
            amt = il["total"] or Decimal(0)
            d = disc(inv_no, "LINE_NOT_ON_PO", "po", key, "line", "on PO", "not on PO", amt,
                     f"'{il['description']}' is billed but is not on PO {po_ref}.", il["idx"] + 1)
            discs.append(d)
            flags.append(d["id"])
        if pl:
            diff["po_qty"] = diff["po_price"] = "ok"
            if il["qty"] != pl["qty"]:
                diff["po_qty"] = "diff"
                v = (il["qty"] - pl["qty"]) * il["unit"]
                d = disc(inv_no, "QTY_MISMATCH", "po", key, "qty", sq(pl["qty"]), sq(il["qty"]), v,
                         f"{il['description']}: invoiced {sq(il['qty'])} vs ordered {sq(pl['qty'])} "
                         f"({'over' if v > 0 else 'under'}-billed by {s2(abs(v))}).", il["idx"] + 1)
                discs.append(d)
                flags.append(d["id"])
            if price_differs(il, pl):
                diff["po_price"] = "diff"
                v = (il["unit"] - pl["unit"]) * il["qty"]
                d = disc(inv_no, "PRICE_MISMATCH", "po", key, "unit_price", s2(pl["unit"]), s2(il["unit"]), v,
                         f"{il['description']}: unit price {s2(il['unit'])} vs PO {s2(pl['unit'])} "
                         f"(impact {s2(v)}).", il["idx"] + 1)
                discs.append(d)
                flags.append(d["id"])
        if receipt and not rl:
            d = disc(inv_no, "LINE_NOT_ON_RECEIPT", "receipt", key, "line", "on receipt", "missing",
                     il["total"] or Decimal(0), f"'{il['description']}' is billed but not on the receipt.",
                     il["idx"] + 1)
            discs.append(d)
            flags.append(d["id"])
        if rl:
            diff["rc_qty"] = diff["rc_price"] = "ok"
            if il["qty"] != rl["qty"]:
                diff["rc_qty"] = "diff"
                v = (il["qty"] - rl["qty"]) * il["unit"]
                d = disc(inv_no, "QTY_MISMATCH", "receipt", key, "qty", sq(rl["qty"]), sq(il["qty"]), v,
                         f"{il['description']}: invoiced {sq(il['qty'])} vs receipt {sq(rl['qty'])}.",
                         il["idx"] + 1)
                discs.append(d)
                flags.append(d["id"])
            if price_differs(il, rl):
                diff["rc_price"] = "diff"
                v = (il["unit"] - rl["unit"]) * il["qty"]
                d = disc(inv_no, "PRICE_MISMATCH", "receipt", key, "unit_price", s2(rl["unit"]), s2(il["unit"]),
                         v, f"{il['description']}: unit price {s2(il['unit'])} vs receipt-derived "
                            f"{s2(rl['unit'])} (receipt line total {s2(rl['total'])}).", il["idx"] + 1)
                discs.append(d)
                flags.append(d["id"])
        rows.append({"row": il["idx"] + 1, "key": key, "description": il["description"],
                     "invoice": _cell(il), "po": _cell(pl), "receipt": _cell(rl), "diff": diff,
                     "flags": flags,
                     "status": "ok" if not flags else max((x["severity"] for x in discs if x["id"] in flags),
                                                          key=ORDER.index)})

    # ---- lines on PO / receipt that the invoice never billed
    for pl in po_lines:
        if pl["idx"] not in p_pairs.values():
            d = disc(inv_no, "ORDERED_NOT_BILLED", "po", f"PO{pl['idx']+1}", "line", "billed", "absent",
                     pl["total"] or Decimal(0), f"PO line '{pl['description']}' is not on the invoice "
                                                "(back-order or partial billing?).")
            discs.append(d)
            rows.append({"row": len(rows) + 1, "key": f"PO{pl['idx']+1}", "description": pl["description"],
                         "invoice": None, "po": _cell(pl), "receipt": None,
                         "diff": {"po_qty": "diff", "po_price": "na", "rc_qty": "na", "rc_price": "na"},
                         "flags": [d["id"]], "status": "low"})
    for rl in rc_lines:
        if rl["idx"] not in r_pairs.values():
            d = disc(inv_no, "RECEIVED_NOT_BILLED", "receipt", f"RC{rl['idx']+1}", "line", "billed", "absent",
                     rl["total"] or Decimal(0), f"Receipt line '{rl['description']}' is not on the invoice.")
            discs.append(d)
            rows.append({"row": len(rows) + 1, "key": f"RC{rl['idx']+1}", "description": rl["description"],
                         "invoice": None, "po": None, "receipt": _cell(rl),
                         "diff": {"po_qty": "na", "po_price": "na", "rc_qty": "diff", "rc_price": "na"},
                         "flags": [d["id"]], "status": "low"})

    # ---- header level checks
    def hcheck(name, a, b, label, kind, source=None):
        if a is None or b is None:
            return
        ok = abs(a - b) <= CFG["header_tol"]
        header.append({"name": name, "label": label, "invoice": s2(a), "other": s2(b), "ok": ok})
        if not ok:
            discs.append(disc(inv_no, kind, source or ("invoice" if "invoice" in name else "receipt"), "header", name,
                              s2(b), s2(a), a - b, f"{label}: invoice {s2(a)} vs expected {s2(b)}."))

    inv_sub, inv_tax, inv_tot = D(invoice.get("subtotal")), D(invoice.get("tax")), D(invoice.get("total"))
    tax_rate = D(invoice.get("tax_rate"))
    line_sum = sum((l["total"] for l in inv_lines if l["total"] is not None), Decimal(0))
    hcheck("invoice_subtotal", inv_sub, line_sum, "Invoice subtotal vs sum of lines", "TOTAL_MISMATCH")
    if tax_rate is not None and inv_tax is not None:
        hcheck("invoice_tax", inv_tax, q2((inv_sub if inv_sub is not None else line_sum) * tax_rate),
               "Invoice tax vs expected tax", "TAX_MISMATCH", "invoice")
    if None not in (inv_sub, inv_tax):
        hcheck("invoice_total", inv_tot, inv_sub + inv_tax, "Invoice total vs subtotal + tax", "TOTAL_MISMATCH")
    if receipt:
        hcheck("receipt_subtotal", inv_sub, D(receipt.get("subtotal")), "Subtotal vs receipt", "TOTAL_MISMATCH")
        hcheck("receipt_tax", inv_tax, D(receipt.get("tax")), "Tax vs receipt", "TAX_MISMATCH")
        hcheck("receipt_total", inv_tot, D(receipt.get("total")), "Total vs receipt", "TOTAL_MISMATCH")
        for c in receipt.get("checks", []):
            if not c["ok"]:
                discs.append(disc(inv_no, "RECEIPT_OCR_UNRELIABLE", "receipt", "header", c["name"], "consistent",
                                  c["detail"], None, f"Receipt arithmetic check failed ({c['detail']}). "
                                                     "OCR may have misread a figure; re-scan before trusting it."))

    # ---- invoice total vs PO total
    if po and (po_lines or D(po.get("total")) is not None):
        po_total = D(po.get("total"))
        if po_total is not None and inv_tot is not None:
            a, b, label = inv_tot, po_total, "Invoice total vs PO total"
        else:
            b = D(po.get("subtotal"))
            if b is None:
                b = sum((l["total"] for l in po_lines if l["total"] is not None), Decimal(0))
            a, label = (inv_sub if inv_sub is not None else line_sum), "Invoice subtotal vs PO subtotal"
        partial = a < b - CFG["header_tol"] and any(d["type"] == "ORDERED_NOT_BILLED" for d in discs)
        if partial:      # under-billing already explained by PO lines missing from the invoice
            header.append({"name": "po_total", "label": label + " (partial billing)", "invoice": s2(a),
                           "other": s2(b), "ok": True})
        else:
            hcheck("po_total", a, b, label, "PO_TOTAL_MISMATCH", "po")

    # ---- invoice date vs PO date
    d_rows, d_discs = date_checks(inv_no, invoice, po, today)
    header.extend(d_rows)
    discs.extend(d_discs)

    # dedupe (same id) preserving order
    seen, uniq = set(), []
    for d in discs:
        if d["id"] not in seen:
            seen.add(d["id"])
            uniq.append(d)

    sev = [d["severity"] for d in uniq]
    status = "MATCHED" if not uniq else ("BLOCKED" if ("critical" in sev) else "REVIEW")
    return {"invoice_no": inv_no, "vendor": invoice.get("vendor"), "po_number": po_ref or None,
            "po_found": po is not None, "receipt_used": receipt is not None, "status": status,
            "summary": {"discrepancies": len(uniq), **{s: sev.count(s) for s in ORDER}},
            "matrix": rows, "header_checks": header, "discrepancies": uniq,
            "receipt_warnings": (receipt or {}).get("warnings", [])}
