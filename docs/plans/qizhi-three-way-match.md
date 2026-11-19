# Plan: Qizhi 6b Part 2 — 3-Way Match, Discrepancy Tasks & Approval (integration)

**Goal:** fold Qizhi's standalone invoice checker into the unified Koda app (same pattern as `aeric/` and `wesley/`), without changing other features.

## Scope
- New top-level package `qizhi/`: `router.py` (APIRouter only), `matching.py`, `receipt_parser.py`, `pdf_extract.py`, `suggester.py`, `store.py`, `sample_data.py`, `three_way_match.js`, tests.
- All routes under `/api/three-way-match/...` (no root `/api/tasks`, `/api/me`, `/api/audit`).
- Store is self-contained and in-memory (hash-chained audit trail kept); no coupling to `app.store` / `DATABASE_URL`.

## Steps
1. Plan (this file) committed first.
2. Port backend: drop Qizhi's FastAPI app, static serving and JSON snapshot; reuse project helpers where equivalent; Pydantic bounds, 10 MB cap, magic-byte file check.
3. Frontend: nav entry + hash route `#invoices/three-way-match`, built with existing Koda classes/tokens; scoped `twm-` CSS; XSS-safe rendering.
4. Wiring (additive lines only): `main.py`, `pytest.ini`, `index.html`, `app.js`, `styles.css`, `vercel.json`, `requirements.txt`.
5. Tests: matching rules, receipt parser, segregation of duties, audit chain, API errors (bad file type, missing PO, OCR unavailable).

## Risks / decisions
- OCR (Tesseract/poppler) and `anthropic` are optional: missing tools produce a clear 422/notice, never a crash.
- Roles are demo identities (`X-User`-style choice in the UI) as in Qizhi's design; real auth is out of scope.

## Done when
Full pytest suite passes (140 existing + new), `node --check` passes on all JS, existing routes unchanged, UI checked in light/dark mode.
