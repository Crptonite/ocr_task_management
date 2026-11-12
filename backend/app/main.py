from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import store
from app.services import autofill, documents as documents_service, supabase_store
from app.routers import documents, invoice_generator, invoice_queue, invoices, orders, planning, po_intake, projects

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Bring back invoices saved in Supabase so uploads survive a restart."""
    if supabase_store.enabled():
        try:
            known = {i["invoice_number"] for i in store.erp["invoices"]}
            loaded = [i for i in supabase_store.load_invoices() if i["invoice_number"] not in known]
            autofill.restore(loaded)
            store.erp["invoices"].extend(loaded)
        except Exception as exc:
            print(f"Supabase invoices not loaded: {exc}")
    documents_service.sync_csv()
    yield


app = FastAPI(title="Koda Workspace API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # lets a separately hosted frontend read PDF filenames
)

app.include_router(documents.router)  # combined document list + CSV
app.include_router(invoices.router)  # Koda: invoice checking
app.include_router(invoice_generator.router)  # standalone invoice generator
app.include_router(orders.router)    # Spectra: order automation
app.include_router(po_intake.router)  # Koda 6a: PO intake & validation
app.include_router(invoice_queue.router)  # Spectra: review invoice queue for approved orders
app.include_router(projects.router)  # EM Services: project tracker
app.include_router(planning.router)  # Koda: material requirements and production priorities


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Clean URLs for the standalone pages (the .html paths keep working through the static mount).
PAGES = {
    "/receipt-generator": "receipt_invoice_generator.html",  # thermal receipt / invoice designer, for test uploads
    "/invoice-generator": "invoice-generator.html",
}


def _page(filename: str):
    def serve():
        path = FRONTEND_DIR / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Page not found")
        return FileResponse(path, media_type="text/html")
    return serve


for route, filename in PAGES.items():
    app.add_api_route(route, _page(filename), methods=["GET"], include_in_schema=False)


# Serve the static frontend at / (keep this last so /api routes win).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
