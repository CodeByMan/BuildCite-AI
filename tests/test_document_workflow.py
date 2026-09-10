from __future__ import annotations

import asyncio
from pathlib import Path

import fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient

from rag_pipeline.api.main import create_app
from rag_pipeline.api.routes import documents
from rag_pipeline.core.config import Settings
from rag_pipeline.db.base import Base
from rag_pipeline.db.models import DocumentStatus
from rag_pipeline.db.repositories.documents import DocumentRepository
from rag_pipeline.db.session import create_engine, create_session_factory
from rag_pipeline.services.documents.ingestion import DocumentIngestionService
from rag_pipeline.services.embeddings.embedder import Embedder
from rag_pipeline.services.embeddings.faiss_store import FaissVectorStore, RetrievedChunk
from rag_pipeline.services.rag.pipeline import RagAnswer, RagPipeline


def make_pdf(*, pages: int = 1, encrypted: bool = False) -> bytes:
    document = fitz.open()
    for page_number in range(1, pages + 1):
        page = document.new_page()
        page.insert_text(
            (72, 72),
            f"Synthetic Karachi community centre - page {page_number}. "
            "Estimated structural package: PKR 2,500,000.",
        )
    if encrypted:
        data = document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner-password",
            user_pw="user-password",
        )
    else:
        data = document.tobytes()
    document.close()
    return data


def build_settings(
    tmp_path: Path,
    *,
    app_mode: str = "local",
    max_upload_bytes: int = 4096,
    max_pdf_pages: int = 2,
) -> Settings:
    return Settings(
        APP_MODE=app_mode,
        LOG_LEVEL="ERROR",
        HOST="127.0.0.1",
        CORS_ORIGINS="http://127.0.0.1:8501",
        ALLOWED_HOSTS="testserver,localhost,127.0.0.1",
        STORAGE_DIR=tmp_path / "data",
        DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        MAX_UPLOAD_BYTES=max_upload_bytes,
        UPLOAD_CHUNK_BYTES=1024,
        MAX_PDF_PAGES=max_pdf_pages,
        OCR_MODE="text_only",
        OPENAI_API_KEY="test-openai-key",
        EMBEDDING_MODEL="test-embedding-model",
        LLM_PROVIDER="openai",
        LLM_MODEL="test-llm-model",
        DEMO_ACCESS_KEY="demo-key-1234567890abcdefgh" if app_mode == "hosted" else "",
        ADMIN_API_KEY="admin-key-0987654321abcdefgh" if app_mode == "hosted" else "",
    )


def install_successful_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ingest(
        self: DocumentIngestionService,
        *,
        document_id: str,
        pdf_path: Path,
    ) -> dict:
        assert pdf_path.is_file()
        structured = self._paths.structured_dir / f"{document_id}.json"
        extracted = self._paths.extracted_text_dir / f"{document_id}.txt"
        index_dir = self._paths.indexes_dir / document_id
        structured.write_text('{"pages": [{"page_number": 1}]}', encoding="utf-8")
        extracted.write_text("Synthetic Karachi structural notes.", encoding="utf-8")
        index_dir.mkdir(parents=True)
        (index_dir / "index.faiss").write_bytes(b"synthetic-index")
        (index_dir / "chunks.jsonl").write_text(
            '{"chunk_id":"p0001_c0000","page_number":1,"text":"steel beam"}\n',
            encoding="utf-8",
        )
        return {
            "pages": 1,
            "chunks": 1,
            "structured_path": str(structured),
            "extracted_text_path": str(extracted),
            "index_dir": str(index_dir),
        }

    monkeypatch.setattr(DocumentIngestionService, "ingest", fake_ingest)


def upload_pdf(
    client: TestClient,
    data: bytes,
    *,
    filename: str = "karachi-centre.pdf",
    content_type: str = "application/pdf",
    headers: dict[str, str] | None = None,
):
    return client.post(
        "/v1/documents",
        files={"file": (filename, data, content_type)},
        headers=headers or {},
    )


def test_upload_runs_once_reaches_completed_and_can_be_queried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    install_successful_ingestion(monkeypatch)
    transitions: list[str] = []
    original_claim = documents.DocumentRepository.claim_pending
    original_set_status = documents.DocumentRepository.set_status

    async def recording_claim(self, document_id: str) -> bool:
        claimed = await original_claim(self, document_id)
        if claimed:
            transitions.append(DocumentStatus.processing.value)
        return claimed

    async def recording_set_status(self, document_id: str, *, status, **kwargs):
        transitions.append(status.value)
        return await original_set_status(self, document_id, status=status, **kwargs)

    async def fake_embed_query(self, text: str) -> np.ndarray:
        return np.array([1.0, 0.0], dtype=np.float32)

    def fake_search(self, *, query_embedding: np.ndarray, top_k: int):
        return [
            RetrievedChunk(
                chunk_id="p0001_c0000",
                page_number=1,
                score=0.99,
                text="The fictional steel package is PKR 2,500,000.",
            )
        ]

    async def fake_answer(self, *, question: str, retrieved, max_tokens: int) -> RagAnswer:
        return RagAnswer(
            answer="The fictional steel package is PKR 2,500,000 [p.1].",
            citations=[
                {
                    "chunk_id": "p0001_c0000",
                    "page_number": 1,
                    "score": 0.99,
                    "excerpt": "The fictional steel package is PKR 2,500,000.",
                }
            ],
        )

    monkeypatch.setattr(documents.DocumentRepository, "claim_pending", recording_claim)
    monkeypatch.setattr(documents.DocumentRepository, "set_status", recording_set_status)
    monkeypatch.setattr(Embedder, "embed_query", fake_embed_query)
    monkeypatch.setattr(FaissVectorStore, "search", fake_search)
    monkeypatch.setattr(RagPipeline, "answer", fake_answer)

    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = upload_pdf(client, make_pdf())
        assert response.status_code == 202
        document_id = response.json()["id"]
        assert response.json()["status"] == "pending"

        status = client.get(f"/v1/documents/{document_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "completed"
        assert transitions == ["processing", "completed"]

        query = client.post(
            f"/v1/documents/{document_id}/query",
            json={"question": "What is the fictional steel package cost?"},
        )
        assert query.status_code == 200
        assert query.json()["citations"][0]["page_number"] == 1

        history = client.get(f"/v1/documents/{document_id}/chat/history")
        assert history.status_code == 200
        assert len(history.json()["history"]) == 2

        duplicate = client.post(f"/v1/documents/{document_id}/reprocess")
        assert duplicate.status_code == 409


def test_query_before_ready_returns_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    async def do_not_process(**kwargs) -> None:
        return None

    monkeypatch.setattr(documents, "_process_document", do_not_process)
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = upload_pdf(client, make_pdf())
        document_id = response.json()["id"]
        status = client.get(f"/v1/documents/{document_id}/status")
        assert status.json()["status"] == "pending"

        query = client.post(
            f"/v1/documents/{document_id}/query",
            json={"question": "Is the document ready?"},
        )
        assert query.status_code == 409
        assert query.json()["message"] == "Document is not ready for queries."


def test_ingestion_failure_is_sanitized_cleans_artifacts_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    attempts = 0

    async def fail_then_succeed(
        self: DocumentIngestionService,
        *,
        document_id: str,
        pdf_path: Path,
    ) -> dict:
        nonlocal attempts
        attempts += 1
        structured = self._paths.structured_dir / f"{document_id}.json"
        extracted = self._paths.extracted_text_dir / f"{document_id}.txt"
        index_dir = self._paths.indexes_dir / document_id
        if attempts == 1:
            structured.write_text("partial", encoding="utf-8")
            extracted.write_text("partial", encoding="utf-8")
            index_dir.mkdir(parents=True)
            (index_dir / "partial").write_text("partial", encoding="utf-8")
            raise RuntimeError("provider payload contained /private/secret.json")
        structured.write_text('{"pages": []}', encoding="utf-8")
        extracted.write_text("Synthetic retry content.", encoding="utf-8")
        index_dir.mkdir(parents=True)
        return {
            "pages": 1,
            "chunks": 1,
            "structured_path": str(structured),
            "extracted_text_path": str(extracted),
            "index_dir": str(index_dir),
        }

    monkeypatch.setattr(DocumentIngestionService, "ingest", fail_then_succeed)
    settings = build_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        response = upload_pdf(client, make_pdf())
        document_id = response.json()["id"]
        failed = client.get(f"/v1/documents/{document_id}/status").json()
        assert failed["status"] == "failed"
        assert failed["message"].startswith("[ingestion_failed]")
        assert "private" not in failed["message"]
        assert not (settings.storage_dir / "structured" / f"{document_id}.json").exists()
        assert not (settings.storage_dir / "extracted_text" / f"{document_id}.txt").exists()
        assert not (settings.storage_dir / "indexes" / document_id).exists()
        assert (settings.storage_dir / "uploads" / f"{document_id}.pdf").is_file()

        retry = client.post(f"/v1/documents/{document_id}/reprocess")
        assert retry.status_code == 202
        completed = client.get(f"/v1/documents/{document_id}/status").json()
        assert completed["status"] == "completed"
        assert attempts == 2


@pytest.mark.parametrize(
    ("filename", "data", "content_type", "expected_code"),
    [
        ("empty.pdf", b"", "application/pdf", "upload_empty"),
        ("notes.pdf", b"not a pdf", "application/pdf", "pdf_signature_invalid"),
        ("notes.pdf", b"%PDF-not-readable", "application/pdf", "pdf_invalid"),
        ("notes.txt", make_pdf(), "application/pdf", "upload_type_invalid"),
        ("notes.pdf", make_pdf(), "text/plain", "upload_mime_invalid"),
        ("encrypted.pdf", make_pdf(encrypted=True), "application/pdf", "pdf_encrypted"),
        ("many-pages.pdf", make_pdf(pages=3), "application/pdf", "pdf_page_limit"),
        ("large.pdf", b"%PDF-" + b"x" * 5000, "application/pdf", "upload_too_large"),
    ],
)
def test_invalid_uploads_leave_no_files_or_records(
    tmp_path: Path,
    filename: str,
    data: bytes,
    content_type: str,
    expected_code: str,
):
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = upload_pdf(
            client,
            data,
            filename=filename,
            content_type=content_type,
        )
        assert response.status_code in {400, 413}
        assert response.json()["code"] == expected_code
        assert client.get("/v1/documents").json()["documents"] == []
        assert list((tmp_path / "data" / "uploads").iterdir()) == []


def test_hosted_access_keys_and_public_health(tmp_path: Path):
    settings = build_settings(tmp_path, app_mode="hosted")
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/admin/health").status_code == 200
        assert client.get("/v1/documents").status_code == 401
        assert (
            client.get("/v1/documents", headers={"X-Demo-Key": "wrong-key"}).status_code
            == 401
        )
        assert (
            client.get(
                "/v1/documents",
                headers={"X-Demo-Key": "demo-key-1234567890abcdefgh"},
            ).status_code
            == 200
        )
        assert client.get("/v1/admin/stats/documents").status_code == 401
        assert (
            client.post(
                "/v1/admin/reset",
                headers={"X-Admin-Key": "wrong-key"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/v1/admin/reset",
                headers={"X-Admin-Key": "admin-key-0987654321abcdefgh"},
            ).status_code
            == 200
        )


@pytest.mark.asyncio
async def test_atomic_claim_prevents_duplicate_processing(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'claim.db'}")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await DocumentRepository(session).create(
            document_id="synthetic-document",
            filename="karachi-centre.pdf",
            original_filename="karachi-centre.pdf",
            upload_path=str(tmp_path / "karachi-centre.pdf"),
        )

    async def claim() -> bool:
        async with session_factory() as session:
            return await DocumentRepository(session).claim_pending("synthetic-document")

    claims = await asyncio.gather(claim(), claim())
    assert sum(claims) == 1
    await engine.dispose()
