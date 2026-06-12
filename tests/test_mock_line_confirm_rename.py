"""Phase 14D-2 測試：Explicit Mock LINE Confirm Rename Command。

所有涉及真實檔案系統操作的測試，一律使用 pytest tmp_path，
不修改任何真實專案檔案（approval store 與 transaction log 均隔離到 tmp_path）。
"""

import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.approvals.manager import approval_manager
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    ValidationReport,
)
from app.filename.transaction_log import RenameTransactionLog


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    """將全域 approval_manager 隔離到 tmp_path，避免污染 runtime/approvals.json。"""
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


def _make_plan(
    candidates: list[RenameCandidate],
    risk_levels: list[str],
) -> RenamePlan:
    """建立帶有完整 ValidationReport 的 RenamePlan（status 維持 pending_approval）。"""
    plan = RenamePlan(total_files=len(candidates))
    plan.candidates = list(candidates)
    plan.validation_report = ValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
        candidates=[
            CandidateValidation(
                original_filename=c.original_filename,
                proposed_filename=c.proposed_filename,
                risk_level=rl,
            )
            for c, rl in zip(candidates, risk_levels)
        ],
    )
    return plan


def _candidate(tmp_path: Path, orig: str, proposed: str) -> RenameCandidate:
    return RenameCandidate(
        original_filename=str(tmp_path / orig),
        proposed_filename=str(tmp_path / proposed),
        confidence=1.0,
        document_type="taipower_bill",
    )


def _approved_rename_approval(plan: RenamePlan, manager) -> str:
    """建立 approval（payload 為 plan dict）並核准，回傳 approval_id。"""
    approval = manager.create_approval(plan.model_dump())
    manager.approve(approval.approval_id)
    return approval.approval_id


# ---------------------------------------------------------------------------
# 測試 1：「整理檔名」不會觸發真實 rename
# ---------------------------------------------------------------------------


def test_rename_planning_keyword_does_not_trigger_real_rename(
    tmp_path, monkeypatch, isolated_approvals
):
    from app.core.config import settings

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

    output = mock_line_payload("整理檔名")

    assert "dry-run" in output or "dry_run" in output
    assert pdf_path.exists(), "「整理檔名」不應觸發真實更名"
    assert len(set(pdf_root.glob("*.pdf"))) == 1
    # 輸出應提示明確確認改名指令格式
    assert "確認改名" in output


# ---------------------------------------------------------------------------
# 測試 2：「確認」等模糊文字不會觸發真實 rename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vague_text", ["確認", "好", "OK", "執行", "確認改名"])
def test_vague_confirmation_does_not_trigger_real_rename(
    vague_text, tmp_path, isolated_approvals
):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    _approved_rename_approval(plan, isolated_approvals)

    output = mock_line_payload(vague_text)

    assert "已執行改名" not in output, f"「{vague_text}」不應觸發真實更名"
    assert (tmp_path / "bill.pdf").exists(), f"「{vague_text}」不應更名檔案"
    assert not (tmp_path / "renamed.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 3：「確認改名」沒有 approval_id 不會觸發（已含於測試 2 的 parametrize），
#         這裡額外驗證帶多餘文字也不會觸發
# ---------------------------------------------------------------------------


def test_confirm_rename_with_extra_text_does_not_trigger(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    # 格式不完全符合「確認改名 + 空白 + approval_id」→ 不可觸發
    for text in [
        f"請確認改名 {approval_id}",
        f"確認改名 {approval_id} 謝謝",
        f"確認改名{approval_id}",
    ]:
        output = mock_line_payload(text)
        assert "已執行改名" not in output, f"「{text}」不應觸發真實更名"
        assert (tmp_path / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 4：「確認改名 unknown_id」回覆找不到 approval
# ---------------------------------------------------------------------------


def test_confirm_rename_unknown_approval_id(isolated_approvals):
    output = mock_line_payload("確認改名 unknown_id")

    assert "找不到 approval" in output
    assert "unknown_id" in output
    assert "已執行改名" not in output


# ---------------------------------------------------------------------------
# 測試 5：approval 尚未核准時不執行 rename
# ---------------------------------------------------------------------------


def test_confirm_rename_pending_approval_not_executed(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval = isolated_approvals.create_approval(plan.model_dump())
    # 刻意不 approve

    output = mock_line_payload(f"確認改名 {approval.approval_id}")

    assert "尚未核准" in output
    assert "已執行改名" not in output
    assert (tmp_path / "bill.pdf").exists(), "未核准的 approval 不應觸發更名"
    assert not (tmp_path / "renamed.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 6：approval 不是 rename plan 時不執行 rename
# ---------------------------------------------------------------------------


def test_confirm_rename_non_rename_plan_payload(isolated_approvals):
    workflow_payload = {
        "workflow_id": "wf-123",
        "workflow_type": "pdf_bill",
        "steps": [{"name": "讀取 PDF"}],
    }
    approval = isolated_approvals.create_approval(workflow_payload)
    isolated_approvals.approve(approval.approval_id)

    output = mock_line_payload(f"確認改名 {approval.approval_id}")

    assert "不是改名計畫" in output
    assert "已執行改名" not in output


# ---------------------------------------------------------------------------
# 測試 7 + 8 + 9 + 10：approved rename plan 可透過「確認改名 {approval_id}」執行，
#   使用 tmp_path，transaction log 寫入測試指定路徑，回覆包含統計
# ---------------------------------------------------------------------------


def test_confirm_rename_executes_approved_plan(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "bill.pdf", "台電電費單_2026-05.pdf")
    (tmp_path / "bill.pdf").write_text("pdf content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "rename_transactions.json")

    output = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    # 真實更名已發生
    assert "已執行改名" in output
    assert not (tmp_path / "bill.pdf").exists(), "原始檔案應已更名"
    assert (tmp_path / "台電電費單_2026-05.pdf").exists()

    # 回覆包含統計
    assert "成功：1 筆" in output
    assert "失敗：0 筆" in output
    assert "跳過：0 筆" in output
    assert "blocked：0 筆" in output

    # transaction log 已寫入測試指定路徑
    transactions = log.list_transactions()
    assert len(transactions) == 1
    assert transactions[0].plan_id == plan.plan_id
    assert transactions[0].actions[0].status == "success"
    assert transactions[0].transaction_id in output, "回覆應包含 transaction_id"


# ---------------------------------------------------------------------------
# 測試 9b：未注入 transaction_log 時，使用預設 runtime 路徑（monkeypatch 到 tmp_path）
# ---------------------------------------------------------------------------


def test_confirm_rename_uses_default_log_path(tmp_path, monkeypatch, isolated_approvals):
    """16B 起預設路徑由 settings 取得：monkeypatch settings.RUNTIME_DIR 即可隔離。"""
    from app.core.config import settings

    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(runtime_dir))
    default_log_path = runtime_dir / "rename_transactions.json"
    assert not default_log_path.parent.exists(), "runtime 目錄測試前不應存在"

    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    output = mock_line_payload(f"確認改名 {approval_id}")

    assert "已執行改名" in output
    assert default_log_path.exists(), "transaction log 應自動建立目錄並寫入預設路徑"
    log = RenameTransactionLog(default_log_path)
    assert len(log.list_transactions()) == 1


# ---------------------------------------------------------------------------
# 測試 11：blocked rename plan 不會執行
# ---------------------------------------------------------------------------


def test_confirm_rename_blocked_plan_not_executed(tmp_path, isolated_approvals):
    good = _candidate(tmp_path, "good.pdf", "good_renamed.pdf")
    bad = RenameCandidate(
        original_filename=str(tmp_path / "bad.pdf"),
        proposed_filename=None,
        confidence=0.1,
        document_type="unknown",
    )
    (tmp_path / "good.pdf").write_text("content")
    plan = _make_plan([good, bad], ["low", "blocked"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    output = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    assert "blocked candidate" in output
    assert "已執行改名" not in output
    assert (tmp_path / "good.pdf").exists(), "blocked plan 不應更名任何檔案"
    assert not (tmp_path / "good_renamed.pdf").exists()
    assert log.list_transactions() == [], "blocked plan 不應寫入 transaction"


# ---------------------------------------------------------------------------
# 測試 11b：validation_report 缺失時不執行
# ---------------------------------------------------------------------------


def test_confirm_rename_missing_validation_report_not_executed(
    tmp_path, isolated_approvals
):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = RenamePlan(total_files=1)
    plan.candidates = [c]
    # 刻意不設定 validation_report
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    output = mock_line_payload(f"確認改名 {approval_id}")

    assert "validation_report" in output
    assert "已執行改名" not in output
    assert (tmp_path / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 12：high-risk candidate 仍由 executor 跳過
# ---------------------------------------------------------------------------


def test_confirm_rename_skips_high_risk_candidate(tmp_path, isolated_approvals):
    c_low = _candidate(tmp_path, "low.pdf", "low_renamed.pdf")
    c_high = _candidate(tmp_path, "high.pdf", "high_renamed.pdf")
    (tmp_path / "low.pdf").write_text("content")
    (tmp_path / "high.pdf").write_text("content")
    plan = _make_plan([c_low, c_high], ["low", "high"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    output = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    assert "已執行改名" in output
    assert "成功：1 筆" in output
    assert "跳過：1 筆" in output
    assert (tmp_path / "low_renamed.pdf").exists(), "低風險應更名"
    assert (tmp_path / "high.pdf").exists(), "高風險不應更名"
    assert not (tmp_path / "high_renamed.pdf").exists()
    assert "high_risk_requires_manual_review" in output


# ---------------------------------------------------------------------------
# 測試 13：Mock LINE 不直接呼叫 Path.rename（AST 驗證）
# ---------------------------------------------------------------------------


def test_mock_line_does_not_directly_call_rename():
    import ast

    source = inspect.getsource(mock_line_module)
    tree = ast.parse(source)

    forbidden_imports = {"os", "shutil"}
    called_names: set[str] = set()
    called_attrs: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_imports, (
                    f"mock_line 不可 import {alias.name}"
                )
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called_attrs.add(node.func.attr)
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

    assert "rename" not in called_attrs, "mock_line 不可直接呼叫 .rename()"
    assert "move" not in called_attrs, "mock_line 不可直接呼叫 .move()"
    assert "replace" not in called_attrs, "mock_line 不可直接呼叫 .replace()"
    # 真實執行必須透過 approval bridge
    assert "execute_approved_rename_plan" in called_names


# ---------------------------------------------------------------------------
# 測試 14：失敗候選（目標已存在）回覆原因
# ---------------------------------------------------------------------------


def test_confirm_rename_reports_target_exists_failure(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "orig.pdf", "target.pdf")
    (tmp_path / "orig.pdf").write_text("content")
    (tmp_path / "target.pdf").write_text("existing")  # 目標已存在
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    output = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    assert "失敗：1 筆" in output
    assert "target_file_already_exists" in output
    assert (tmp_path / "orig.pdf").exists(), "失敗時原始檔案不應被動到"
    assert (tmp_path / "target.pdf").read_text() == "existing", "既有目標檔案不可被覆寫"


# ---------------------------------------------------------------------------
# 測試 15：已核准後重複執行第二次，once-only guard 擋下（Phase 14E）
# ---------------------------------------------------------------------------


def test_confirm_rename_second_run_does_not_overwrite(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    first = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)
    assert "成功：1 筆" in first

    second = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)
    assert "已執行過" in second, "第二次確認應被 once-only guard 擋下"
    assert "已執行改名" not in second
    assert (tmp_path / "renamed.pdf").read_text() == "content", "已更名檔案不可被覆寫"
    assert len(log.list_transactions()) == 1, "第二次確認不應新增 transaction"
