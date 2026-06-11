"""Phase 14D-3A 測試：Mock LINE Rollback Preview Command。

Preview 是純讀取操作：不 rollback、不更名檔案、不寫 transaction log。
所有涉及檔案的測試一律使用 pytest tmp_path。
"""

import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload, preview_rollback
from app.filename.schemas import RenameTransaction, RenameTransactionAction
from app.filename.transaction_log import (
    RenameTransactionLog,
    preview_rollback_transaction,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _action(tmp_path: Path, orig: str, new: str, status: str) -> RenameTransactionAction:
    return RenameTransactionAction(
        original_path=str(tmp_path / orig),
        new_path=str(tmp_path / new),
        status=status,
        rollback_from=str(tmp_path / new),
        rollback_to=str(tmp_path / orig),
    )


def _make_log_with_tx(
    tmp_path: Path,
    statuses: list[str],
    plan_id: str = "plan-test",
) -> tuple[RenameTransactionLog, RenameTransaction]:
    log = RenameTransactionLog(tmp_path / "tx_log.json")
    actions = [
        _action(tmp_path, f"orig_{i}.pdf", f"new_{i}.pdf", status)
        for i, status in enumerate(statuses)
    ]
    tx = RenameTransaction(plan_id=plan_id, actions=actions)
    log.save_transaction(tx)
    return log, tx


# ---------------------------------------------------------------------------
# 測試 1：「預覽回滾改名 {transaction_id}」可查詢 transaction
# ---------------------------------------------------------------------------


def test_preview_rollback_command_queries_transaction(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["success", "success"])

    output = mock_line_payload(f"預覽回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "回滾預覽" in output
    assert tx.transaction_id in output
    assert "plan-test" in output
    assert "可回滾：2 筆" in output
    assert "目前僅預覽，尚未執行回滾" in output


# ---------------------------------------------------------------------------
# 測試 2：transaction_id 不存在時回覆找不到
# ---------------------------------------------------------------------------


def test_preview_rollback_unknown_transaction_id(tmp_path):
    log = RenameTransactionLog(tmp_path / "empty_log.json")

    output = mock_line_payload("預覽回滾改名 unknown_tx_id", transaction_log=log)

    assert "找不到 transaction" in output
    assert "unknown_tx_id" in output
    assert "回滾預覽" not in output


# ---------------------------------------------------------------------------
# 測試 3 + 5 + 6：模糊文字與不完全格式不會觸發 preview 或 rollback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vague_text",
    ["回滾", "回滾改名", "預覽回滾", "預覽回滾改名", "OK", "好"],
)
def test_vague_text_does_not_trigger_preview_or_rollback(vague_text, tmp_path):
    output = mock_line_payload(vague_text)

    assert "回滾預覽" not in output, f"「{vague_text}」不應觸發 preview"
    assert "已執行" not in output, f"「{vague_text}」不應觸發任何執行"


def test_preview_rollback_without_space_does_not_trigger(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    # 沒有空白 → 不可觸發
    output = mock_line_payload(f"預覽回滾改名{tx.transaction_id}", transaction_log=log)
    assert "回滾預覽" not in output

    # 多餘文字 → 不可觸發
    for text in [
        f"請預覽回滾改名 {tx.transaction_id}",
        f"預覽回滾改名 {tx.transaction_id} 謝謝",
    ]:
        output = mock_line_payload(text, transaction_log=log)
        assert "回滾預覽" not in output, f"「{text}」不應觸發 preview"


# ---------------------------------------------------------------------------
# 測試 4：格式不完全符合的「回滾改名」不會真的 rollback
# （Phase 14D-3B 起「回滾改名 {id}」為真實 rollback 指令；
#   完全比對與執行行為由 tests/test_rollback_execution.py 覆蓋。）
# ---------------------------------------------------------------------------


def test_malformed_rollback_command_does_not_actually_rollback(tmp_path):
    # 建立一個真實已更名的檔案情境
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    for text in [
        f"請回滾改名 {tx.transaction_id}",
        f"回滾改名 {tx.transaction_id} 謝謝",
        f"回滾改名{tx.transaction_id}",
    ]:
        output = mock_line_payload(text, transaction_log=log)
        assert "已執行回滾改名" not in output, f"「{text}」不應觸發 rollback"
        assert renamed.exists(), f"「{text}」不應移動任何檔案"
        assert not (tmp_path / "orig_0.pdf").exists(), "不應出現回滾後的檔案"
        # log 中 action 狀態不變
        reloaded = log.load_transaction(tx.transaction_id)
        assert reloaded.actions[0].status == "success"


# ---------------------------------------------------------------------------
# 測試 7：preview 不會修改 transaction log
# ---------------------------------------------------------------------------


def test_preview_does_not_modify_transaction_log(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["success", "failed", "rolled_back"])
    log_path = tmp_path / "tx_log.json"
    before = log_path.read_bytes()

    mock_line_payload(f"預覽回滾改名 {tx.transaction_id}", transaction_log=log)

    assert log_path.read_bytes() == before, "preview 不可改動 transaction log 檔案"


# ---------------------------------------------------------------------------
# 測試 8：preview 不會呼叫 rollback_transaction_by_id()
# ---------------------------------------------------------------------------


def test_preview_does_not_call_rollback_by_id(tmp_path, monkeypatch):
    import app.filename.executor as executor_module

    def explode(*args, **kwargs):
        raise AssertionError("preview 不應呼叫 rollback_transaction_by_id")

    monkeypatch.setattr(executor_module, "rollback_transaction_by_id", explode)
    monkeypatch.setattr(executor_module, "rollback_rename_transaction", explode)
    # Phase 14D-3B 起 mock_line 為「回滾改名」指令引用 rollback_transaction_by_id，
    # preview 路徑仍不可呼叫它
    monkeypatch.setattr(mock_line_module, "rollback_transaction_by_id", explode)

    log, tx = _make_log_with_tx(tmp_path, ["success"])
    output = mock_line_payload(f"預覽回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "回滾預覽" in output

    # 原始碼層級驗證：transaction_log（preview helper 所在模組）不引用 rollback 執行函式
    source = inspect.getsource(__import__("app.filename.transaction_log", fromlist=[""]))
    assert "rollback_transaction_by_id" not in source
    assert "rollback_rename_transaction" not in source


# ---------------------------------------------------------------------------
# 測試 9：preview 不會呼叫 Path.rename，也不會動到任何檔案
# ---------------------------------------------------------------------------


def test_preview_does_not_touch_files(tmp_path):
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    files_before = sorted(p.name for p in tmp_path.iterdir())
    mock_line_payload(f"預覽回滾改名 {tx.transaction_id}", transaction_log=log)
    files_after = sorted(p.name for p in tmp_path.iterdir())

    assert files_before == files_after, "preview 不可新增/刪除/更名任何檔案"
    assert renamed.read_text() == "content"


def test_preview_helper_source_has_no_rename_calls():
    import ast

    import app.filename.transaction_log as tx_log_module

    tree = ast.parse(inspect.getsource(tx_log_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("rename", "move", "replace"), (
                f"transaction_log 不可呼叫 .{node.func.attr}()"
            )


# ---------------------------------------------------------------------------
# 測試 10 + 11 + 12：rollbackable 判斷
# ---------------------------------------------------------------------------


def test_preview_success_action_is_rollbackable(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    preview = preview_rollback_transaction(tx.transaction_id, log)

    assert preview.rollbackable_count == 1
    assert preview.actions[0].rollbackable is True
    assert preview.actions[0].status == "success"


@pytest.mark.parametrize("status", ["rolled_back", "failed", "pending"])
def test_preview_non_success_action_is_not_rollbackable(status, tmp_path):
    log, tx = _make_log_with_tx(tmp_path, [status])

    preview = preview_rollback_transaction(tx.transaction_id, log)

    assert preview.rollbackable_count == 0
    assert preview.actions[0].rollbackable is False
    assert preview.actions[0].status == status


def test_preview_mixed_statuses_counts(tmp_path):
    log, tx = _make_log_with_tx(
        tmp_path, ["success", "success", "rolled_back", "failed", "pending"]
    )

    preview = preview_rollback_transaction(tx.transaction_id, log)

    assert preview.total_actions == 5
    assert preview.success_count == 2
    assert preview.rollbackable_count == 2
    assert preview.rolled_back_count == 1
    assert preview.failed_count == 1
    assert preview.pending_count == 1

    # Mock LINE 輸出也包含正確統計與每筆狀態
    output = preview_rollback(tx.transaction_id, transaction_log=log)
    assert "可回滾：2 筆" in output
    assert "已回滾：1 筆" in output
    assert "失敗：1 筆" in output
    assert "可回滾：是" in output
    assert "可回滾：否" in output


# ---------------------------------------------------------------------------
# 測試：helper 對不存在的 transaction 回傳 None
# ---------------------------------------------------------------------------


def test_preview_helper_returns_none_when_not_found(tmp_path):
    log = RenameTransactionLog(tmp_path / "empty.json")

    assert preview_rollback_transaction("nope", log) is None
