"""Tests for PdfWorker safe analysis mode."""

from pathlib import Path
import asyncio

from app.core.config import settings
from app.schemas.messages import WorkerRequest
from app.workers.pdf_worker import PDFWorker


def test_pdf_worker_no_pdfs(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="test_user",
        request_id="1",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "success"
    assert data["data"]["data"]["total_pdfs"] == 0


def test_pdf_worker_with_pdfs(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    (pdf_root / "a.pdf").write_text("x")
    (pdf_root / "b.pdf").write_text("x")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="test_user",
        request_id="2",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "success"
    assert data["data"]["data"]["total_pdfs"] == 2
    assert set(data["data"]["data"]["pdf_files"]) == {"a.pdf", "b.pdf"}


def test_pdf_worker_rejects_outside_home(tmp_path, monkeypatch):
    # ensure worker will not scan home or root
    forbidden = Path("/")
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(forbidden))

    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="test_user",
        request_id="3",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "error"
