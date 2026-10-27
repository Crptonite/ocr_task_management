# Architecture (draft)

```
Invoice PDF / scan
      │
      ▼
Extraction (backend/app/ai)          OCR / LLM → structured JSON        [Lucas]
      │
      ▼
Matching (backend/app/services)      invoice vs PO (later + GRN)        [Aeric]
      │
      ▼
Review UI (frontend)                 staff check flags, approve / edit  [Qizhi]
      │
      ▼
Export                               CSV / Excel for Dynamics           [Aeric]

Tests across all layers                                                [Wesley]
```

## API (v0.1)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/invoices` | Invoices with match result |
| GET | `/api/invoices/{number}` | One invoice |
| GET | `/api/purchase-orders` | Mock ERP purchase orders |
| POST | `/api/invoices/upload` | Upload file → extraction draft |

## Open questions (after client meeting)

- 2-way or 3-way matching?
- Tolerance thresholds for price / tax?
- Dynamics version and import format?

