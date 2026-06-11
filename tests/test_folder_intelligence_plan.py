"""Phase 15A 測試：Folder Intelligence / Move Plan Design。

本階段只產生 MovePlan（dry-run、requires approval），不實際搬移：
- 不碰真實 filesystem
- 不建立資料夾
- folder_intelligence 模組不得出現 rename / move / replace 呼叫
"""

import inspect
from pathlib import Path

import pytest

from app.folder_intelligence import (
    MovePlan,
    build_move_plan,
    format_move_plan_for_cli,
    validate_move_plan,
)
from app.folder_intelligence.template import (
    UNCLASSIFIED_FOLDER,
    build_taipower_folder,
    sanitize_folder_segment,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _taipower_doc(
    path: str = "/inbox/bill.pdf",
    business_id: str = "24581234",
    billing_start_date: str = "1150501",
    proposed_filename: str | None = "台電電費單_24581234_03123456789_2026-05_125430.pdf",
) -> dict:
    fields = {}
    if business_id:
        fields["business_id"] = business_id
    if billing_start_date:
        fields["billing_start_date"] = billing_start_date
    doc = {
        "path": path,
        "filename": "bill.pdf",
        "document_type": "taipower_bill",
        "extracted_fields": fields,
    }
    if proposed_filename:
        doc["proposed_filename"] = proposed_filename
    return doc


# ---------------------------------------------------------------------------
# 測試 1：build_move_plan 產生 dry-run、pending_approval 的計畫
# ---------------------------------------------------------------------------


def test_build_move_plan_creates_dry_run_pending_approval_plan():
    plan = build_move_plan([_taipower_doc()])

    assert isinstance(plan, MovePlan)
    assert plan.dry_run is True
    assert plan.status == "pending_approval"
    assert plan.requires_approval is True
    assert plan.total_files == 1
    assert len(plan.candidates) == 1
    assert plan.candidates[0].requires_approval is True
    assert plan.plan_id


# ---------------------------------------------------------------------------
# 測試 2：Taipower bill 對應 電費單/{business_id}/{billing_period}/
# ---------------------------------------------------------------------------


def test_taipower_bill_maps_to_business_period_folder():
    plan = build_move_plan([_taipower_doc()])

    c = plan.candidates[0]
    assert c.proposed_folder == "電費單/24581234/2026-05/"
    assert c.proposed_path == (
        "電費單/24581234/2026-05/台電電費單_24581234_03123456789_2026-05_125430.pdf"
    )
    assert c.confidence == 1.0
    assert c.document_type == "taipower_bill"


# ---------------------------------------------------------------------------
# 測試 3 + 4：proposed_filename 優先；缺失時使用 original_filename
# ---------------------------------------------------------------------------


def test_proposed_filename_takes_priority():
    plan = build_move_plan([_taipower_doc(proposed_filename="renamed.pdf")])
    assert plan.candidates[0].proposed_path == "電費單/24581234/2026-05/renamed.pdf"


def test_original_filename_used_when_no_proposed_filename():
    plan = build_move_plan([_taipower_doc(proposed_filename=None)])
    assert plan.candidates[0].proposed_path == "電費單/24581234/2026-05/bill.pdf"


# ---------------------------------------------------------------------------
# 測試 5 + 6：缺 business_id / billing_period 使用 fallback segment
# ---------------------------------------------------------------------------


def test_missing_business_id_uses_unknown_business():
    plan = build_move_plan([_taipower_doc(business_id="")])

    c = plan.candidates[0]
    assert "unknown-business" in c.proposed_folder
    assert c.proposed_folder == "電費單/unknown-business/2026-05/"
    assert any("unknown-business" in w for w in c.warnings)
    assert c.confidence < 1.0


def test_missing_billing_period_uses_unknown_period():
    plan = build_move_plan([_taipower_doc(billing_start_date="")])

    c = plan.candidates[0]
    assert c.proposed_folder == "電費單/24581234/unknown-period/"
    assert any("unknown-period" in w for w in c.warnings)


# ---------------------------------------------------------------------------
# 測試 7：folder segment 會被 sanitize（不得含 / \\ : 等非法字元）
# ---------------------------------------------------------------------------


def test_folder_segments_are_sanitized():
    assert sanitize_folder_segment("245/812:34") == "24581234"
    assert sanitize_folder_segment("a\\b|c?d") == "abcd"
    assert sanitize_folder_segment("..") == ""
    assert sanitize_folder_segment("  spaced   name  ") == "spaced name"

    folder, _conf, _warnings = build_taipower_folder(
        {"business_id": "245/812:34", "billing_period": "2026-05"}
    )
    assert folder == "電費單/24581234/2026-05/"

    plan = build_move_plan([
        _taipower_doc(business_id="245/812:34", proposed_filename="x.pdf")
    ])
    # folder 內除了結構分隔外不得出現非法字元
    assert plan.candidates[0].proposed_folder.count("/") == 3
    assert ":" not in plan.candidates[0].proposed_folder
    assert "\\" not in plan.candidates[0].proposed_folder


# ---------------------------------------------------------------------------
# 測試 8：unknown document type 對應 未分類/unknown-document/
# ---------------------------------------------------------------------------


def test_unknown_document_type_maps_to_unclassified():
    plan = build_move_plan([
        {"path": "/inbox/mystery.pdf", "filename": "mystery.pdf",
         "document_type": "unknown"},
    ])

    c = plan.candidates[0]
    assert c.proposed_folder == UNCLASSIFIED_FOLDER == "未分類/unknown-document/"
    assert c.confidence == 0.0
    assert c.proposed_path == "未分類/unknown-document/mystery.pdf"


# ---------------------------------------------------------------------------
# 測試 9：完整 Taipower bill → low risk
# ---------------------------------------------------------------------------


def test_validate_low_risk_for_complete_taipower_bill():
    plan = build_move_plan([_taipower_doc()])
    report = validate_move_plan(plan)

    assert report.low_count == 1
    assert report.blocked_count == 0
    assert report.candidates[0].risk_level == "low"
    assert report.candidates[0].issues == []
    assert report.approval_required is True


# ---------------------------------------------------------------------------
# 測試 10：unknown-business / unknown-period → high risk
# ---------------------------------------------------------------------------


def test_validate_high_risk_for_fallback_segments():
    plan = build_move_plan([
        _taipower_doc(business_id=""),
        _taipower_doc(billing_start_date="", proposed_filename="y.pdf"),
    ])
    report = validate_move_plan(plan)

    assert report.high_count == 2
    for cv in report.candidates:
        assert cv.risk_level == "high"
        assert any("fallback segment" in i for i in cv.issues)


# ---------------------------------------------------------------------------
# 測試 11：unknown document type → blocked
# ---------------------------------------------------------------------------


def test_validate_blocked_for_unknown_document_type():
    plan = build_move_plan([
        {"path": "/inbox/mystery.pdf", "filename": "mystery.pdf",
         "document_type": "unknown"},
    ])
    report = validate_move_plan(plan)

    assert report.blocked_count == 1
    assert report.candidates[0].risk_level == "blocked"
    assert any("文件類型未知" in i for i in report.candidates[0].issues)


# ---------------------------------------------------------------------------
# 測試 12：空計畫 → plan_issues
# ---------------------------------------------------------------------------


def test_validate_blocked_for_empty_plan():
    plan = build_move_plan([])
    report = validate_move_plan(plan)

    assert report.candidates == []
    assert any("搬移計畫為空" in i for i in report.plan_issues)
    assert report.approval_required is True


# ---------------------------------------------------------------------------
# 測試 12b：缺少原始路徑 → blocked
# ---------------------------------------------------------------------------


def test_validate_blocked_for_missing_original_path():
    plan = build_move_plan([
        {"filename": "nopath.pdf", "document_type": "taipower_bill",
         "extracted_fields": {"business_id": "24581234", "billing_period": "2026-05"}},
    ])
    report = validate_move_plan(plan)

    assert report.blocked_count == 1
    assert any("缺少原始路徑" in i for i in report.candidates[0].issues)


# ---------------------------------------------------------------------------
# 測試 13：同計畫內 proposed_path 重複 → high
# ---------------------------------------------------------------------------


def test_validate_detects_duplicate_proposed_path():
    doc1 = _taipower_doc(path="/inbox/a.pdf")
    doc2 = _taipower_doc(path="/inbox/b.pdf")  # 相同 folder + 相同 proposed_filename
    plan = build_move_plan([doc1, doc2])
    report = validate_move_plan(plan)

    assert report.candidates[0].risk_level == "low"
    assert report.candidates[1].risk_level == "high"
    assert any("重複" in i for i in report.candidates[1].issues)


# ---------------------------------------------------------------------------
# 測試 13b：proposed_path 與原始路徑相同 → medium
# ---------------------------------------------------------------------------


def test_validate_medium_when_proposed_equals_original():
    doc = _taipower_doc(
        path="電費單/24581234/2026-05/bill.pdf",
        proposed_filename=None,
    )
    plan = build_move_plan([doc])
    report = validate_move_plan(plan)

    assert report.candidates[0].risk_level == "medium"
    assert any("相同" in i for i in report.candidates[0].issues)


# ---------------------------------------------------------------------------
# 測試 13c：信心度分級（<0.7 → high；0.7~0.9 → medium）
# ---------------------------------------------------------------------------


def test_validate_confidence_tiers():
    low_conf = _taipower_doc()
    low_conf["confidence"] = 0.5
    mid_conf = _taipower_doc(path="/inbox/c.pdf", proposed_filename="mid.pdf")
    mid_conf["confidence"] = 0.8
    plan = build_move_plan([low_conf, mid_conf])
    report = validate_move_plan(plan)

    assert report.candidates[0].risk_level == "high"
    assert any("信心度不足" in i for i in report.candidates[0].issues)
    assert report.candidates[1].risk_level == "medium"
    assert any("信心度偏低" in i for i in report.candidates[1].issues)


# ---------------------------------------------------------------------------
# 測試 14：validation_report 可掛上 MovePlan，CLI 輸出包含必要資訊
# ---------------------------------------------------------------------------


def test_validation_report_attaches_to_plan_and_formats():
    plan = build_move_plan([_taipower_doc()])
    plan.validation_report = validate_move_plan(plan)

    assert plan.validation_report.low_count == 1

    output = format_move_plan_for_cli(plan)
    assert "dry-run" in output
    assert "bill.pdf" in output
    assert "電費單/24581234/2026-05/" in output
    assert "信心度：1.00" in output
    assert "風險：low" in output
    assert "尚未實際搬移" in output


# ---------------------------------------------------------------------------
# 測試 15：build_move_plan 不搬移、不建立任何檔案或資料夾
# ---------------------------------------------------------------------------


def test_build_move_plan_does_not_move_files(tmp_path):
    src = tmp_path / "bill.pdf"
    src.write_text("content")

    doc = _taipower_doc(path=str(src))
    plan = build_move_plan([doc])
    plan.validation_report = validate_move_plan(plan)
    format_move_plan_for_cli(plan)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["bill.pdf"], (
        "planning 不可新增/刪除/搬移任何檔案或建立資料夾"
    )
    assert src.read_text() == "content"


# ---------------------------------------------------------------------------
# 測試 16：folder_intelligence 模組不得呼叫 rename / move / replace（AST）
# ---------------------------------------------------------------------------


def test_folder_intelligence_has_no_filesystem_move_calls():
    import ast

    import app.folder_intelligence.formatter as formatter_module
    import app.folder_intelligence.planner as planner_module
    import app.folder_intelligence.schemas as schemas_module
    import app.folder_intelligence.template as template_module
    import app.folder_intelligence.validator as validator_module

    forbidden_imports = {"os", "shutil"}

    for module in (
        planner_module, validator_module, template_module,
        schemas_module, formatter_module,
    ):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports, (
                        f"{module.__name__} 不可 import {alias.name}"
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("rename", "move", "replace", "mkdir"), (
                    f"{module.__name__} 不可呼叫 .{node.func.attr}()"
                )


# ---------------------------------------------------------------------------
# 測試 17：可沿用 rename pipeline 的 pdf_summaries 結構（document_object.fields）
# ---------------------------------------------------------------------------


def test_build_move_plan_accepts_pdf_summary_structure():
    doc = {
        "path": "/inbox/bill.pdf",
        "file_name": "bill.pdf",
        "document_type": "taipower_bill",
        "document_object": {
            "fields": [
                {"name": "business_id", "value": "24581234"},
                {"name": "billing_start_date", "value": "1150501"},
            ]
        },
    }
    plan = build_move_plan([doc])

    c = plan.candidates[0]
    assert c.original_filename == "bill.pdf"
    assert c.proposed_folder == "電費單/24581234/2026-05/"
