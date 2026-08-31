from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import anyio
import fitz
from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rag_pipeline.api.deps import (
    get_db_session,
    get_paths,
    get_settings,
    require_demo_access,
)
from rag_pipeline.api.schemas.documents import (
    DocumentListOut,
    DocumentOut,
    DocumentStatusOut,
    UploadResponse,
)
from rag_pipeline.core.config import Settings
from rag_pipeline.core.errors import ConflictError, NotFoundError, ValidationError
from rag_pipeline.core.paths import StoragePaths
from rag_pipeline.db.models import DocumentStatus
from rag_pipeline.db.repositories.documents import DocumentRepository
from rag_pipeline.services.documents.ingestion import (
    DocumentIngestionService,
    cleanup_document_artifacts,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_demo_access)])

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
PUBLIC_INGESTION_ERROR = (
    "[ingestion_failed] Document processing failed. "
    "Check provider configuration and retry the document."
)


def _new_document_id() -> str:
    timestamp = int(datetime.now(timezone.utc).timestamp())
    return f"{timestamp}_{secrets.token_hex(4)}"


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "").strip()
    basename = raw.replace("\\", "/").split("/")[-1]
    if not basename or not basename.lower().endswith(".pdf"):
        raise ValidationError(
            "Only PDF uploads are supported.",
            code="upload_type_invalid",
        )
    sanitized = re.sub(r"[^A-Za-z0-9._ -]", "_", basename).strip(" .")
    if not sanitized:
        sanitized = "document.pdf"
    if not sanitized.lower().endswith(".pdf"):
        sanitized += ".pdf"
    return f"{sanitized[:-4][:176]}.pdf"


def _inspect_pdf(path: Path, max_pages: int) -> int:
    try:
        with fitz.open(path) as document:
            if not document.is_pdf:
                raise ValidationError("The uploaded file is not a recognized PDF.", code="pdf_invalid")
            if document.needs_pass:
                raise ValidationError(
                    "Encrypted PDFs are not supported.",
                    code="pdf_encrypted",
                )
            page_count = document.page_count
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            "The uploaded file is not a readable PDF.",
            code="pdf_invalid",
        ) from exc
    if page_count < 1:
        raise ValidationError("The PDF contains no pages.", code="pdf_empty")
    if page_count > max_pages:
        raise ValidationError(
            f"The PDF exceeds the {max_pages}-page limit.",
            code="pdf_page_limit",
            status_code=413,
        )
    return page_count


async def _store_validated_pdf(
    *,
    file: UploadFile,
    destination: Path,
    settings: Settings,
) -> None:
    if (file.content_type or "").lower() not in PDF_CONTENT_TYPES:
        raise ValidationError(
            "The upload MIME type must be application/pdf.",
            code="upload_mime_invalid",
        )

    temporary = destination.with_suffix(".pdf.part")
    total = 0
    signature = b""
    try:
        async with await anyio.open_file(temporary, "wb") as output:
            while chunk := await file.read(settings.upload_chunk_bytes):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise ValidationError(
                        f"The PDF exceeds the {settings.max_upload_bytes}-byte upload limit.",
                        code="upload_too_large",
                        status_code=413,
                    )
                if len(signature) < 5:
                    signature = (signature + chunk)[:5]
                await output.write(chunk)

        if total == 0:
            raise ValidationError("The uploaded file is empty.", code="upload_empty")
        if signature != b"%PDF-":
            raise ValidationError(
                "The uploaded file does not have a valid PDF signature.",
                code="pdf_signature_invalid",
            )
        await anyio.to_thread.run_sync(_inspect_pdf, temporary, settings.max_pdf_pages)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


async def _process_document(
    *,
    document_id: str,
    pdf_path: Path,
    settings: Settings,
    paths: StoragePaths,
    session_factory: async_sessionmaker[AsyncSession],
    semaphore,
) -> None:
    async with semaphore:
        async with session_factory() as session:
            repository = DocumentRepository(session)
            if not await repository.claim_pending(document_id):
                logger.info("Skipped duplicate ingestion request document_id=%s", document_id)
                return

            try:
                ingestion = DocumentIngestionService(settings=settings, paths=paths)
                result = await ingestion.ingest(document_id=document_id, pdf_path=pdf_path)
                await repository.set_status(
                    document_id,
                    status=DocumentStatus.completed,
                    progress=100,
                    message="Document processed successfully.",
                    pages=result["pages"],
                    chunks=result["chunks"],
                    structured_path=result["structured_path"],
                    extracted_text_path=result["extracted_text_path"],
                    index_dir=result["index_dir"],
                )
            except Exception:
                logger.exception("Document ingestion failed document_id=%s", document_id)
                cleanup_document_artifacts(paths=paths, document_id=document_id)
                await repository.set_status(
                    document_id,
                    status=DocumentStatus.failed,
                    progress=100,
                    message=PUBLIC_INGESTION_ERROR,
                    pages=None,
                    chunks=None,
                    structured_path=None,
                    extracted_text_path=None,
                    index_dir=None,
                )


def _schedule_ingestion(
    *,
    background_tasks: BackgroundTasks,
    request: Request,
    document_id: str,
    upload_path: Path,
    settings: Settings,
    paths: StoragePaths,
) -> None:
    background_tasks.add_task(
        _process_document,
        document_id=document_id,
        pdf_path=upload_path,
        settings=settings,
        paths=paths,
        session_factory=request.app.state.session_factory,
        semaphore=request.app.state.ingestion_semaphore,
    )


def _document_out(document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        status=document.status.value,
        progress=document.progress,
        message=document.message,
        pages=document.pages,
        chunks=document.chunks,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("", response_model=UploadResponse, status_code=202)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    paths: StoragePaths = Depends(get_paths),
) -> UploadResponse:
    settings.validate_embedding_config()
    filename = _safe_filename(file.filename)
    document_id = _new_document_id()
    upload_path = paths.uploads_dir / f"{document_id}.pdf"
    await _store_validated_pdf(file=file, destination=upload_path, settings=settings)

    repository = DocumentRepository(session)
    try:
        await repository.create(
            document_id=document_id,
            filename=filename,
            original_filename=filename,
            upload_path=str(upload_path),
        )
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise

    _schedule_ingestion(
        background_tasks=background_tasks,
        request=request,
        document_id=document_id,
        upload_path=upload_path,
        settings=settings,
        paths=paths,
    )
    return UploadResponse(id=document_id, status=DocumentStatus.pending.value)


@router.post("/{document_id}/reprocess", response_model=UploadResponse, status_code=202)
async def reprocess_document(
    document_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
    paths: StoragePaths = Depends(get_paths),
) -> UploadResponse:
    settings.validate_embedding_config()
    repository = DocumentRepository(session)
    document = await repository.get(document_id)
    if not document:
        raise NotFoundError("Document not found.")
    if document.status != DocumentStatus.failed:
        raise ConflictError("Only failed documents can be reprocessed.")

    upload_path = Path(document.upload_path)
    if not upload_path.is_file():
        raise ConflictError("The validated source PDF is unavailable; upload it again.")
    if not await repository.prepare_retry(document_id):
        raise ConflictError("Document retry is already queued or processing.")

    _schedule_ingestion(
        background_tasks=background_tasks,
        request=request,
        document_id=document_id,
        upload_path=upload_path,
        settings=settings,
        paths=paths,
    )
    return UploadResponse(id=document_id, status=DocumentStatus.pending.value)


@router.get("", response_model=DocumentListOut)
async def list_documents(
    session: AsyncSession = Depends(get_db_session),
    limit: int = 50,
    offset: int = 0,
) -> DocumentListOut:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    documents = await DocumentRepository(session).list(limit=limit, offset=offset)
    return DocumentListOut(documents=[_document_out(document) for document in documents])


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    document = await DocumentRepository(session).get(document_id)
    if not document:
        raise NotFoundError("Document not found.")
    return _document_out(document)


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def document_status(
    document_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentStatusOut:
    document = await DocumentRepository(session).get(document_id)
    if not document:
        raise NotFoundError("Document not found.")
    return DocumentStatusOut(
        id=document.id,
        status=document.status.value,
        progress=document.progress,
        message=document.message,
    )
