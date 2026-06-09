"""Tests for PdfWorker safe analysis mode."""

from pathlib import Path
import asyncio

import fitz
from app.core.config import settings
from app.schemas.messages import WorkerRequest
from app.workers.pdf_worker import PDFWorker


def create_pdf(path: Path, content: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()


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
    create_pdf(pdf_root / "a.pdf", "Taiwan Power Company electric bill sample.")
    create_pdf(pdf_root / "b.pdf", "This is an invoice example.")

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
    payload = data["data"]["data"]
    assert payload["total_pdfs"] == 2
    assert payload["readable_pdfs"] == 2
    assert payload["classification_counts"]["taipower_bill"] == 1
    assert payload["classification_counts"]["invoice"] == 1
    assert {item["file_name"] for item in payload["pdf_summaries"]} == {"a.pdf", "b.pdf"}


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
