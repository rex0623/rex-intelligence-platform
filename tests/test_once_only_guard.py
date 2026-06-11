"""Phase 14E 測試：Rename Execution Hardening / Once-only Guard。

涵蓋：
- Approval once-only guard：同一 approval_id 不會重複執行真實 rename。
- Rollback once-only guard：已無可回滾 action 時不進入 rollback 執行路徑。

所有會異動檔案的測試一律使用 pytest tmp_path；approval store 與
transaction log 均隔離，不污染 runtime/。
"""

from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload, preview_rollback
from app.approvals.manager import approval_manager
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    RenameTransaction,
    RenameTransactionAction,
    ValidationReport,
)
from app.filename.transaction_log import (
    RenameTransactionLog,
    preview_rollback_transaction,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    """將全域 approval_manager 隔離到 tmp_path，避免污染 runtime/approvals.json。"""
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


def _make_plan(candidates: list[RenameCandidate], risk_levels: list[str]) -> RenamePlan:
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
    approval = manager.create_approval(plan.model_dump())
    manager.approve(approval.approval_id)
    return approval.approval_id


def _tx_action(tmp_path: Path, orig: str, new: str, status: str) -> RenameTransactionAction:
    return RenameTransactionAction(
        original_path=str(tmp_path / orig),
        new_path=str(tmp_path / new),
        status=status,
        rollback_from=str(tmp_path / new),
        rollback_to=str(tmp_path / orig),
    )


def _make_log_with_tx(
    tmp_path: Path, statuses: list[str]
) -> tuple[RenameTransactionLog, RenameTransaction]:
    log = RenameTransactionLog(tmp_path / "tx_log.json")
    tx = RenameTransaction(
        plan_id="plan-test",
        actions=[
            _tx_action(tmp_path, f"orig_{i}.pdf", f"new_{i}.pdf", s)
            for i, s in enumerate(statuses)
        ],
    )
    log.save_transaction(tx)
    return log, tx


# ===========================================================================
# A. Approval once-only guard
# ===========================================================================


# ---------------------------------------------------------------------------
# 測試 1 + 7：第一次「確認改名」成功執行（舊 payload 無 execution_status）
# ---------------------------------------------------------------------------


def test_first_confirm_executes_and_old_payload_has_no_execution_status(
    tmp_path, isolated_approvals
):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    # 舊格式 payload：沒有 execution_status → 視為尚未執行
    assert "execution_status" not in isolated_approvals.get(approval_id).payload

    log = RenameTransactionLog(tmp_path / "tx.json")
    output = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    assert "已執行改名" in output
    assert "成功：1 筆" in output
    assert (tmp_path / "renamed.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 8：成功後 approval record 寫入 execution_status / executed_at / transaction_id
# ---------------------------------------------------------------------------


def test_confirm_marks_approval_executed(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    payload = isolated_approvals.get(approval_id).payload
    assert payload["execution_status"] == "executed"
    assert payload["executed_at"]  # ISO datetime 字串
    tx_id = payload["execution_transaction_id"]
    assert tx_id == log.list_transactions()[0].transaction_id

    # 寫入 store 檔案（持久化）
    store_text = isolated_approvals.store_path.read_text(encoding="utf-8")
    assert "execution_status" in store_text


# ---------------------------------------------------------------------------
# 測試 2 + 3 + 4 + 5 + 6：第二次相同「確認改名」被 guard 擋下
# ---------------------------------------------------------------------------


def test_second_confirm_is_blocked_by_once_only_guard(
    tmp_path, isolated_approvals, monkeypatch
):
    c = _candidate(tmp_path, "bill.pdf", "renamed.pdf")
    (tmp_path / "bill.pdf").write_text("content")
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    first = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)
    assert "成功：1 筆" in first
    tx_id = log.list_transactions()[0].transaction_id

    files_before = sorted(p.name for p in tmp_path.iterdir())

    # 第二次不可再呼叫 execute_approved_rename_plan
    def explode(*args, **kwargs):
        raise AssertionError("重複確認不應再呼叫 execute_approved_rename_plan")

    monkeypatch.setattr(mock_line_module, "execute_approved_rename_plan", explode)

    second = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)

    # 回覆已執行過 + transaction_id + 復原提示
    assert "已執行過" in second
    assert "已執行改名" not in second
    assert tx_id in second, "重複確認應顯示 transaction_id"
    assert f"預覽回滾改名 {tx_id}" in second
    assert f"回滾改名 {tx_id}" in second

    # 不更動檔案、不新增 transaction
    files_after = sorted(p.name for p in tmp_path.iterdir())
    assert files_before == files_after, "重複確認不應更動任何檔案"
    assert len(log.list_transactions()) == 1, "重複確認不應新增 transaction"


# ---------------------------------------------------------------------------
# 全數失敗（無任何檔案被動到）時不標記 executed，允許重試
# ---------------------------------------------------------------------------


def test_failed_execution_does_not_mark_executed(tmp_path, isolated_approvals):
    c = _candidate(tmp_path, "ghost.pdf", "ghost_renamed.pdf")
    # 刻意不建立 ghost.pdf → 執行全數失敗
    plan = _make_plan([c], ["low"])
    approval_id = _approved_rename_approval(plan, isolated_approvals)

    log = RenameTransactionLog(tmp_path / "tx.json")
    first = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)
    assert "成功：0 筆" in first
    assert "original_file_not_found" in first

    # 未標記 executed → 補上檔案後可重試成功
    assert "execution_status" not in isolated_approvals.get(approval_id).payload
    (tmp_path / "ghost.pdf").write_text("late content")

    second = mock_line_payload(f"確認改名 {approval_id}", transaction_log=log)
    assert "成功：1 筆" in second
    assert (tmp_path / "ghost_renamed.pdf").exists()


# ===========================================================================
# B. Rollback once-only guard
# ===========================================================================


# ---------------------------------------------------------------------------
# 測試 9–13：第一次 rollback 成功，第二次被 guard 擋下
# ---------------------------------------------------------------------------


def test_second_rollback_is_blocked_by_once_only_guard(tmp_path, monkeypatch):
    (tmp_path / "new_0.pdf").write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])
    log_path = tmp_path / "tx_log.json"

    first = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)
    assert "已執行回滾改名" in first
    assert "成功：1 筆" in first
    assert (tmp_path / "orig_0.pdf").exists()
    assert log.load_transaction(tx.transaction_id).actions[0].status == "rolled_back"

    log_bytes_before = log_path.read_bytes()
    files_before = sorted(p.name for p in tmp_path.iterdir())

    # 第二次不可再進入 rollback 執行路徑
    def explode(*args, **kwargs):
        raise AssertionError("重複回滾不應再呼叫 rollback_transaction_by_id")

    monkeypatch.setattr(mock_line_module, "rollback_transaction_by_id", explode)

    second = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "已回滾完成" in second
    assert "沒有可回滾項目" in second
    assert "已執行回滾改名" not in second
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before, (
        "重複回滾不應更動任何檔案"
    )
    assert log_path.read_bytes() == log_bytes_before, "重複回滾不應改動 transaction log"


# ---------------------------------------------------------------------------
# 測試 14：部分 rollback 狀態時，只 rollback status == success 的 action
# ---------------------------------------------------------------------------


def test_partial_rollback_only_touches_success_actions(tmp_path):
    (tmp_path / "new_0.pdf").write_text("a")   # success → 會回滾
    (tmp_path / "orig_1.pdf").write_text("b")  # rolled_back → 不動
    log, tx = _make_log_with_tx(tmp_path, ["success", "rolled_back"])

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "已執行回滾改名" in output
    assert "成功：1 筆" in output
    assert (tmp_path / "orig_0.pdf").exists(), "success action 應回滾"
    assert (tmp_path / "orig_1.pdf").read_text() == "b", "rolled_back action 不應被動到"

    statuses = [a.status for a in log.load_transaction(tx.transaction_id).actions]
    assert statuses == ["rolled_back", "rolled_back"]

    # 全部回滾完成後，再次回滾被擋下
    again = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)
    assert "已回滾完成" in again
    assert "已回滾 2 筆" in again


# ---------------------------------------------------------------------------
# 非 fully-rolled-back 但無可回滾項目（failed/pending）仍被擋下
# ---------------------------------------------------------------------------


def test_rollback_blocked_when_no_rollbackable_but_not_fully_rolled_back(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["failed", "pending"])
    log_path = tmp_path / "tx_log.json"
    before = log_path.read_bytes()

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "沒有可回滾項目" in output
    assert "已回滾完成" not in output
    assert log_path.read_bytes() == before


# ===========================================================================
# C. Preview 與狀態 helper
# ===========================================================================


# ---------------------------------------------------------------------------
# 測試 15：預覽 fully rolled_back transaction，可回滾數為 0 + 提醒
# ---------------------------------------------------------------------------


def test_preview_fully_rolled_back_transaction(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["rolled_back", "rolled_back"])

    output = preview_rollback(tx.transaction_id, transaction_log=log)

    assert "可回滾：0 筆" in output
    assert "已回滾：2 筆" in output
    assert "此交易已全部回滾，目前沒有可回滾項目" in output
    assert "目前僅預覽，尚未執行回滾" in output


def test_preview_partial_no_rollbackable_hint(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["failed", "pending"])

    output = preview_rollback(tx.transaction_id, transaction_log=log)

    assert "可回滾：0 筆" in output
    assert "目前沒有可回滾項目" in output
    assert "此交易已全部回滾" not in output


# ---------------------------------------------------------------------------
# RollbackPreview 狀態判斷 properties
# ---------------------------------------------------------------------------


def test_rollback_preview_state_properties(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["success", "rolled_back"])
    preview = preview_rollback_transaction(tx.transaction_id, log)
    assert preview.has_rollbackable_actions is True
    assert preview.is_fully_rolled_back is False

    log2, tx2 = _make_log_with_tx(tmp_path / "sub2", ["rolled_back"])
    preview2 = preview_rollback_transaction(tx2.transaction_id, log2)
    assert preview2.has_rollbackable_actions is False
    assert preview2.is_fully_rolled_back is True

    log3, tx3 = _make_log_with_tx(tmp_path / "sub3", ["failed"])
    preview3 = preview_rollback_transaction(tx3.transaction_id, log3)
    assert preview3.has_rollbackable_actions is False
    assert preview3.is_fully_rolled_back is False


# ===========================================================================
# D. 模糊文字仍不可觸發（Phase 14E 後不變）
# ===========================================================================


@pytest.mark.parametrize("vague_text", ["確認", "好", "OK", "執行", "回滾", "回滾改名"])
def test_vague_text_still_does_not_trigger_anything(
    vague_text, tmp_path, isolated_approvals
):
    (tmp_path / "new_0.pdf").write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    output = mock_line_payload(vague_text, transaction_log=log)

    assert "已執行改名" not in output
    assert "已執行回滾改名" not in output
    assert (tmp_path / "new_0.pdf").exists()
    assert log.load_transaction(tx.transaction_id).actions[0].status == "success"
