"""Combined document list (invoices + orders) and its CSV."""
from fastapi import APIRouter
from fastapi.responses import Response

from app.services import documents

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
def list_documents():
    return documents.build_documents()


@router.get("/documents.csv")
def documents_csv():
    documents.sync_csv()
    return Response(
        documents.CSV_PATH.read_text(encoding="utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="documents.csv"'},
    )
