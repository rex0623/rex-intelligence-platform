"""Phase 14D-1 測試：Approval-to-Execution Bridge。

所有涉及真實檔案系統操作的測試，一律使用 pytest tmp_path，
不修改任何真實專案檔案。
"""

import inspect
from pathlib import Path

import pytest

import app.filename.approval_bridge as approval_bridge_module
from app.filename.approval_bridge import (
    execute_approved_rename_by_plan_id,
    execute_approved_rename_plan,
)
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    ValidationReport,
)
from app.filename.transaction_log import RenameTransactionLog


# ---------------------------------------------------------------------------
# 測試輔助函式
# ---------------------------------------------------------------------------


def _make_plan(
    candidates: list[RenameCandidate],
    risk_levels: list[str],
    status: str = "approved",
) -> RenamePlan:
    """建立帶有完整 ValidationReport 的 RenamePlan。"""
    plan = RenamePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)

    cv_list = [
        CandidateValidation(
            original_filename=c.original_filename,
            proposed_filename=c.proposed_filename,
            risk_level=rl,
        )
        for c, rl in zip(candidates, risk_levels)
    ]
    plan.validation_report = ValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
        candidates=cv_list,
    )
    return plan


def _candidate(tmp_path: Path, orig: str, proposed: str, confidence: float = 1.0) -> RenameCandidate:
    return RenameCandidate(
        original_filename=str(tmp_path / orig),
        proposed_filename=str(tmp_path / proposed),
        confidence=confidence,
        document_type="taipower_bill",
    )


def _write_file(path: Path, content: str = "dummy") -> Path:
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# 測試 1：拒絕非 approved plan，不更名
# ---------------------------------------------------------------------------


def test_bridge_rejects_non_approved_plan(tmp_path):
    c = _candidate(tmp_path, "source.pdf", "renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"], status="pending_approval")

    result = execute_approved_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is False
    assert result.success_count == 0
    assert all(r.reason == "plan_not_approved" for r in result.results)
    assert Path(c.original_filename).exists(), "原始檔案不應被更名"
    assert not Path(c.proposed_filename).exists()


# ---------------------------------------------------------------------------
# 測試 2：拒絕缺少 validation_report 的 plan，不更名
# ---------------------------------------------------------------------------


def test_bridge_rejects_missing_validation_report(tmp_path):
    c = _candidate(tmp_path, "source.pdf", "renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = RenamePlan(total_files=1, status="approved")
    plan.candidates = [c]
    # 刻意不設定 validation_report

    result = execute_approved_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is False
    assert result.success_count == 0
    assert all(r.reason == "missing_validation_report" for r in result.results)
    assert Path(c.original_filename).exists()


# ---------------------------------------------------------------------------
# 測試 3：拒絕 blocked_count > 0 的 plan，不更名
# ---------------------------------------------------------------------------


def test_bridge_rejects_validation_report_with_blocked_candidates(tmp_path):
    good = _candidate(tmp_path, "good.pdf", "good_renamed.pdf")
    bad = RenameCandidate(
        original_filename=str(tmp_path / "bad.pdf"),
        proposed_filename=None,
        confidence=0.1,
        document_type="unknown",
    )
    _write_file(Path(good.original_filename))
    plan = _make_plan([good, bad], ["low", "blocked"])

    result = execute_approved_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is False
    assert result.success_count == 0
    assert all(r.reason == "validation_has_blocked_candidates" for r in result.results)
    assert Path(good.original_filename).exists(), "good 檔案不應被更名"


# ---------------------------------------------------------------------------
# 測試 4：approved 低風險 plan，成功執行更名
# ---------------------------------------------------------------------------


def test_bridge_executes_approved_low_risk_plan(tmp_path):
    c = _candidate(tmp_path, "bill.pdf", "台電電費單_2026-05.pdf")
    _write_file(Path(c.original_filename), "pdf content")
    plan = _make_plan([c], ["low"])

    result = execute_approved_rename_plan(plan)

    assert result.executed is True
    assert result.dry_run is False
    assert result.success_count == 1
    assert result.failed_count == 0
    assert not Path(c.original_filename).exists(), "原始路徑應已消失"
    assert Path(c.proposed_filename).exists(), "目標路徑應已存在"


# ---------------------------------------------------------------------------
# 測試 5：approved 中風險 plan，成功執行更名
# ---------------------------------------------------------------------------


def test_bridge_executes_approved_medium_risk_plan(tmp_path):
    c = _candidate(tmp_path, "medium.pdf", "medium_renamed.pdf", confidence=0.8)
    _write_file(Path(c.original_filename), "pdf content")
    plan = _make_plan([c], ["medium"])

    result = execute_approved_rename_plan(plan)

    assert result.executed is True
    assert result.success_count == 1
    assert Path(c.proposed_filename).exists()


# ---------------------------------------------------------------------------
# 測試 6：高風險候選項由 executor 行為跳過，不更名
# ---------------------------------------------------------------------------


def test_bridge_skips_high_risk_candidate_via_executor(tmp_path):
    c = _candidate(tmp_path, "risky.pdf", "risky_renamed.pdf", confidence=0.6)
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["high"])

    result = execute_approved_rename_plan(plan)

    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "high_risk_requires_manual_review"
    assert Path(c.original_filename).exists(), "高風險檔案不應被更名"


# ---------------------------------------------------------------------------
# 測試 7：提供 transaction_log 時，交易寫入 log
# ---------------------------------------------------------------------------


def test_bridge_writes_transaction_log_when_provided(tmp_path):
    c = _candidate(tmp_path, "logged.pdf", "logged_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log_path = tmp_path / "logs" / "transactions.json"
    log = RenameTransactionLog(log_path)

    result = execute_approved_rename_plan(plan, transaction_log=log)

    assert result.success_count == 1
    transactions = log.list_transactions()
    assert len(transactions) == 1
    tx = transactions[0]
    assert tx.plan_id == plan.plan_id
    assert len(tx.actions) == 1
    assert tx.actions[0].status == "success"
    assert tx.actions[0].original_path == c.original_filename
    assert tx.actions[0].new_path == c.proposed_filename


# ---------------------------------------------------------------------------
# 測試 8：bridge 模組原始碼不直接呼叫 Path.rename / os.rename / shutil.move
# ---------------------------------------------------------------------------


def test_bridge_does_not_directly_call_rename():
    import ast

    source = inspect.getsource(approval_bridge_module)
    tree = ast.parse(source)

    forbidden_imports = {"os", "shutil"}
    called_names: set[str] = set()

    for node in ast.walk(tree):
        # 不可 import os / shutil
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_imports, (
                    f"bridge 不可 import {alias.name}"
                )
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_imports, (
                f"bridge 不可 from {node.module} import"
            )
        # 不可呼叫任何 .rename(...) / .move(...) 方法
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("rename", "move", "replace"), (
                    f"bridge 不可直接呼叫 .{node.func.attr}()"
                )
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

    # 真實執行必須透過 execute_rename_plan
    assert "execute_rename_plan" in called_names


# ---------------------------------------------------------------------------
# 測試 8b：bridge 確實委派給 execute_rename_plan（monkeypatch 驗證）
# ---------------------------------------------------------------------------


def test_bridge_delegates_to_execute_rename_plan(tmp_path, monkeypatch):
    c = _candidate(tmp_path, "delegate.pdf", "delegate_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    calls = {}

    def fake_execute(p, transaction_log=None):
        calls["plan_id"] = p.plan_id
        calls["transaction_log"] = transaction_log
        from app.filename.executor import execute_rename_plan as real
        return real(p, transaction_log=transaction_log)

    monkeypatch.setattr(approval_bridge_module, "execute_rename_plan", fake_execute)

    result = execute_approved_rename_plan(plan)

    assert calls["plan_id"] == plan.plan_id
    assert result.success_count == 1


# ---------------------------------------------------------------------------
# 測試 9：Mock LINE 通用指令行為不受 bridge 影響，仍走 dry-run
# ---------------------------------------------------------------------------


def test_bridge_does_not_affect_generic_mock_line_behavior(tmp_path, monkeypatch):
    from app.core.config import settings
    from scripts.mock_line import mock_line_payload

    # Phase 14D-2 起 Mock LINE 接入 approval bridge，但僅限明確
    # 「確認改名 {approval_id}」指令；通用改名指令仍不可觸發真實更名。
    import scripts.mock_line as mock_line_module
    assert hasattr(mock_line_module, "_CONFIRM_RENAME_PATTERN"), (
        "真實更名必須限定於明確確認指令格式"
    )

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()

    import fitz
    pdf_path = pdf_root / "bill.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Taiwan Power Company electric bill amount due 1000")
    doc.save(str(pdf_path))
    doc.close()

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("產生改名計畫")
    assert "dry-run" in output or "dry_run" in output
    assert pdf_path.exists(), "Mock LINE 通用指令不應觸發真實更名"
    assert len(set(pdf_root.glob("*.pdf"))) == 1


# ---------------------------------------------------------------------------
# 測試 10：plan_id helper — loader 回傳 None 時回報 plan_not_found
# ---------------------------------------------------------------------------


def test_plan_id_helper_returns_plan_not_found_when_loader_returns_none():
    result = execute_approved_rename_by_plan_id(
        "missing-plan-id",
        plan_loader=lambda plan_id: None,
    )

    assert result.executed is False
    assert result.dry_run is False
    assert result.plan_id == "missing-plan-id"
    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].reason == "plan_not_found"


# ---------------------------------------------------------------------------
# 測試 11：plan_id helper — loader 回傳 approved plan 時成功執行
# ---------------------------------------------------------------------------


def test_plan_id_helper_executes_when_loader_returns_approved_plan(tmp_path):
    c = _candidate(tmp_path, "via_id.pdf", "via_id_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    store = {plan.plan_id: plan}

    result = execute_approved_rename_by_plan_id(
        plan.plan_id,
        plan_loader=lambda plan_id: store.get(plan_id),
    )

    assert result.executed is True
    assert result.success_count == 1
    assert Path(c.proposed_filename).exists()


# ---------------------------------------------------------------------------
# 測試 11b：plan_id helper — loader 回傳非 approved plan 時拒絕
# ---------------------------------------------------------------------------


def test_plan_id_helper_rejects_non_approved_plan(tmp_path):
    c = _candidate(tmp_path, "pending.pdf", "pending_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"], status="pending_approval")

    result = execute_approved_rename_by_plan_id(
        plan.plan_id,
        plan_loader=lambda plan_id: plan,
    )

    assert result.executed is False
    assert all(r.reason == "plan_not_approved" for r in result.results)
    assert Path(c.original_filename).exists()


# ---------------------------------------------------------------------------
# 測試 12：plan_id helper 支援 transaction_log
# ---------------------------------------------------------------------------


def test_plan_id_helper_passes_transaction_log(tmp_path):
    c = _candidate(tmp_path, "tx.pdf", "tx_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx_log.json")

    result = execute_approved_rename_by_plan_id(
        plan.plan_id,
        plan_loader=lambda plan_id: plan,
        transaction_log=log,
    )

    assert result.success_count == 1
    assert len(log.list_transactions()) == 1


# ---------------------------------------------------------------------------
# 測試 13：拒絕時不應呼叫 execute_rename_plan
# ---------------------------------------------------------------------------


def test_bridge_rejection_does_not_call_executor(tmp_path, monkeypatch):
    c = _candidate(tmp_path, "guard.pdf", "guard_renamed.pdf")
    _write_file(Path(c.original_filename))

    def explode(*args, **kwargs):
        raise AssertionError("拒絕時不應呼叫 execute_rename_plan")

    monkeypatch.setattr(approval_bridge_module, "execute_rename_plan", explode)

    # 非 approved
    plan = _make_plan([c], ["low"], status="pending_approval")
    result = execute_approved_rename_plan(plan)
    assert result.executed is False

    # 缺 validation_report
    plan2 = RenamePlan(total_files=1, status="approved")
    plan2.candidates = [c]
    result2 = execute_approved_rename_plan(plan2)
    assert result2.executed is False

    # blocked_count > 0
    plan3 = _make_plan([c], ["blocked"])
    result3 = execute_approved_rename_plan(plan3)
    assert result3.executed is False

    assert Path(c.original_filename).exists(), "檔案不應被更名"
