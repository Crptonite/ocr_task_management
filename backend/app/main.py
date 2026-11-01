from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import invoices, orders, planning, projects

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Koda Workspace API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # lets a separately hosted frontend read PDF filenames
)

app.include_router(invoices.router)  # Koda: invoice checking
app.include_router(orders.router)    # Spectra: order automation
app.include_router(projects.router)  # EM Services: project tracker
app.include_router(planning.router)  # Koda: material requirements and production priorities


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the static frontend at / (keep this last so /api routes win).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
