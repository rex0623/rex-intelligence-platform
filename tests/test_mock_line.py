"""Tests for the local mock LINE CLI."""

from pathlib import Path

import fitz

from app.core.config import settings
from scripts.mock_line import mock_line_payload


def test_mock_line_pdf_task(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    (pdf_root / "sample1.pdf").write_text("x")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("處理電費單")
    assert output.startswith("小雷收到：已建立電費單處理流程（dry-run）")
    assert "狀態：waiting_approval" in output
    assert "步驟：" in output


def test_mock_line_folder_task(tmp_path, monkeypatch):
    safe_root = tmp_path / "inbox"
    downloads = safe_root / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "example.pdf").write_text("dummy")

    monkeypatch.setattr(settings, "SAFE_FOLDER_ROOT", str(safe_root))

    output = mock_line_payload("整理 Downloads")
    assert output.startswith("小雷收到：資料夾分析完成")
    assert "檔案總數" in output
    assert "pdf 1" in output
    assert "dry-run" in output


def test_mock_line_code_task():
    assert mock_line_payload("幫我寫 API") == "小雷收到：我判斷這是程式開發任務"


def test_mock_line_requirements_task():
    assert mock_line_payload("幫我整理需求") == "小雷收到：我判斷這是需求分析任務"


def test_mock_line_default_task():
    assert mock_line_payload("你好") == "小雷收到：我還不確定你的需求，可以再說清楚一點嗎？"


def _create_pdf(path: Path, content: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()


def test_mock_line_analyze_pdf_no_pdfs(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF")
    assert output.startswith("小雷收到：PDF 智慧分析完成")
    assert "PDF 檔案總數：0" in output


def test_mock_line_analyze_pdf_with_documents(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(pdf_root / "bill.pdf", "Taiwan Power Company electric bill account no. A123 amount due 999")
    _create_pdf(pdf_root / "inv.pdf", "This is an invoice example.")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF")
    assert output.startswith("小雷收到：PDF 智慧分析完成")
    assert "PDF 檔案總數：2" in output
    assert "可讀數量：2" in output
    assert "Document Summary：" in output
    assert "taipower_bill" in output
    assert "invoice" in output


def test_mock_line_analyze_pdf_shows_fields(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / "bill.pdf",
        "Taiwan Power Company electric bill account no. B9876 amount due 2,500",
    )

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF")
    assert "Document Summary：" in output
    assert "電號" in output
    assert "應繳金額" in output


def test_mock_line_analyze_pdf_bypasses_workflow(tmp_path, monkeypatch):
    """「分析 PDF」不走 workflow approval 路徑。"""
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF")
    assert "waiting_approval" not in output
    assert "步驟：" not in output


# ---------------------------------------------------------------------------
# 分析 PDF 詳細
# ---------------------------------------------------------------------------


def test_mock_line_analyze_pdf_detail_header(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert output.startswith("小雷收到：PDF 詳細分析完成")
    assert "dry-run" in output
    assert "PDF 檔案總數：0" in output


def test_mock_line_analyze_pdf_detail_per_file_fields(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / "bill.pdf",
        "Taiwan Power Company electric bill account no. C5555 amount due 3,000",
    )

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert "小雷收到：PDF 詳細分析完成" in output
    assert "bill.pdf" in output
    assert "document_type：taipower_bill" in output
    assert "confidence：" in output
    assert "text_length：" in output
    assert "first_200_chars：" in output
    assert "extracted_fields：" in output
    assert "電號" in output
    assert "應繳金額" in output


def test_mock_line_analyze_pdf_detail_no_fields_label(tmp_path, monkeypatch):
    """可讀但無法萃取欄位的 PDF 顯示「（無）」。"""
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(pdf_root / "misc.pdf", "Some random document with no known fields.")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert "extracted_fields：（無）" in output


def test_mock_line_analyze_pdf_detail_multiple_files(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(pdf_root / "a.pdf", "Taiwan Power Company electric bill account no. A1")
    _create_pdf(pdf_root / "b.pdf", "This is an invoice example.")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert "PDF 檔案總數：2" in output
    assert "1/2" in output
    assert "2/2" in output


def test_mock_line_analyze_pdf_detail_bypasses_workflow(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert "waiting_approval" not in output
    assert "步驟：" not in output


def test_mock_line_analyze_pdf_detail_does_not_trigger_summary(tmp_path, monkeypatch):
    """「分析 PDF 詳細」不應觸發普通 Document Summary 路徑。"""
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("分析 PDF 詳細")
    assert "PDF 詳細分析完成" in output
    assert "PDF 智慧分析完成" not in output
