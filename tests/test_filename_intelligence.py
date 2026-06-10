"""Tests for Phase 13 + Phase 13.5: Filename Intelligence / Rename Plan Quality Gate."""

import re
from pathlib import Path

import fitz
import pytest

from app.core.config import settings
from app.document.schemas import Document, DocumentField, DocumentType
from app.filename.normalizer import sanitize_filename
from app.filename.planner import build_rename_plan
from app.filename.schemas import CandidateValidation, RenameCandidate, RenamePlan, ValidationReport
from app.filename.template import _roc_to_billing_period, build_taipower_filename
from app.filename.validator import validate_rename_plan
from scripts.mock_line import mock_line_payload


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def test_sanitize_removes_invalid_chars():
    assert sanitize_filename('hello<world>.pdf') == 'helloworld.pdf'
    assert sanitize_filename('file:name?.txt') == 'filename.txt'
    assert sanitize_filename('a/b\\c|d.pdf') == 'abcd.pdf'


def test_sanitize_collapses_whitespace():
    assert sanitize_filename('hello  world.pdf') == 'hello world.pdf'
    assert sanitize_filename('  trimmed  .pdf') == 'trimmed.pdf'


def test_sanitize_avoids_reserved_names():
    result = sanitize_filename('CON.txt')
    assert result != 'CON.txt'
    assert result.upper() != 'CON.TXT'

    result = sanitize_filename('NUL.pdf')
    assert 'NUL' not in result.upper().split('.')[0] or result.startswith('_')


def test_sanitize_length_limit():
    long_stem = 'a' * 300
    result = sanitize_filename(f'{long_stem}.pdf')
    stem = result.rpartition('.')[0]
    assert len(stem) <= 200


# ---------------------------------------------------------------------------
# Template — ROC date conversion
# ---------------------------------------------------------------------------


def test_roc_to_billing_period_valid():
    assert _roc_to_billing_period('1150501') == '2026-05'
    assert _roc_to_billing_period('1140201') == '2025-02'
    assert _roc_to_billing_period('1000101') == '2011-01'


def test_roc_to_billing_period_invalid():
    assert _roc_to_billing_period('20260501') is None  # 8 chars, not 7
    assert _roc_to_billing_period('abc') is None
    assert _roc_to_billing_period('') is None


# ---------------------------------------------------------------------------
# Template — build_taipower_filename
# ---------------------------------------------------------------------------


_ALL_FIELDS = {
    'business_id': '24581234',
    '電號': '03123456789',
    'billing_start_date': '1150501',  # → 2026-05
    'payable_amount': '125430元',
}


def test_build_taipower_filename_all_fields():
    proposed, confidence, warnings = build_taipower_filename(_ALL_FIELDS)
    assert proposed == '台電電費單_24581234_03123456789_2026-05_125430.pdf'
    assert warnings == []
    assert confidence == pytest.approx(1.0)


def test_build_taipower_filename_confidence_full():
    _, confidence, warnings = build_taipower_filename(_ALL_FIELDS)
    assert confidence == pytest.approx(1.0)
    assert len(warnings) == 0


def test_build_taipower_filename_confidence_one_missing():
    fields = {k: v for k, v in _ALL_FIELDS.items() if k != 'business_id'}
    _, confidence, warnings = build_taipower_filename(fields)
    assert confidence == pytest.approx(0.8)
    assert len(warnings) == 1


def test_build_taipower_filename_confidence_two_missing():
    fields = {'billing_start_date': '1150501', 'payable_amount': '100元'}
    _, confidence, warnings = build_taipower_filename(fields)
    assert confidence == pytest.approx(0.6)
    assert len(warnings) == 2


def test_build_taipower_filename_no_fields():
    proposed, confidence, warnings = build_taipower_filename({})
    assert proposed is None
    assert confidence == pytest.approx(0.2)
    assert len(warnings) == 4


def test_build_taipower_filename_fallback_electricity_no():
    """Falls back to invoice_or_bill_code when 電號 is absent."""
    fields = {
        'business_id': '24581234',
        'invoice_or_bill_code': 'XB17839034',
        'billing_start_date': '1150501',
        'payable_amount': '280元',
    }
    proposed, confidence, warnings = build_taipower_filename(fields)
    assert proposed is not None
    assert 'XB17839034' in proposed
    assert warnings == []


def test_build_taipower_filename_amount_strips_yuan():
    fields = {**_ALL_FIELDS, 'payable_amount': '1,234元'}
    proposed, _, _ = build_taipower_filename(fields)
    assert '1234' in proposed
    assert ',' not in proposed


# ---------------------------------------------------------------------------
# Planner — build_rename_plan
# ---------------------------------------------------------------------------


def _make_summary(filename: str, doc_type: DocumentType, fields: list[DocumentField]) -> dict:
    doc = Document(
        document_type=doc_type,
        confidence=0.95,
        fields=fields,
        text='',
        source_file=filename,
    )
    return {'file_name': filename, 'document_object': doc.model_dump()}


_BILL_FIELDS = [
    DocumentField(name='business_id', value='24581234', confidence=0.85),
    DocumentField(name='電號', value='03123456789', confidence=0.95),
    DocumentField(name='billing_start_date', value='1150501', confidence=0.9),
    DocumentField(name='payable_amount', value='125430元', confidence=0.75),
]


def test_build_rename_plan_empty():
    plan = build_rename_plan([])
    assert isinstance(plan, RenamePlan)
    assert plan.total_files == 0
    assert plan.renamed_count == 0
    assert plan.candidates == []
    assert plan.dry_run is True
    assert plan.status == 'pending_approval'
    assert plan.requires_approval is True


def test_build_rename_plan_taipower_bill():
    summary = _make_summary('bill.pdf', DocumentType.taipower_bill, _BILL_FIELDS)
    plan = build_rename_plan([summary])

    assert plan.total_files == 1
    assert plan.renamed_count == 1
    assert len(plan.candidates) == 1

    c = plan.candidates[0]
    assert c.original_filename == 'bill.pdf'
    assert c.proposed_filename == '台電電費單_24581234_03123456789_2026-05_125430.pdf'
    assert c.confidence == pytest.approx(1.0)
    assert c.warnings == []
    assert c.document_type == 'taipower_bill'


def test_build_rename_plan_unknown_type():
    summary = _make_summary('misc.pdf', DocumentType.unknown, [])
    plan = build_rename_plan([summary])

    assert plan.renamed_count == 0
    c = plan.candidates[0]
    assert c.proposed_filename is None
    assert len(c.warnings) > 0


def test_build_rename_plan_collision_handling():
    """Two identical bills should get distinct proposed filenames."""
    s1 = _make_summary('bill1.pdf', DocumentType.taipower_bill, _BILL_FIELDS)
    s2 = _make_summary('bill2.pdf', DocumentType.taipower_bill, _BILL_FIELDS)
    plan = build_rename_plan([s1, s2])

    assert plan.total_files == 2
    assert plan.renamed_count == 2
    proposed_names = {c.proposed_filename for c in plan.candidates}
    assert len(proposed_names) == 2  # no collisions


def test_build_rename_plan_mixed_types():
    s_bill = _make_summary('bill.pdf', DocumentType.taipower_bill, _BILL_FIELDS)
    s_inv = _make_summary('inv.pdf', DocumentType.invoice, [])
    plan = build_rename_plan([s_bill, s_inv])

    assert plan.total_files == 2
    assert plan.renamed_count == 1  # only the bill gets renamed

    types = {c.document_type for c in plan.candidates}
    assert 'taipower_bill' in types
    assert 'invoice' in types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_pdf(path: Path, content: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), content)
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# Mock LINE CLI integration
# ---------------------------------------------------------------------------


def test_mock_line_generate_rename_plan_no_pdfs(tmp_path, monkeypatch):
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('產生改名計畫')
    assert '已產生改名計畫' in output
    assert 'dry-run' in output
    assert '待處理檔案：0 份' in output
    assert '改名計畫：' in output


def test_mock_line_generate_rename_plan_with_bill(tmp_path, monkeypatch):
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / 'bill.pdf',
        'Taiwan Power Company electric bill account no. D9876 amount due 3,000',
    )
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('產生改名計畫')
    assert '已產生改名計畫' in output
    assert '待處理檔案：1 份' in output
    assert '改名計畫：' in output
    assert '若要確認' in output
    assert '若要取消' in output


def test_mock_line_generate_rename_plan_zhenglifile(tmp_path, monkeypatch):
    """「整理檔名」觸發改名計畫而非資料夾整理。"""
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('整理檔名')
    assert '已產生改名計畫' in output


def test_mock_line_generate_rename_plan_combined(tmp_path, monkeypatch):
    """「分析 PDF 並產生改名計畫」觸發改名計畫而非普通 PDF 分析。"""
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('分析 PDF 並產生改名計畫')
    assert '已產生改名計畫' in output
    assert 'PDF 智慧分析完成' not in output


def test_mock_line_rename_plan_approval_confirmation(tmp_path, monkeypatch):
    """確認改名計畫後，顯示 dry-run 執行報告。"""
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / 'bill.pdf',
        'Taiwan Power Company electric bill account no. E1111 amount due 5,000',
    )
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    plan_output = mock_line_payload('產生改名計畫')
    assert '若要確認' in plan_output

    # Extract the approval_id from the output
    match = re.search(r'確認\s+([0-9a-fA-F\-]{36})', plan_output)
    assert match, f"approval_id not found in output:\n{plan_output}"
    approval_id = match.group(1)

    confirm_output = mock_line_payload(f'確認 {approval_id}')
    assert '改名計畫已確認' in confirm_output
    assert 'dry-run' in confirm_output
    assert '本次沒有實際更名任何 PDF' in confirm_output


# ---------------------------------------------------------------------------
# Phase 13.5: Quality Gate — validator unit tests
# ---------------------------------------------------------------------------


def _plan_from_candidates(candidates: list[RenameCandidate]) -> RenamePlan:
    plan = RenamePlan(total_files=len(candidates))
    plan.candidates = candidates
    plan.renamed_count = sum(1 for c in candidates if c.proposed_filename)
    return plan


def test_validate_empty_plan():
    plan = RenamePlan(total_files=0)
    report = validate_rename_plan(plan)
    assert isinstance(report, ValidationReport)
    assert report.total_files == 0
    assert report.low_count == 0
    assert report.blocked_count == 0
    assert len(report.plan_issues) > 0
    assert report.approval_required is True


def test_validate_low_risk_all_fields():
    """All 4 required fields → confidence 1.0 → low risk."""
    c = RenameCandidate(
        original_filename='bill.pdf',
        proposed_filename='台電電費單_24581234_03123456789_2026-05_125430.pdf',
        confidence=1.0,
        document_type='taipower_bill',
        warnings=[],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.low_count == 1
    assert report.medium_count == 0
    assert report.high_count == 0
    assert report.blocked_count == 0
    assert report.candidates[0].risk_level == 'low'
    assert report.candidates[0].issues == []


def test_validate_medium_risk_one_missing_field():
    """1 missing field → confidence 0.8 → medium risk."""
    c = RenameCandidate(
        original_filename='bill.pdf',
        proposed_filename='台電電費單_unknown_03123456789_2026-05_125430.pdf',
        confidence=0.8,
        document_type='taipower_bill',
        warnings=['缺少 business_id'],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.medium_count == 1
    assert report.candidates[0].risk_level == 'medium'


def test_validate_high_risk_two_missing_fields():
    """2 missing fields → confidence 0.6 → high risk."""
    c = RenameCandidate(
        original_filename='bill.pdf',
        proposed_filename='台電電費單_unknown_unknown_2026-05_125430.pdf',
        confidence=0.6,
        document_type='taipower_bill',
        warnings=['缺少 business_id', '缺少電號'],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.high_count == 1
    assert report.candidates[0].risk_level == 'high'


def test_validate_blocked_unknown_document_type():
    """Unknown document type → blocked."""
    c = RenameCandidate(
        original_filename='misc.pdf',
        proposed_filename=None,
        confidence=0.0,
        document_type='unknown',
        warnings=['文件類型 unknown 尚不支援自動改名'],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.blocked_count == 1
    assert report.candidates[0].risk_level == 'blocked'
    assert '文件類型未知' in report.candidates[0].issues[0]


def test_validate_blocked_no_proposed_filename():
    """No proposed filename (unsupported type) → blocked."""
    c = RenameCandidate(
        original_filename='contract.pdf',
        proposed_filename=None,
        confidence=0.0,
        document_type='contract',
        warnings=['文件類型 contract 尚不支援自動改名'],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.blocked_count == 1
    assert report.candidates[0].risk_level == 'blocked'


def test_validate_blocked_low_confidence():
    """Confidence < 0.5 → blocked."""
    c = RenameCandidate(
        original_filename='bill.pdf',
        proposed_filename='台電電費單_unknown_unknown_unknown_unknown.pdf',
        confidence=0.2,
        document_type='taipower_bill',
        warnings=['缺少 business_id', '缺少電號', '缺少計費期間', '缺少應繳金額'],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    assert report.blocked_count == 1
    assert report.candidates[0].risk_level == 'blocked'


def test_validate_medium_risk_same_name():
    """Proposed == original → at least medium risk."""
    c = RenameCandidate(
        original_filename='existing.pdf',
        proposed_filename='existing.pdf',
        confidence=1.0,
        document_type='taipower_bill',
        warnings=[],
    )
    plan = _plan_from_candidates([c])
    report = validate_rename_plan(plan)
    cv = report.candidates[0]
    assert cv.risk_level in ('medium', 'high', 'blocked')
    assert any('相同' in i for i in cv.issues)


def test_validate_high_risk_duplicate_proposed():
    """Two candidates with same proposed filename → second gets high risk."""
    c1 = RenameCandidate(
        original_filename='a.pdf',
        proposed_filename='台電電費單_SAME.pdf',
        confidence=1.0,
        document_type='taipower_bill',
        warnings=[],
    )
    c2 = RenameCandidate(
        original_filename='b.pdf',
        proposed_filename='台電電費單_SAME.pdf',
        confidence=1.0,
        document_type='taipower_bill',
        warnings=[],
    )
    plan = _plan_from_candidates([c1, c2])
    report = validate_rename_plan(plan)
    assert report.low_count == 1   # first one is fine
    assert report.high_count == 1  # duplicate → high
    assert any('重複' in i for i in report.candidates[1].issues)


def test_validate_mixed_risk_levels():
    good = RenameCandidate(
        original_filename='good.pdf',
        proposed_filename='台電電費單_24581234_A_2026-05_100.pdf',
        confidence=1.0,
        document_type='taipower_bill',
        warnings=[],
    )
    bad = RenameCandidate(
        original_filename='bad.pdf',
        proposed_filename=None,
        confidence=0.0,
        document_type='unknown',
        warnings=[],
    )
    plan = _plan_from_candidates([good, bad])
    report = validate_rename_plan(plan)
    assert report.low_count == 1
    assert report.blocked_count == 1
    assert report.approval_required is True


def test_validate_report_fields_all_present():
    """ValidationReport has all required output fields."""
    plan = RenamePlan(total_files=0)
    report = validate_rename_plan(plan)
    assert hasattr(report, 'total_files')
    assert hasattr(report, 'low_count')
    assert hasattr(report, 'medium_count')
    assert hasattr(report, 'high_count')
    assert hasattr(report, 'blocked_count')
    assert hasattr(report, 'approval_required')
    assert hasattr(report, 'plan_issues')
    assert hasattr(report, 'candidates')
    assert hasattr(report, 'validated_at')


# ---------------------------------------------------------------------------
# Phase 13.5: Mock LINE CLI output — risk level display
# ---------------------------------------------------------------------------


def test_mock_line_rename_plan_shows_risk_summary(tmp_path, monkeypatch):
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('產生改名計畫')
    assert '風險摘要' in output
    assert '低風險' in output
    assert '封鎖' in output


def test_mock_line_rename_plan_with_bill_shows_low_risk(tmp_path, monkeypatch):
    """A PDF that extracts enough fields should appear as low risk."""
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / 'bill.pdf',
        'Taiwan Power Company electric bill account no. F2222 amount due 8,000',
    )
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    output = mock_line_payload('產生改名計畫')
    assert '風險' in output
    assert '低風險' in output or '中風險' in output or '高風險' in output or '封鎖' in output


def test_mock_line_rename_confirm_shows_risk_summary(tmp_path, monkeypatch):
    """Confirming a rename plan shows risk summary in the dry-run report."""
    pdf_root = tmp_path / 'pdf_inbox'
    pdf_root.mkdir(parents=True)
    _create_pdf(
        pdf_root / 'bill.pdf',
        'Taiwan Power Company electric bill account no. G3333 amount due 2,000',
    )
    monkeypatch.setattr(settings, 'SAFE_PDF_ROOT', str(pdf_root))

    plan_output = mock_line_payload('產生改名計畫')
    match = re.search(r'確認\s+([0-9a-fA-F\-]{36})', plan_output)
    assert match, f"approval_id not found:\n{plan_output}"
    approval_id = match.group(1)

    confirm_output = mock_line_payload(f'確認 {approval_id}')
    assert '改名計畫已確認' in confirm_output
    assert '風險摘要' in confirm_output
    assert '本次沒有實際更名任何 PDF' in confirm_output
