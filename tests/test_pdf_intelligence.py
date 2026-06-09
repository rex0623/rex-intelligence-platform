"""Tests for PDF Intelligence Engine v1."""

import asyncio
from pathlib import Path

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


def test_pdf_intelligence_classification_rules():
    worker = PDFWorker()

    assert worker.classify_pdf("台灣電力公司 發票 電費通知單") == {
        "type": "taipower_bill",
        "confidence": 0.95,
    }
    assert worker.classify_pdf("這是一張發票") == {
        "type": "invoice",
        "confidence": 0.9,
    }
    assert worker.classify_pdf("契約內容範例") == {
        "type": "contract",
        "confidence": 0.9,
    }
    assert worker.classify_pdf("未知文件類型") == {
        "type": "unknown",
        "confidence": 0.5,
    }


def test_pdf_intelligence_analysis_report(tmp_path: Path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    create_pdf(pdf_root / "bill.pdf", "Taiwan Power Company electric bill sample.")
    create_pdf(pdf_root / "invoice.pdf", "This is an invoice example.")

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
    payload = data["data"]["data"]

    assert payload["total_pdfs"] == 2
    assert payload["readable_pdfs"] == 2
    assert payload["classification_counts"]["taipower_bill"] == 1
    assert payload["classification_counts"]["invoice"] == 1
    assert len(payload["pdf_summaries"]) == 2
    for summary in payload["pdf_summaries"]:
        assert summary["file_size"] > 0
        assert summary["page_count"] == 1
        assert isinstance(summary["first_200_chars"], str)
        assert summary["text_length"] >= 0
