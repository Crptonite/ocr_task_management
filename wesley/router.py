"""6a Part 2: SG-to-Vietnam ERP Bridge, Price Masking & Dual Navision 2013 Export API (Wesley).

GET  /api/erp-bridge/orders                    list bridged orders (approved/exported by default)
GET  /api/erp-bridge/orders/{order_id}         inspect one bridged order under SG or VN role
GET  /api/erp-bridge/transfer-prices           master SKU transfer pricing & VN BOM table
PUT  /api/erp-bridge/transfer-prices/{sku}     map or update a SKU's factory transfer price
POST /api/erp-bridge/orders/{order_id}/convert lock Vietnam Factory SO on an approved order
POST /api/erp-bridge/orders/{order_id}/advisor run Lead-Time & Rush Order Risk Advisor
GET  /api/erp-bridge/orders/{order_id}/export.csv   Dual / SG / VN Navision 2013 CSV export
GET  /api/erp-bridge/orders/{order_id}/export.pdf   Dual / SG / VN Navision 2013 PDF sheet
POST /api/erp-bridge/seed/{scenario}           seed a demo approved order (clean | rush | unmapped)
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import store
from app.services import documents
from app.services.invoice_queue import new_invoice_draft, now_iso, transaction_id
from wesley.exporter import export_navision_csv, export_navision_pdf
from wesley.service import (
    DEMO_SCENARIOS,
    build_bridge_record,
    get_transfer_catalog,
    update_transfer_price,
)

router = APIRouter(prefix="/api/erp-bridge", tags=["erp bridge (Koda 6a Part 2)"])

Role = Literal["sg", "vn"]
Target = Literal["dual", "sg", "vn"]


class TransferPriceIn(BaseModel):
    transfer_price: float = Field(gt=0, le=10_000_000)
    vn_item_code: str | None = Field(default=None, max_length=60)
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    plant: str | None = Field(default=None, max_length=120)
    updated_by: str = Field(default="ERP Coordinator", min_length=1, max_length=80)


class ConvertIn(BaseModel):
    converted_by: str = Field(default="ERP Coordinator", min_length=1, max_length=80)
    role: Role = "sg"
    notes: str = Field(default="", max_length=500)


class AdvisorIn(BaseModel):
    role: Role = "sg"


def _find_order(order_id: str) -> dict:
    order = next((o for o in store.orders["orders"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _require_exportable(bridge: dict) -> None:
    if not bridge["approved"]:
        raise HTTPException(
            status_code=409,
            detail=f"Order is '{bridge['order_status']}' — approve it in the Order Queue before ERP conversion/export.",
        )
    if bridge["unmapped_skus"]:
        raise HTTPException(
            status_code=409,
            detail="Unmapped factory transfer price for SKU(s): " + ", ".join(bridge["unmapped_skus"]),
        )
    if not bridge["lines"]:
        raise HTTPException(status_code=409, detail="Order has no line items to export.")


@router.get("/orders")
def list_bridge_orders(role: Role = "sg", include_pending: bool = False):
    """Return orders prepared for the SG-to-Vietnam ERP Bridge."""
    source_orders = [
        o for o in store.orders["orders"]
        if include_pending or o.get("status") in ("approved", "exported")
    ]
    records = [build_bridge_record(o, role=role) for o in source_orders]
    stats = {
        "total": len(records),
        "ready": sum(1 for r in records if r["status"] == "ready"),
        "converted": sum(1 for r in records if r["converted"]),
        "unmapped": sum(1 for r in records if r["unmapped_count"] > 0),
        "rush": sum(1 for r in records if r["lead_time_risk"]["risk_level"] in ("rush", "tight")),
    }
    return {"role": role, "stats": stats, "orders": records}


@router.get("/orders/{order_id}")
def get_bridge_order(order_id: str, role: Role = "sg"):
    return build_bridge_record(_find_order(order_id), role=role)


@router.get("/transfer-prices")
def list_transfer_prices():
    return get_transfer_catalog()


@router.put("/transfer-prices/{sku}")
def map_transfer_price(sku: str, body: TransferPriceIn):
    try:
        mapping = update_transfer_price(
            sku=sku,
            transfer_price=body.transfer_price,
            vn_item_code=body.vn_item_code,
            lead_time_days=body.lead_time_days,
            plant=body.plant,
            updated_by=body.updated_by,
        )
        return {"mapping": mapping}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/orders/{order_id}/convert")
def convert_order(order_id: str, body: ConvertIn | None = None):
    """Convert an approved SG sales order into a locked Vietnam Factory SO."""
    body = body or ConvertIn()
    order = _find_order(order_id)
    bridge = build_bridge_record(order, role="sg")
    _require_exportable(bridge)

    order["erp_bridge"] = {
        "converted": True,
        "vn_so_number": bridge["vn_so_number"],
        "navision_doc_no": bridge["navision_doc_no"],
        "converted_by": body.converted_by.strip(),
        "converted_at": now_iso(),
        "notes": body.notes.strip(),
    }
    documents.sync_csv()
    return build_bridge_record(order, role=body.role)


@router.post("/orders/{order_id}/advisor")
def run_lead_time_advisor(order_id: str, body: AdvisorIn | None = None):
    """Run the Lead-Time & Rush Order Risk Advisor (rules + optional LLM brief)."""
    body = body or AdvisorIn()
    order = _find_order(order_id)
    return build_bridge_record(order, role=body.role, use_ai=True)


@router.get("/orders/{order_id}/export.csv")
def export_csv(order_id: str, target: Target = "dual"):
    order = _find_order(order_id)
    role: Role = "vn" if target == "vn" else "sg"
    bridge = build_bridge_record(order, role=role)
    _require_exportable(bridge)

    csv_text = export_navision_csv(bridge, target=target)
    ref = (bridge.get("order_number") or order_id).replace(" ", "_")
    filename = f"navision2013_{target}_{ref}.csv"
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/orders/{order_id}/export.pdf")
def export_pdf(order_id: str, target: Target = "dual"):
    order = _find_order(order_id)
    role: Role = "vn" if target == "vn" else "sg"
    bridge = build_bridge_record(order, role=role)
    _require_exportable(bridge)

    pdf_bytes = export_navision_pdf(bridge, target=target)
    ref = (bridge.get("order_number") or order_id).replace(" ", "_")
    filename = f"navision2013_{target}_{ref}.pdf"
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/seed/{scenario}", status_code=201)
def seed_demo_order(scenario: str, role: Role = "sg"):
    """Seed one of the demo approved orders (clean | rush | unmapped) into the queue."""
    spec = DEMO_SCENARIOS.get(scenario)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario}'. Use clean, rush, or unmapped.")

    existing = next((o for o in store.orders["orders"] if o.get("order_number") == spec["order_number"]), None)
    if existing is not None:
        if existing.get("status") not in ("approved", "exported"):
            existing["status"] = "approved"
            existing["approval"] = {"decision": "approved", "by": "Wesley (ERP Demo)", "at": now_iso()}
            existing.setdefault("invoice", new_invoice_draft(existing, store.orders["catalog"]))
            documents.sync_csv()
        return {"order": build_bridge_record(existing, role=role)}

    from app.routers.orders import build_lines, log_status

    lines = build_lines(spec["lines"])
    order = {
        "id": store.next_id("ord", store.orders["orders"]),
        "order_number": spec["order_number"],
        "type": spec["type"],
        "counterparty": spec["counterparty"],
        "order_date": spec["order_date"],
        "delivery_date": spec["delivery_date"],
        "currency": spec["currency"],
        "port": spec["port"],
        "buyer_email": spec["buyer_email"],
        "lines": lines,
        "total": round(sum(l["amount"] for l in lines), 2),
        "status": "approved",
        "source_file": spec["source_file"],
        "created_by": "Wesley (ERP Demo)",
        "created_at": now_iso(),
        "approval": {"decision": "approved", "by": "Wesley (ERP Demo)", "at": now_iso()},
    }
    order["transaction_id"] = transaction_id(order)
    order["invoice"] = new_invoice_draft(order, store.orders["catalog"])
    log_status(order, "extracted", "Wesley (ERP Demo)", "Seeded demo order")
    log_status(order, "approved", "Wesley (ERP Demo)", "Auto-approved for ERP Bridge")
    store.orders["orders"].append(order)
    documents.sync_csv()
    return {"order": build_bridge_record(order, role=role)}
