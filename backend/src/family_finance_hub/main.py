from contextlib import asynccontextmanager
from decimal import Decimal
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from .application.use_cases import ImportDocumentUseCase, ImportFinanceCsvUseCase
from .config import Settings
from .database import Base, make_engine, make_session_factory
from .documents.service import DocumentService
from .finance.service import FinanceCsvImportService
from .models import Document, FinanceTransaction, ImportJob
from .documents.sources import DocumentSourceRegistry, LocalFileDocumentSource
from .documents.sources.ports import DocumentSourceUnavailable
from .storage.local_filesystem import LocalFilesystemStorage


def create_app(settings: Settings | None = None, *, create_schema: bool = False) -> FastAPI:
    config = settings or Settings.from_environment()
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)
    storage = LocalFilesystemStorage(config.storage_root)
    documents = DocumentService(storage)
    document_sources = DocumentSourceRegistry((LocalFileDocumentSource(storage),))
    document_import = ImportDocumentUseCase(documents)
    finance_import = ImportFinanceCsvUseCase(FinanceCsvImportService(documents, document_sources))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.storage_root.mkdir(parents=True, exist_ok=True)
        if create_schema:
            Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="家庭收支記錄 API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "product": "家庭收支記錄"}

    @app.post("/api/documents")
    async def upload_document(file: UploadFile = File(...), session: Session = Depends(get_session)):
        content = await file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件超過上傳大小限制")
        try:
            result = document_import.execute(session, file.filename or "upload", content, "documents")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"id": result.document.id, "filename": result.document.filename, "sha256": result.document.sha256, "duplicate": result.duplicate}

    @app.get("/api/documents")
    def list_documents(session: Session = Depends(get_session)):
        rows = session.scalars(select(Document).order_by(Document.created_at.desc())).all()
        return [{"id": row.id, "filename": row.filename, "content_type": row.content_type, "size_bytes": row.size_bytes, "created_at": row.created_at} for row in rows]

    @app.get("/api/documents/{document_id}/content")
    def get_document_content(document_id: str, session: Session = Depends(get_session)):
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="找不到文件")
        try:
            content = document_sources.read(document)
        except DocumentSourceUnavailable as error:
            raise HTTPException(status_code=503, detail="目前無法取得文件來源") from error
        except OSError as error:
            raise HTTPException(status_code=404, detail="文件內容不存在") from error
        return Response(
            content=content,
            media_type=document.content_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}",
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/finance/import-csv")
    async def import_finance_csv(file: UploadFile = File(...), session: Session = Depends(get_session)):
        content = await file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件超過上傳大小限制")
        try:
            return finance_import.execute(session, file.filename or "upload.csv", content)
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/finance/transactions")
    def list_transactions(session: Session = Depends(get_session)):
        rows = session.scalars(select(FinanceTransaction).order_by(FinanceTransaction.transaction_date.desc(), FinanceTransaction.created_at.desc())).all()
        return [{"id": row.id, "source_document_id": row.source_document_id, "date": row.transaction_date, "description": row.description, "amount": str(row.amount), "currency": row.currency} for row in rows]

    @app.get("/api/dashboard")
    def dashboard(session: Session = Depends(get_session)):
        rows = session.scalars(select(FinanceTransaction)).all()
        totals: dict[str, dict[str, Decimal]] = {}
        for row in rows:
            bucket = totals.setdefault(row.currency, {"income": Decimal("0"), "expenses": Decimal("0")})
            if row.amount >= 0:
                bucket["income"] += row.amount
            else:
                bucket["expenses"] -= row.amount
        return {
            "transaction_count": len(rows),
            "currency_totals": [
                {
                    "currency": currency,
                    "income": str(values["income"].quantize(Decimal("0.01"))),
                    "expenses": str(values["expenses"].quantize(Decimal("0.01"))),
                    "net": str((values["income"] - values["expenses"]).quantize(Decimal("0.01"))),
                }
                for currency, values in sorted(totals.items())
            ],
        }

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=200), session: Session = Depends(get_session)):
        pattern = f"%{q.strip()}%"
        documents = session.scalars(select(Document).where(Document.filename.ilike(pattern)).limit(50)).all()
        transactions = session.scalars(select(FinanceTransaction).where(or_(FinanceTransaction.description.ilike(pattern), cast(FinanceTransaction.amount, String).ilike(pattern))).limit(50)).all()
        return {
            "documents": [{"id": row.id, "filename": row.filename, "content_type": row.content_type} for row in documents],
            "transactions": [{"id": row.id, "source_document_id": row.source_document_id, "date": row.transaction_date, "description": row.description, "amount": str(row.amount), "currency": row.currency} for row in transactions],
        }

    @app.get("/api/jobs")
    def list_jobs(session: Session = Depends(get_session)):
        rows = session.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)).all()
        return [{"id": row.id, "document_id": row.document_id, "source_type": row.source_type, "target_module": row.target_module, "status": row.status, "summary": row.summary, "created_at": row.created_at} for row in rows]

    return app


app = create_app()
