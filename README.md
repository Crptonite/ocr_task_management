# Koda Invoice Check

AI-assisted invoice checking for **Koda Ltd** (Problem Statement 6b, SCCCI × NYP AI Innovation Challenge, IT2134).

Staff upload a supplier invoice → the system extracts the fields → matches them against the purchase order → flags price, quantity, tax and duplicate issues → staff approve and export for Dynamics.

## Team

| Member | Role | Owns |
| --- | --- | --- |
| Aeric (lead) | Backend & architecture | `backend/app/` (API, matching, data) |
| Qizhi | Frontend | `frontend/` |
| Lucas | OCR & AI | `backend/app/ai/` |
| Wesley | Testing & QA | `backend/tests/`, `.github/workflows/` |

## Project structure

```
backend/
  app/
    main.py            FastAPI app + serves the frontend
    services/          matching engine (invoice vs PO)
    ai/                extraction pipeline (OCR / LLM)
    data/              mock ERP data (POs, invoices)
  tests/               pytest
frontend/              static HTML / CSS / JS (light + dark mode)
docs/                  architecture, meeting notes, client Q&A
legacy/opspilot/       earlier Next.js prototype, kept for reference
```

## Run it

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 (frontend) or http://localhost:8000/docs (API docs).

Run tests: `cd backend && pytest`

## Workflow

See [CONTRIBUTING.md](CONTRIBUTING.md) for branches, commits and pull requests.

