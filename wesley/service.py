"""6a Part 2: SG-to-Vietnam ERP Bridge, Role-Based Price Masking & Lead-Time Risk Advisor.

Owner: Wesley (6a Part 2). Pure functions over plain dicts so they are easy to test;
the router wires them to the shared order queue (store.orders) and Navision 2013 exporters.
"""
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.ai import llm

DATA_PATH = Path(__file__).resolve().parent / "data" / "transfer_pricing.json"
DEFAULT_PLANT = "Koda Vietnam - Binh Duong Plant 1"
DEFAULT_LEAD_TIME_DAYS = 21

# Runtime mapping overrides (allows inline mapping of unmapped SKUs without mutating repo JSON)
_BASE_CATALOG: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
_OVERRIDES: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_sku(sku: str | None) -> str:
    return (sku or "").strip().upper().replace("\u2013", "-").replace("\u2014", "-")


def reset_mappings() -> None:
    """Clear runtime transfer-price overrides (used by tests for clean isolation)."""
    _OVERRIDES.clear()


def get_transfer_catalog() -> list[dict]:
    """Return master transfer pricing & Vietnam BOM mappings (base JSON + runtime overrides)."""
    merged: dict[str, dict] = {}
    for item in _BASE_CATALOG:
        key = _norm_sku(item["sku"])
        merged[key] = copy.deepcopy(item)
    for key, override in _OVERRIDES.items():
        if key in merged:
            merged[key].update(copy.deepcopy(override))
        else:
            merged[key] = copy.deepcopy(override)
    return list(merged.values())


def get_mapping_for_sku(sku: str | None) -> dict | None:
    key = _norm_sku(sku)
    if not key:
        return None
    for item in get_transfer_catalog():
        if _norm_sku(item["sku"]) == key:
            return item
    return None


def update_transfer_price(
    sku: str,
    transfer_price: float,
    vn_item_code: str | None = None,
    lead_time_days: int | None = None,
    plant: str | None = None,
    updated_by: str = "ERP Coordinator",
) -> dict:
    """Map or update a SKU's Vietnam factory transfer price and BOM metadata."""
    key = _norm_sku(sku)
    if not key:
        raise ValueError("SKU is required.")
    if transfer_price is None or float(transfer_price) <= 0:
        raise ValueError("Factory transfer price must be greater than 0.")

    existing = get_mapping_for_sku(key)
    record = copy.deepcopy(existing) if existing else {
        "sku": key,
        "name": key,
        "customer_list_price": None,
        "transfer_price": None,
        "suggested_transfer_price": round(float(transfer_price), 2),
        "vn_item_code": f"VN-BOM-{key.replace('-', '')}",
        "bom_summary": "Engineering BOM pending confirmation",
        "lead_time_days": DEFAULT_LEAD_TIME_DAYS,
        "plant": DEFAULT_PLANT,
    }
    record["transfer_price"] = round(float(transfer_price), 2)
    if vn_item_code and vn_item_code.strip():
        record["vn_item_code"] = vn_item_code.strip().upper()
    if lead_time_days is not None:
        if int(lead_time_days) <= 0:
            raise ValueError("Lead time must be at least 1 day.")
        record["lead_time_days"] = int(lead_time_days)
    if plant and plant.strip():
        record["plant"] = plant.strip()
    record["updated_by"] = (updated_by or "ERP Coordinator").strip()
    record["updated_at"] = _now_iso()

    _OVERRIDES[key] = record
    return copy.deepcopy(record)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def analyze_lead_time_risk(order: dict, mapped_lines: list[dict], use_ai: bool = False) -> dict:
    """Assess whether Vietnam factory manufacturing + shipping buffer fits before delivery date."""
    order_dt = _parse_iso_date(order.get("order_date"))
    delivery_dt = _parse_iso_date(order.get("delivery_date"))

    total_qty = sum(float(l.get("quantity") or 0) for l in mapped_lines)
    max_mfg_days = max((int(l.get("lead_time_days") or DEFAULT_LEAD_TIME_DAYS) for l in mapped_lines), default=DEFAULT_LEAD_TIME_DAYS)
    shipping_buffer_days = 7 + (5 if total_qty > 300 else 0)
    required_days = max_mfg_days + shipping_buffer_days

    if not order_dt or not delivery_dt:
        available_days = None
        shortfall_days = required_days
        risk_level = "rush"
        headline = "Order or delivery date missing — cannot confirm Vietnam factory schedule"
        recommendations = [
            "Confirm buyer delivery date and ex-factory ETD before releasing work orders to Vietnam.",
            f"Reserve at least {required_days} days ({max_mfg_days}d manufacturing + {shipping_buffer_days}d sea freight buffer).",
        ]
    else:
        available_days = (delivery_dt - order_dt).days
        shortfall_days = max(0, required_days - available_days)
        if available_days < max_mfg_days:
            risk_level = "rush"
            headline = (
                f"Rush order risk: {available_days}d window is shorter than {max_mfg_days}d factory build time "
                f"({required_days}d needed with freight buffer)"
            )
            recommendations = [
                f"Flag urgent schedule gap ({shortfall_days}d shortfall) to Binh Duong production control before Navision SO release.",
                "Propose split-container dispatch for fast-turnaround SKUs or request buyer ETD extension.",
                "Verify kiln-dried timber stock and oxidation-matched batches physically before cutting.",
            ]
        elif available_days < required_days:
            risk_level = "tight"
            headline = (
                f"Tight schedule: {available_days}d window covers {max_mfg_days}d build time but leaves less than "
                f"{shipping_buffer_days}d sea-freight buffer"
            )
            recommendations = [
                f"Lock Vietnam finishing line capacity immediately ({shortfall_days}d buffer shortfall).",
                "Pre-book freight forwarder container slot early to avoid late-shipment contract penalties.",
                "Confirm timber & hardware readiness with Vietnam warehouse prior to PO confirmation.",
            ]
        else:
            risk_level = "feasible"
            headline = (
                f"Schedule feasible: {available_days}d available vs {required_days}d required "
                f"({max_mfg_days}d mfg + {shipping_buffer_days}d freight)"
            )
            recommendations = [
                "Release Vietnam Navision 2013 internal SO with standard Engineering BOM allocation.",
                "Perform physical timber batch check for color/grain consistency prior to line start.",
            ]

    result = {
        "risk_level": risk_level,
        "available_days": available_days,
        "max_mfg_days": max_mfg_days,
        "shipping_buffer_days": shipping_buffer_days,
        "required_days": required_days,
        "shortfall_days": shortfall_days,
        "total_units": int(total_qty) if float(total_qty).is_integer() else round(total_qty, 2),
        "headline": headline,
        "recommendations": recommendations,
        "method": "rules",
        "ai_used": False,
        "tokens": 0,
        "ai_brief": None,
    }

    if use_ai and llm.llm_enabled():
        ai_out = _ai_advisor_summary(order, mapped_lines, result)
        if ai_out:
            result["ai_brief"] = ai_out["summary"]
            result["tokens"] = ai_out["tokens"]
            result["ai_used"] = True
            result["method"] = "hybrid"
            if ai_out["recommendations"]:
                result["recommendations"] = ai_out["recommendations"]

    return result


def _ai_advisor_summary(order: dict, mapped_lines: list[dict], base_risk: dict) -> dict | None:
    """Optional LLM advisory note for tight/rush factory scheduling. Fails open to rules."""
    try:
        from openai import OpenAI

        line_summary = ", ".join(
            f"{l.get('sku')} ({l.get('vn_item_code')}) qty={l.get('quantity')} lt={l.get('lead_time_days')}d"
            for l in mapped_lines
        )
        prompt = (
            f"Order: {order.get('order_number')} | Port: {order.get('port') or 'unspecified'} | "
            f"Order Date: {order.get('order_date')} | Delivery Date: {order.get('delivery_date')} | "
            f"Risk: {base_risk['risk_level']} ({base_risk['available_days']}d avail vs {base_risk['required_days']}d req). "
            f"Lines: {line_summary}"
        )
        response = OpenAI(api_key=llm.api_key()).responses.create(
            model=llm.MODEL,
            instructions=(
                "You are Koda Ltd's SG-to-Vietnam production coordinator advisor. Never mention customer prices. "
                "Give a concise 2-sentence operational risk assessment and 3 short bullet mitigations starting with '- '."
            ),
            input=prompt,
        )
        text = (response.output_text or "").strip()
        if not text:
            return None
        bullets = [ln.lstrip("-* ").strip() for ln in text.splitlines() if ln.strip().startswith(("-", "*"))]
        prose = " ".join(ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("-", "*")))
        tokens = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)
        return {"summary": prose or text, "recommendations": bullets[:4], "tokens": tokens}
    except Exception:
        return None


def build_bridge_record(order: dict, role: str = "sg", use_ai: bool = False) -> dict:
    """Build an SG-to-Vietnam ERP Bridge view of an order with strict role-based price masking.

    role == 'sg': Singapore HQ coordinator sees Customer Contract Price, Factory Transfer Price, and HQ Margin.
    role == 'vn': Vietnam Factory staff see VN BOM codes and Factory Transfer Price ONLY;
                  all customer contract prices and HQ margins are masked to None.
    """
    role_clean = (role or "sg").strip().lower()
    if role_clean not in ("sg", "vn"):
        raise ValueError("Role must be 'sg' or 'vn'.")
    masked = role_clean == "vn"

    raw_no = (order.get("order_number") or order.get("id") or "DRAFT").strip()
    vn_so_number = raw_no if raw_no.upper().startswith("VN-SO-") else f"VN-SO-{raw_no}"
    txn_id = order.get("transaction_id") or order.get("id") or "TXN-00000"
    navision_doc_no = f"NAV2013-VN-{txn_id}"

    mapped_lines: list[dict] = []
    unmapped_skus: list[str] = []
    customer_total = 0.0
    transfer_total = 0.0

    for idx, line in enumerate(order.get("lines") or []):
        sku = _norm_sku(line.get("sku"))
        qty_raw = line.get("quantity") or 0
        qty = int(qty_raw) if float(qty_raw).is_integer() else float(qty_raw)
        cust_price = round(float(line.get("unit_price") or 0), 2)
        cust_amount = round(qty * cust_price, 2)
        customer_total += cust_amount

        mapping = get_mapping_for_sku(sku)
        transfer_price = mapping.get("transfer_price") if mapping else None
        suggested_price = mapping.get("suggested_transfer_price") if mapping else round(cust_price * 0.65, 2)
        vn_code = mapping.get("vn_item_code") if mapping else f"VN-BOM-{sku.replace('-', '') or f'LINE{idx + 1}'}"
        bom_summary = mapping.get("bom_summary") if mapping else "BOM mapping required in Vietnam ERP"
        lead_time = int(mapping.get("lead_time_days") or DEFAULT_LEAD_TIME_DAYS) if mapping else DEFAULT_LEAD_TIME_DAYS
        plant = mapping.get("plant") if mapping else DEFAULT_PLANT

        if transfer_price is not None and float(transfer_price) > 0:
            tp = round(float(transfer_price), 2)
            t_amt = round(qty * tp, 2)
            transfer_total += t_amt
            mapping_status = "mapped"
            margin = round(cust_amount - t_amt, 2)
            margin_pct = round((margin / cust_amount) * 100, 1) if cust_amount > 0 else 0.0
        else:
            tp = None
            t_amt = None
            mapping_status = "unmapped"
            margin = None
            margin_pct = None
            unmapped_skus.append(sku or f"Line {idx + 1}")

        mapped_lines.append({
            "line_no": idx + 1,
            "sku": sku or None,
            "vn_item_code": vn_code,
            "description": line.get("description") or (mapping.get("name") if mapping else None),
            "bom_summary": bom_summary,
            "plant": plant,
            "lead_time_days": lead_time,
            "quantity": qty,
            "mapping_status": mapping_status,
            "transfer_unit_price": tp,
            "transfer_amount": t_amt,
            "suggested_transfer_price": suggested_price,
            "customer_unit_price": None if masked else cust_price,
            "customer_amount": None if masked else cust_amount,
            "hq_margin": None if masked else margin,
            "margin_pct": None if masked else margin_pct,
        })

    customer_total = round(customer_total, 2)
    transfer_total = round(transfer_total, 2)
    hq_margin_total = round(customer_total - transfer_total, 2)
    hq_margin_pct = round((hq_margin_total / customer_total) * 100, 1) if customer_total > 0 else 0.0

    lead_time_risk = analyze_lead_time_risk(order, mapped_lines, use_ai=use_ai)
    approved_for_bridge = order.get("status") in ("approved", "exported")
    bridge_meta = order.get("erp_bridge") or {}
    converted = bool(bridge_meta.get("converted"))

    issues: list[dict] = []
    if not approved_for_bridge:
        issues.append({
            "level": "error",
            "code": "order_not_approved",
            "line": None,
            "sku": None,
            "message": f"Order status is '{order.get('status')}' — approve the order in the Order Queue before converting to Vietnam Factory SO.",
        })
    for l in mapped_lines:
        if l["mapping_status"] == "unmapped":
            issues.append({
                "level": "error",
                "code": "unmapped_transfer_price",
                "line": l["line_no"] - 1,
                "sku": l["sku"],
                "message": f"Line {l['line_no']} ({l['sku'] or 'no SKU'}): Factory transfer price is unmapped — assign a transfer price before Navision export.",
            })
    if lead_time_risk["risk_level"] in ("rush", "tight"):
        issues.append({
            "level": "warning",
            "code": "rush_order_risk" if lead_time_risk["risk_level"] == "rush" else "tight_lead_time",
            "line": None,
            "sku": None,
            "message": lead_time_risk["headline"],
        })

    has_errors = any(i["level"] == "error" for i in issues)
    can_export = approved_for_bridge and not unmapped_skus and bool(mapped_lines)

    return {
        "order_id": order.get("id"),
        "transaction_id": txn_id,
        "order_number": order.get("order_number"),
        "vn_so_number": vn_so_number,
        "navision_doc_no": navision_doc_no,
        "order_status": order.get("status"),
        "approved": approved_for_bridge,
        "converted": converted,
        "conversion": copy.deepcopy(bridge_meta) if bridge_meta else None,
        "role": role_clean,
        "confidentiality_masked": masked,
        "customer_price_masked": masked,
        "sg_entity": "Koda Ltd (Singapore HQ)",
        "vn_entity": "Koda Vietnam Factory (Binh Duong)",
        "buyer": order.get("counterparty"),
        "port": order.get("port") or "Ho Chi Minh / Cat Lai -> Buyer Port",
        "order_date": order.get("order_date"),
        "delivery_date": order.get("delivery_date"),
        "currency": order.get("currency") or "USD",
        "status": "ready" if (not has_errors and bool(mapped_lines)) else "needs_attention",
        "can_convert": can_export,
        "can_export": can_export,
        "unmapped_skus": unmapped_skus,
        "unmapped_count": len(unmapped_skus),
        "customer_total": None if masked else customer_total,
        "transfer_total": None if unmapped_skus else transfer_total,
        "partial_transfer_total": transfer_total,
        "hq_margin_total": None if (masked or unmapped_skus) else hq_margin_total,
        "hq_margin_pct": None if (masked or unmapped_skus) else hq_margin_pct,
        "lead_time_risk": lead_time_risk,
        "lines": mapped_lines,
        "issues": issues,
    }


DEMO_SCENARIOS = {
    "clean": {
        "label": "Clean Multi-SKU PO (Pottery Barn)",
        "order_number": "PB-2026-44718",
        "type": "sales",
        "counterparty": "Pottery Barn Inc.",
        "port": "Los Angeles, USA",
        "buyer_email": "sourcing@potterybarn.example",
        "order_date": "2026-11-10",
        "delivery_date": "2027-01-22",
        "currency": "USD",
        "source_file": "ERP Bridge demo · Pottery Barn clean PO",
        "lines": [
            {"sku": "KD-CH-2047", "description": "Ashby oak dining chair", "quantity": 120, "unit_price": 145.0},
            {"sku": "KD-TB-3110", "description": "Ashby extending dining table", "quantity": 30, "unit_price": 1280.0},
            {"sku": "KD-BN-1520", "description": "Ashby oak bench 1.5m", "quantity": 30, "unit_price": 420.0},
            {"sku": "KD-SB-4402", "description": "Harlow teak sideboard", "quantity": 18, "unit_price": 960.0},
            {"sku": "KD-ST-6031", "description": "Linden bar stool", "quantity": 64, "unit_price": 118.0},
        ],
    },
    "rush": {
        "label": "Rush Order Risk PO (Costco)",
        "order_number": "CW-2026-0918-RUSH",
        "type": "sales",
        "counterparty": "Costco Wholesale",
        "port": "Seattle, USA",
        "buyer_email": "furniture.buying@costco.example",
        "order_date": "2026-11-18",
        "delivery_date": "2026-12-05",
        "currency": "USD",
        "source_file": "ERP Bridge demo · Costco rush PO",
        "lines": [
            {"sku": "KD-SB-4402", "description": "Harlow teak sideboard", "quantity": 120, "unit_price": 960.0},
            {"sku": "KD-CH-2047", "description": "Ashby oak dining chair", "quantity": 240, "unit_price": 145.0},
        ],
    },
    "unmapped": {
        "label": "Unmapped Transfer Price PO (RH)",
        "order_number": "RH-2026-7105",
        "type": "sales",
        "counterparty": "Restoration Hardware",
        "port": "Oakland, USA",
        "buyer_email": "dana.whitfield@rh.example",
        "order_date": "2026-11-15",
        "delivery_date": "2027-01-15",
        "currency": "USD",
        "source_file": "ERP Bridge demo · RH unmapped SKU PO",
        "lines": [
            {"sku": "KD-LC-7105", "description": "Linden lounge chair", "quantity": 40, "unit_price": 540.0},
            {"sku": "KD-CT-5208", "description": "Harlow round coffee table", "quantity": 25, "unit_price": 385.0},
        ],
    },
}
