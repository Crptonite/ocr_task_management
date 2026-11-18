# AI Coding Plan: Wesley — Module 6a (Part 2) SG-to-Vietnam ERP Bridge

**Owner:** Wesley (6a Part 2 — SG-VN ERP Bridge, Price Masking & Dual Navision 2013 Export)  
**Module:** Problem Statement 6a (AI Purchase Order Assistant)  
**Date:** 2026-11-18  

---

## 1. Problem & Business Context
From the Koda Ltd client briefing (`docs/meetings/2026-11-05-koda-client-briefing.md`):
- Koda Ltd (Singapore HQ) receives B2B customer Purchase Orders (e.g., Pottery Barn, Crate & Barrel, Costco) at the **Customer Sales Contract Price**.
- Koda manufactures in **Vietnam** (1,000+ floor workers) under a separate **Microsoft Dynamics Navision 2013** instance.
- Singapore HQ issues an internal PO / Vietnam Factory Sales Order (SO) using **Factory Transfer Prices** and Vietnam Engineering **BOM Item Codes**.
- **Strict Confidentiality Boundary:** Vietnam factory and sourcing staff must **never** see the customer contract price (only the factory transfer price) to avoid conflict of interest. Currently, staff re-enter every order manually across both Navision instances.
- **Lead-Time Reality:** Furniture timber and hardware orders require factory manufacturing lead times plus sea freight / container consolidation buffer. Rush delivery windows must be flagged before committing to the factory schedule.

## 2. Solution Architecture (`wesley/` Isolated Vertical Slice)
Following the team's vertical-slice convention (`aeric/` for 6a Part 1), all 6a Part 2 logic lives in `wesley/`:
- `wesley/data/transfer_pricing.json` — Master SKU-to-Vietnam BOM code, factory transfer price, lead-time, and plant assignment table. Deliberately leaves `KD-LC-7105` (*Linden lounge chair*) unmapped (`transfer_price: null`) to demonstrate the unmapped transfer price edge case.
- `wesley/service.py` — Pure business rules + deterministic Lead-Time & Rush Order Risk Advisor (with optional OpenAI GPT summary when `OPENAI_API_KEY` is configured, falling back gracefully with 0 tokens):
  - `get_transfer_catalog()`, `update_transfer_price()`, `reset_mappings()`
  - `analyze_lead_time_risk()` (`rush` / `tight` / `feasible` + actionable mitigation recommendations)
  - `build_bridge_record()` with role-based price masking (`role="sg"` exposes contract price & HQ margin; `role="vn"` masks customer unit price, line amount, customer total, and HQ margin to `None`).
- `wesley/exporter.py` — Navision 2013 CSV (`sg`, `vn`, `dual`) and `fpdf2` PDF (`sg`, `vn`, `dual`) exporters.
- `wesley/router.py` — FastAPI `/api/erp-bridge/*` endpoints.
- `wesley/erp_bridge.js` — Integrated Studio UI section (`#ord-bridge`) inside the Orders (6a) workspace with SG HQ vs. Vietnam Factory role toggle, inline transfer price resolver, Lead-Time Risk Advisor, demo scenario seeders, and 1-click Dual Navision CSV/PDF export.
- `wesley/test_erp_bridge.py` — Automated pytest suite covering end-to-end intake→approve→bridge flow, confidentiality price masking, unmapped SKU blocking/resolution, rush order advisor, CSV/PDF exports, and API error states.

## 3. API Endpoints (`/api/erp-bridge`)
| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/erp-bridge/orders?role=sg\|vn&include_pending=false` | List orders enriched with bridge conversion status & lead-time risk |
| `GET` | `/api/erp-bridge/orders/{order_id}?role=sg\|vn` | Inspect a single bridged order under SG HQ or Vietnam Factory role |
| `GET` | `/api/erp-bridge/transfer-prices` | List master SKU transfer prices and Vietnam BOM codes |
| `PUT` | `/api/erp-bridge/transfer-prices/{sku}` | Map or update transfer price, BOM code, and lead time inline |
| `POST` | `/api/erp-bridge/orders/{order_id}/convert` | Lock Vietnam Factory SO (`VN-SO-...`); returns `409` if unapproved or unmapped SKUs exist |
| `POST` | `/api/erp-bridge/orders/{order_id}/advisor` | Run Lead-Time & Rush Order Risk Advisor (hybrid deterministic + optional LLM) |
| `GET` | `/api/erp-bridge/orders/{order_id}/export.csv?target=dual\|sg\|vn` | Export Navision 2013 CSV; returns `409` if unapproved or unmapped SKUs exist |
| `GET` | `/api/erp-bridge/orders/{order_id}/export.pdf?target=dual\|sg\|vn` | Export Navision 2013 PDF sheet/pack; returns `409` if unapproved or unmapped SKUs exist |
| `POST` | `/api/erp-bridge/seed/{scenario}` | Seed `clean`, `rush`, or `unmapped` approved demo order for live walkthroughs |

## 4. Edge Cases & Verification Plan
1. **Unmapped Transfer Price (`KD-LC-7105`):** Blocks factory SO conversion and Navision export with HTTP `409`; staff resolve the transfer price inline via `PUT /api/erp-bridge/transfer-prices/KD-LC-7105` and immediately unblock conversion/export.
2. **Role-Based Price Masking (`role=vn`):** Strips customer contract unit price, line amount, customer total, and HQ margin from both JSON API responses and Vietnam Navision CSV/PDF exports.
3. **Rush Order Risk:** Flags orders where `available_days < max_mfg_days` as `rush` and `max_mfg_days <= available_days < required_days` as `tight`, surfacing capacity & sea-freight mitigation steps.
4. **Tests:** Run full `pytest` suite across `backend/tests`, `aeric`, and `wesley`.
