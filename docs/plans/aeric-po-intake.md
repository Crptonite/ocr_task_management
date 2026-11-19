# AI Coding Plan: Aeric — Module 6a (Part 1) Customer PO Intake & Validation

**Owner:** Aeric (Team Lead, 6a Part 1 — PO Intake, Fuzzy SKU Matching & Order Queue Gatekeeper)  
**Module:** Problem Statement 6a (AI Purchase Order Assistant)

---

## 1. Problem & Business Context
From `docs/meetings/2026-11-05-koda-client-briefing.md`:
- B2B furniture buyers (Pottery Barn, Crate & Barrel, Costco, RH) send Purchase Orders (POs) via PDFs, portal CSVs, free-text emails, or photographed paper notes.
- Orders routinely contain 20–30 SKUs; staff spend hours spotting 1-character SKU typos (`KD-CH-2041` vs `KD-CH-2047`), chasing missing destination ports (`TBC`) or delivery dates, and drafting buyer clarification emails before Vietnam factory scheduling.

## 2. Solution Architecture (`aeric/` Vertical Slice)
- `aeric/po_parser.py` — Hybrid rules-first PO parser: CSV / text-layer PDF / regex table & email extraction (`0 AI tokens`) + optional Tesseract OCR for scans + OpenAI Vision/Structured Outputs fallback only when needed (`ai_used` and `tokens` telemetry returned).
- `aeric/service.py` — Deterministic fuzzy SKU matcher (Levenshtein + `SequenceMatcher` scoring: `exact`, `typo`, `near`, `unknown`), field/line validation (`validate_po`), buyer clarification email generator (`clarification_email`), and 5 demo POs (`clean`, `missing`, `typo`, `email`, `csv`).
- `aeric/router.py` — FastAPI `/api/po-intake` endpoints (`/`, `/validate`, `/email`, `/submit`, `/samples`) with 10 MB upload cap, `%PDF` magic-byte validation, Pydantic bounds, and `409` blocking guard when errors remain.
- `aeric/po_intake.js` — Intake & Validation Studio UI (`#ord-intake`): drag/drop file upload, camera scanner integration (`window.Scanner`), sample chips, inline header/SKU editing, 1-click `Accept SKU`, Buyer Clarification Email modal (`mailto:` + Copy), and Order Queue handoff (`#orders/queue`).
- `aeric/test_po_intake.py` — Pytest suite covering clean POs, CSV/PDF rules, camera scan OCR/AI fallback, missing port/date blocking (`409`), 1-digit SKU typo acceptance, hybrid AI fallback, and invalid upload rejections (`400`/`415`).
