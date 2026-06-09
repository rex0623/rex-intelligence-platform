"""Tests for Phase 11/12 Document Intelligence Engine."""

import asyncio
from pathlib import Path

import fitz

from app.core.config import settings
from app.document.classifier import classify_document_type
from app.document.extractor import extract_fields
from app.document.parser import parse_text
from app.document.schemas import Document, DocumentField, DocumentType
from app.schemas.messages import WorkerRequest
from app.workers.pdf_worker import PDFWorker


# ---------------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------------


def test_document_type_enum_values():
    assert DocumentType.taipower_bill == "taipower_bill"
    assert DocumentType.invoice == "invoice"
    assert DocumentType.contract == "contract"
    assert DocumentType.unknown == "unknown"


def test_document_field_default_confidence():
    field = DocumentField(name="電號", value="A123")
    assert field.confidence == 0.0


def test_document_model_defaults():
    doc = Document(document_type=DocumentType.unknown)
    assert doc.fields == []
    assert doc.text == ""
    assert doc.source_file is None
    assert doc.confidence == 0.0


def test_document_model_dump():
    field = DocumentField(name="電號", value="A123", confidence=0.95)
    doc = Document(
        document_type=DocumentType.taipower_bill,
        confidence=0.95,
        fields=[field],
        text="sample",
        source_file="bill.pdf",
    )
    data = doc.model_dump()
    assert data["document_type"] == "taipower_bill"
    assert data["confidence"] == 0.95
    assert data["fields"][0]["name"] == "電號"
    assert data["source_file"] == "bill.pdf"


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def test_parse_text_normalizes_whitespace():
    raw = "hello\t\t  world\r\nfoo  bar"
    result = parse_text(raw)
    assert "\t" not in result
    assert result == "hello world\nfoo bar"


def test_parse_text_collapses_blank_lines():
    raw = "line1\n\n\nline2"
    result = parse_text(raw)
    assert result == "line1\nline2"


def test_parse_text_none_returns_empty():
    assert parse_text(None) == ""


def test_parse_text_empty_returns_empty():
    assert parse_text("") == ""


# ---------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------


def test_classify_taipower_bill_chinese():
    result = classify_document_type("台灣電力公司 電費通知單")
    assert result["document_type"] == DocumentType.taipower_bill
    assert result["confidence"] == 0.95


def test_classify_taipower_bill_english():
    result = classify_document_type("Taiwan Power Company electric bill")
    assert result["document_type"] == DocumentType.taipower_bill
    assert result["confidence"] == 0.95


def test_classify_invoice():
    result = classify_document_type("這是一張發票，請妥善保存")
    assert result["document_type"] == DocumentType.invoice
    assert result["confidence"] == 0.9


def test_classify_invoice_english():
    result = classify_document_type("This is an invoice for services rendered")
    assert result["document_type"] == DocumentType.invoice
    assert result["confidence"] == 0.9


def test_classify_contract():
    result = classify_document_type("本契約由甲乙雙方簽署")
    assert result["document_type"] == DocumentType.contract
    assert result["confidence"] == 0.9


def test_classify_contract_english():
    result = classify_document_type("This contract is entered into by both parties")
    assert result["document_type"] == DocumentType.contract
    assert result["confidence"] == 0.9


# priority: taipower overrides invoice when both signals are present
def test_classify_taipower_beats_invoice_with_購電():
    text = "本公司購電 電費計算 發票資訊 統一發票號碼 AB12345678"
    result = classify_document_type(text)
    assert result["document_type"] == DocumentType.taipower_bill
    assert result["confidence"] == 0.95


def test_classify_taipower_beats_invoice_with_電費通知單():
    text = "電費通知單 發票號碼 AB-12345678 請於期限內繳納"
    result = classify_document_type(text)
    assert result["document_type"] == DocumentType.taipower_bill


def test_classify_taipower_電號_計費期間_combination():
    text = "電號 123456 計費期間 2024-01-01 至 2024-01-31"
    result = classify_document_type(text)
    assert result["document_type"] == DocumentType.taipower_bill
    assert result["confidence"] == 0.95


def test_classify_taipower_購電電費():
    result = classify_document_type("購電電費明細表")
    assert result["document_type"] == DocumentType.taipower_bill


def test_classify_taipower_應付總金額():
    result = classify_document_type("應付總金額 新台幣 1,234 元")
    assert result["document_type"] == DocumentType.taipower_bill


def test_classify_invoice_without_taipower_signals():
    text = "統一發票 買受人 王小明 品名 辦公桌"
    result = classify_document_type(text)
    assert result["document_type"] == DocumentType.invoice


def test_classify_unknown():
    result = classify_document_type("一般文件無法識別類型")
    assert result["document_type"] == DocumentType.unknown
    assert result["confidence"] == 0.5


def test_classify_empty():
    result = classify_document_type("")
    assert result["document_type"] == DocumentType.unknown
    assert result["confidence"] == 0.5


# ---------------------------------------------------------------------------
# extractor
# ---------------------------------------------------------------------------


def test_extract_electric_number():
    text = "電號：A123456789"
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert "電號" in names
    field = next(f for f in fields if f.name == "電號")
    assert "A123456789" in field.value
    assert field.confidence == 0.95


def test_extract_billing_period():
    text = "計費期間：2024-01-01 to 2024-01-31"
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert "計費期間" in names


def test_extract_amount_due():
    text = "應繳金額：1,234.56"
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert "應繳金額" in names
    field = next(f for f in fields if f.name == "應繳金額")
    assert "1,234.56" in field.value


def test_extract_customer_name():
    text = "用戶名稱：王小明"
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert "用戶名稱" in names


def test_extract_address():
    text = "地址：台北市信義區信義路五段7號"
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert "地址" in names


def test_extract_empty_text_returns_no_fields():
    assert extract_fields("") == []


def test_extract_all_fields():
    text = (
        "台灣電力公司 電費通知單\n"
        "電號：A123456789\n"
        "計費期間：2024-01-01\n"
        "應繳金額：1,234\n"
        "用戶名稱：王小明\n"
        "地址：台北市信義區"
    )
    fields = extract_fields(text)
    names = {f.name for f in fields}
    assert {"電號", "計費期間", "應繳金額", "用戶名稱", "地址"}.issubset(names)


# ---------------------------------------------------------------------------
# full pipeline: parse → classify → extract → Document
# ---------------------------------------------------------------------------


def test_full_pipeline_taipower():
    raw = "台灣電力公司 電費通知單\n電號：B9876543\n應繳金額：2,500"
    text = parse_text(raw)
    classification = classify_document_type(text)
    fields = extract_fields(text)
    doc = Document(
        document_type=classification["document_type"],
        confidence=float(classification["confidence"]),
        fields=fields,
        text=text,
        source_file="bill.pdf",
    )
    assert doc.document_type == DocumentType.taipower_bill
    assert doc.confidence == 0.95
    assert any(f.name == "電號" for f in doc.fields)
    assert any(f.name == "應繳金額" for f in doc.fields)


# ---------------------------------------------------------------------------
# PDFWorker.classify_pdf()
# ---------------------------------------------------------------------------


def test_pdf_worker_classify_pdf_taipower():
    worker = PDFWorker()
    result = worker.classify_pdf("台灣電力公司 電費通知單")
    assert result == {"type": "taipower_bill", "confidence": 0.95}


def test_pdf_worker_classify_pdf_invoice():
    worker = PDFWorker()
    result = worker.classify_pdf("這是一張發票")
    assert result == {"type": "invoice", "confidence": 0.9}


def test_pdf_worker_classify_pdf_contract():
    worker = PDFWorker()
    result = worker.classify_pdf("契約內容範例")
    assert result == {"type": "contract", "confidence": 0.9}


def test_pdf_worker_classify_pdf_unknown():
    worker = PDFWorker()
    result = worker.classify_pdf("未知文件類型")
    assert result == {"type": "unknown", "confidence": 0.5}


# ---------------------------------------------------------------------------
# analyze_pdfs includes document_object
# ---------------------------------------------------------------------------


def _create_pdf(path: Path, content: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()


def test_analyze_pdfs_document_objects(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(pdf_root / "bill.pdf", "Taiwan Power Company electric bill account no. A123456 amount due 999")
    _create_pdf(pdf_root / "invoice.pdf", "This is an invoice example.")

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="test_user",
        request_id="ph11",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()
    payload = data["data"]["data"]

    assert payload["total_pdfs"] == 2
    assert payload["readable_pdfs"] == 2
    assert len(payload["document_objects"]) == 2

    types = {d["document_type"] for d in payload["document_objects"]}
    assert "taipower_bill" in types
    assert "invoice" in types

    for doc in payload["document_objects"]:
        assert "fields" in doc
        assert "confidence" in doc
        assert "document_type" in doc
        assert "source_file" in doc


def test_analyze_pdfs_taipower_has_fields(tmp_path, monkeypatch):
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / "bill.pdf",
        "Taiwan Power Company electric bill account no. B9876543 amount due 2,500",
    )

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="test_user",
        request_id="ph11b",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()
    payload = data["data"]["data"]

    docs = payload["document_objects"]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["document_type"] == "taipower_bill"
    field_names = {f["name"] for f in doc["fields"]}
    assert "電號" in field_names
    assert "應繳金額" in field_names


# ---------------------------------------------------------------------------
# Phase 12 — full-width normalization (parser)
# ---------------------------------------------------------------------------


def test_parse_text_converts_fullwidth_digits():
    assert parse_text("１２３456") == "123456"


def test_parse_text_converts_fullwidth_uppercase():
    assert parse_text("ＸＢ") == "XB"


def test_parse_text_converts_fullwidth_lowercase():
    assert parse_text("ａｂｃ") == "abc"


def test_parse_text_converts_ideographic_space():
    result = parse_text("hello　world")  # U+3000 ideographic space
    assert result == "hello world"


def test_parse_text_converts_nbsp():
    result = parse_text("hello world")  # non-breaking space
    assert result == "hello world"


# ---------------------------------------------------------------------------
# Phase 12 — TaiPower bill sample (real text from problem statement)
# ---------------------------------------------------------------------------

# Raw text as it appears in a real TaiPower PDF (full-width chars intact)
_SAMPLE_BILL_RAW = """\
電子帳單
115 03
106
台北市大安區信義路三段１５３號４樓
得禾能源股份有限公司
先生/女士/寶號
115 02 01    115 02 28
基隆區營業處核算（收費）課
２００基隆市仁一路３０１號
基隆市七堵區東新街３號屋頂
0元
115年01-02月
XB17839034
21元
(02)24231156
00423107
42923195
155元
112元
13元
280元"""

_SAMPLE_BILL = parse_text(_SAMPLE_BILL_RAW)
_SAMPLE_FIELDS = {f.name: f for f in extract_fields(_SAMPLE_BILL)}


def test_sample_bill_billing_start_date():
    assert "billing_start_date" in _SAMPLE_FIELDS
    assert _SAMPLE_FIELDS["billing_start_date"].value == "1150201"


def test_sample_bill_billing_end_date():
    assert "billing_end_date" in _SAMPLE_FIELDS
    assert _SAMPLE_FIELDS["billing_end_date"].value == "1150228"


def test_sample_bill_site_address():
    assert "site_address" in _SAMPLE_FIELDS
    site = _SAMPLE_FIELDS["site_address"].value
    assert "基隆市七堵區東新街" in site
    assert "3號" in site


def test_sample_bill_invoice_or_bill_code():
    assert "invoice_or_bill_code" in _SAMPLE_FIELDS
    assert _SAMPLE_FIELDS["invoice_or_bill_code"].value == "XB17839034"


def test_sample_bill_business_id():
    assert "business_id" in _SAMPLE_FIELDS
    assert _SAMPLE_FIELDS["business_id"].value == "42923195"


def test_sample_bill_amount_candidates_contains_all():
    assert "amount_candidates" in _SAMPLE_FIELDS
    amounts_str = _SAMPLE_FIELDS["amount_candidates"].value
    for expected in ["21元", "155元", "112元", "13元", "280元"]:
        assert expected in amounts_str


def test_sample_bill_payable_amount_max_nonzero():
    # amounts = [0,21,155,112,13,280] — no duplicates, max non-zero = 280
    assert "payable_amount" in _SAMPLE_FIELDS
    assert _SAMPLE_FIELDS["payable_amount"].value == "280元"


# ---------------------------------------------------------------------------
# Phase 12 — payable_amount priority rules
# ---------------------------------------------------------------------------


def test_payable_amount_first_nonzero_after_bill_code():
    """Priority 1: first non-zero amount after the bill code."""
    text = "UJ17628390\n983元\n0元\n0元"
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "983元"


def test_payable_amount_skips_leading_zeros_after_code():
    """Priority 1 skips 0元 entries immediately after the bill code."""
    text = "UJ17628391\n0元\n0元\n567元"
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "567元"


def test_payable_amount_falls_back_to_last_nonzero():
    """Priority 2: no bill code present, take the last non-zero amount."""
    text = "155元\n13元\n280元\n0元\n0元"
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "280元"


def test_payable_amount_all_zeros_returns_zero():
    """Fallback: all amounts are 0元."""
    text = "UJ17628390\n0元\n0元"
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "0元"


def test_payable_amount_zero_before_code_nonzero_after():
    """0元 before the bill code must not interfere with post-code selection."""
    text = "0元\n0元\nUJ17628390\n983元"
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "983元"


def test_uj17628390_full_extraction():
    """UJ bill code is extracted and payable_amount is the first non-zero after it."""
    text = (
        "115 02 01 115 02 28\n"
        "基隆市七堵區東新街3號屋頂\n"
        "0元\n"
        "UJ17628390\n"
        "983元\n"
        "0元\n"
        "42923195\n"
    )
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["invoice_or_bill_code"].value == "UJ17628390"
    assert fields["payable_amount"].value == "983元"
    assert "983元" in fields["amount_candidates"].value


def test_uj17628391_trailing_zeros():
    """UJ17628391 variant: trailing zeros must not become payable_amount."""
    text = (
        "115 03 01 115 03 31\n"
        "台北市大安區信義路三段153號4樓\n"
        "UJ17628391\n"
        "1200元\n"
        "0元\n"
        "0元\n"
    )
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["invoice_or_bill_code"].value == "UJ17628391"
    assert fields["payable_amount"].value == "1200元"


# ---------------------------------------------------------------------------
# payable_amount — new priority rules (duplicate > max > zero fallback)
# ---------------------------------------------------------------------------


def _amounts_text(nums: list) -> str:
    """Build a plain text string of 'N元' entries for testing."""
    return "\n".join(f"{n}元" for n in nums)


def test_pick_payable_repeated_value_wins():
    """280 appears twice → repeated non-zero wins."""
    text = _amounts_text([0, 21, 155, 112, 13, 280, 0, 0, 163, 117, 280])
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "280元"


def test_pick_payable_repeated_307():
    """307 appears twice → repeated non-zero wins."""
    text = _amounts_text([0, 21, 155, 137, 15, 307, 0, 0, 163, 144, 307])
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "307元"


def test_pick_payable_no_repeat_max_wins():
    """983 is the only non-zero amount → max (= itself) wins."""
    text = _amounts_text([0, 983, 0, 0, 0])
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "983元"


def test_pick_payable_all_zeros():
    """All amounts are 0 → fallback 0元."""
    text = _amounts_text([0, 0, 0])
    fields = {f.name: f for f in extract_fields(text)}
    assert fields["payable_amount"].value == "0元"


def test_fullwidth_bill_code_via_parse_text():
    """Full-width bill code becomes extractable after parse_text."""
    raw = "ＸＢ１７８３９０３４"
    normalized = parse_text(raw)
    assert normalized == "XB17839034"
    fields = extract_fields(normalized)
    names = {f.name for f in fields}
    assert "invoice_or_bill_code" in names
    code = next(f for f in fields if f.name == "invoice_or_bill_code")
    assert code.value == "XB17839034"


def test_business_id_excludes_phone_number():
    """Phone number like (02)24231156 must not be extracted as business_id."""
    text = parse_text("(02)24231156\n00423107\n42923195")
    fields = extract_fields(text)
    bid = next((f for f in fields if f.name == "business_id"), None)
    assert bid is not None
    assert bid.value == "42923195"
    assert "24231156" not in bid.value


def test_site_address_prefers_site_over_billing_address():
    """When billing address and site address both match, prefer the site address."""
    fields = extract_fields(_SAMPLE_BILL)
    site = next(f for f in fields if f.name == "site_address")
    # Site address (七堵) should win over billing address (大安)
    assert "七堵" in site.value
    assert "大安" not in site.value
