"""Phase 15I 測試：Explicit Mock LINE Move Rollback Command。

「回滾搬移 {transaction_id}」是唯一可觸發真實 move rollback 的 Mock LINE 指令：

- full match 才生效；「回滾搬移」「回滾搬移一下 …」「請幫我回滾搬移 …」
  「預覽回滾搬移 …」「回滾改名 …」「確認搬移 …」「確認改名 …」均不觸發
- 執行一律透過 rollback_move_transaction_by_id()（safe executor + log 同步），
  Mock LINE 不直接操作 filesystem
- once-only guard：先以 read-only preview 判斷；全部已回滾 →
  already_fully_rolled_back、無可回滾 → no_rollbackable_actions，
  完全不進入執行路徑
- rename rollback 與 move rollback transaction log 完全分離

所有真實 rollback 測試使用 pytest tmp_path，不污染 runtime/。
"""

import ast
import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog
from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def move_log(tmp_path):
    return MoveTransactionLog(tmp_path / "log" / "move_transactions.json")


def _save_moved_file(tmp_path, move_log, name: str = "bill.pdf"):
    """建立一筆「已成功搬移」狀態並回傳 (tx, moved, original)。"""
    moved = tmp_path / "電費單" / "24581234" / name
    moved.parent.mkdir(parents=True, exist_ok=True)
    moved.write_text("moved-" + name)
    original = tmp_path / "inbox" / name  # 已搬走，不存在

    tx = MoveTransaction(
        plan_id="plan-1",
        actions=[MoveTransactionAction(
            original_path=str(original),
            new_path=str(moved),
            status="success",
            rollback_from=str(moved),
            rollback_to=str(original),
        )],
    )
    move_log.save_transaction(tx)
    return tx, moved, original


@pytest.fixture
def moved_state(tmp_path, move_log):
    tx, moved, original = _save_moved_file(tmp_path, move_log)
    return {
        "tx_id": tx.transaction_id,
        "moved": moved,
        "original": original,
        "log_path": move_log._log_path,
    }


@pytest.fixture
def rollback_spy(monkeypatch):
    """側錄 mock_line 對 rollback_move_transaction_by_id 的呼叫。"""
    calls: list[str] = []
    real = mock_line_module.rollback_move_transaction_by_id

    def _spy(transaction_id, transaction_log):
        calls.append(transaction_id)
        return real(transaction_id, transaction_log)

    monkeypatch.setattr(mock_line_module, "rollback_move_transaction_by_id", _spy)
    return calls


# ---------------------------------------------------------------------------
# 測試 1–7：明確指令、真實回滾、log 更新與 response 格式
# ---------------------------------------------------------------------------


def test_exact_rollback_command_triggers_move_rollback(
    moved_state, move_log, rollback_spy
):
    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    assert rollback_spy == [moved_state["tx_id"]], (
        "「回滾搬移」必須走 rollback_move_transaction_by_id()"
    )


def test_exact_command_rolls_moved_file_back(moved_state, move_log):
    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert moved_state["original"].exists(), "檔案應被搬回原位置"
    assert moved_state["original"].read_text() == "moved-bill.pdf"
    assert not moved_state["moved"].exists(), "新位置不應殘留檔案"
    assert "成功：1 筆" in output


def test_rollback_updates_action_status_to_rolled_back(moved_state, move_log):
    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    tx = move_log.load_transaction(moved_state["tx_id"])
    assert tx.actions[0].status == "rolled_back"


def test_rollback_response_includes_title_and_flags(moved_state, move_log):
    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "搬移回滾結果" in output
    assert f"transaction_id：{moved_state['tx_id']}" in output
    assert "executed：True" in output
    assert "dry_run：False" in output


def test_rollback_response_includes_all_counts(moved_state, move_log):
    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "成功：1 筆" in output
    assert "失敗：0 筆" in output
    assert "跳過：0 筆" in output
    assert "blocked：0 筆" in output


def test_rollback_response_includes_rollback_paths(moved_state, move_log):
    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert f"rollback_from：{moved_state['moved']}" in output
    assert f"rollback_to：{moved_state['original']}" in output


def test_rollback_response_includes_completion_message(moved_state, move_log):
    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "已完成回滾搬移。" in output


# ---------------------------------------------------------------------------
# 測試 8–9：transaction 不存在 / 無可回滾項目
# ---------------------------------------------------------------------------


def test_missing_transaction_returns_transaction_not_found(move_log):
    output = mock_line_payload("回滾搬移 no-such-id", move_transaction_log=move_log)

    assert "transaction_not_found" in output
    assert "找不到 transaction" in output


def test_no_rollbackable_actions_does_not_execute(tmp_path, move_log, rollback_spy):
    """只有 failed action 的 transaction → no_rollbackable_actions，
    不進入執行路徑。"""
    tx = MoveTransaction(
        plan_id="plan-1",
        actions=[MoveTransactionAction(
            original_path=str(tmp_path / "a.pdf"),
            new_path=str(tmp_path / "b" / "a.pdf"),
            status="failed",
            rollback_from=str(tmp_path / "b" / "a.pdf"),
            rollback_to=str(tmp_path / "a.pdf"),
        )],
    )
    move_log.save_transaction(tx)

    output = mock_line_payload(
        f"回滾搬移 {tx.transaction_id}", move_transaction_log=move_log
    )

    assert "no_rollbackable_actions" in output
    assert rollback_spy == [], "無可回滾項目時不可進入執行路徑"


# ---------------------------------------------------------------------------
# 測試 10–12：once-only guard
# ---------------------------------------------------------------------------


def test_repeated_rollback_does_not_move_twice(moved_state, move_log, rollback_spy):
    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    # 在新位置放一個無關檔案：若 guard 失效，第二次會試圖再搬移它
    moved_state["moved"].write_text("new-unrelated-content")

    second = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "already_fully_rolled_back" in second
    assert "不會重複回滾" in second
    assert rollback_spy == [moved_state["tx_id"]], "第二次不可進入執行路徑"
    assert moved_state["moved"].read_text() == "new-unrelated-content", (
        "第二次「回滾搬移」不可搬移任何檔案"
    )


def test_repeated_rollback_does_not_corrupt_log(moved_state, move_log):
    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)
    after_first = moved_state["log_path"].read_bytes()

    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    assert moved_state["log_path"].read_bytes() == after_first, (
        "第二次「回滾搬移」不可改動 log"
    )
    tx = move_log.load_transaction(moved_state["tx_id"])
    assert tx is not None, "log 應仍可正常載入"
    assert tx.actions[0].status == "rolled_back"


def test_repeated_rollback_does_not_report_source_missing(moved_state, move_log):
    """第二次回滾應由 once-only guard 擋下（already_fully_rolled_back），
    不可進入執行路徑後才以 rollback_source_not_found 失敗。"""
    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    second = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "rollback_source_not_found" not in second
    assert "already_fully_rolled_back" in second


# ---------------------------------------------------------------------------
# 測試 13–16：rollback 失敗時的安全行為
# ---------------------------------------------------------------------------


def test_rollback_fails_safely_when_source_missing(moved_state, move_log):
    moved_state["moved"].unlink()  # 新位置檔案被外部移除

    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "rollback_source_not_found" in output
    assert "失敗：1 筆" in output
    tx = move_log.load_transaction(moved_state["tx_id"])
    assert tx.actions[0].status == "success", (
        "回滾失敗的 action 不可標記 rolled_back"
    )


def test_rollback_fails_safely_when_target_occupied(moved_state, move_log):
    moved_state["original"].parent.mkdir(parents=True, exist_ok=True)
    moved_state["original"].write_text("occupied")  # 原位置被佔用

    output = mock_line_payload(
        f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "rollback_target_already_exists" in output
    assert moved_state["original"].read_text() == "occupied", "不可覆寫任何檔案"
    assert moved_state["moved"].exists(), "檔案應留在新位置"


def test_failed_rollback_does_not_mark_rolled_back(moved_state, move_log):
    moved_state["original"].parent.mkdir(parents=True, exist_ok=True)
    moved_state["original"].write_text("occupied")

    mock_line_payload(f"回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log)

    tx = move_log.load_transaction(moved_state["tx_id"])
    assert tx.actions[0].status == "success", (
        "失敗的 rollback 不可標記 rolled_back（檔案仍在新位置）"
    )


def test_partial_rollback_updates_only_successful_actions(tmp_path, move_log):
    """兩筆 success action：一筆可回滾、一筆原位置被佔用 →
    只有成功回滾的標記 rolled_back，失敗的保持 success。"""
    moved_a = tmp_path / "電費單" / "a.pdf"
    moved_b = tmp_path / "電費單" / "b.pdf"
    moved_a.parent.mkdir(parents=True)
    moved_a.write_text("content-a")
    moved_b.write_text("content-b")
    orig_a = tmp_path / "inbox" / "a.pdf"
    orig_b = tmp_path / "inbox" / "b.pdf"
    orig_b.parent.mkdir(parents=True)
    orig_b.write_text("occupied-b")  # b 的原位置被佔用 → 回滾失敗

    tx = MoveTransaction(plan_id="plan-1", actions=[
        MoveTransactionAction(
            original_path=str(orig_a), new_path=str(moved_a), status="success",
            rollback_from=str(moved_a), rollback_to=str(orig_a),
        ),
        MoveTransactionAction(
            original_path=str(orig_b), new_path=str(moved_b), status="success",
            rollback_from=str(moved_b), rollback_to=str(orig_b),
        ),
    ])
    move_log.save_transaction(tx)

    output = mock_line_payload(
        f"回滾搬移 {tx.transaction_id}", move_transaction_log=move_log
    )

    assert "成功：1 筆" in output and "失敗：1 筆" in output
    assert orig_a.exists() and orig_a.read_text() == "content-a"
    assert orig_b.read_text() == "occupied-b", "不可覆寫"
    assert moved_b.exists(), "失敗的檔案應留在新位置"
    reloaded = move_log.load_transaction(tx.transaction_id)
    statuses = {a.original_path: a.status for a in reloaded.actions}
    assert statuses[str(orig_a)] == "rolled_back"
    assert statuses[str(orig_b)] == "success"


# ---------------------------------------------------------------------------
# 測試 17–21：模糊文字與 preview 不可觸發真實 rollback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template",
    [
        "回滾搬移",
        "回滾搬移一下 {tx_id}",
        "請幫我回滾搬移 {tx_id}",
        "預覽搬移回滾 {tx_id}",
    ],
)
def test_fuzzy_texts_do_not_trigger_rollback(
    moved_state, move_log, rollback_spy, template
):
    output = mock_line_payload(
        template.format(tx_id=moved_state["tx_id"]), move_transaction_log=move_log
    )

    assert rollback_spy == [], f"「{template}」不可觸發 rollback"
    assert "搬移回滾結果" not in output
    assert moved_state["moved"].exists(), "檔案必須留在新位置"
    assert not moved_state["original"].exists()


def test_preview_command_does_not_rollback_and_stays_read_only(
    moved_state, move_log, rollback_spy
):
    before = moved_state["log_path"].read_bytes()

    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "搬移回滾預覽" in output
    assert rollback_spy == [], "「預覽回滾搬移」不可觸發 rollback"
    assert moved_state["moved"].exists()
    assert not moved_state["original"].exists()
    assert moved_state["log_path"].read_bytes() == before, "preview 不可改動 log"


# ---------------------------------------------------------------------------
# 測試 22–25：rename / move 指令互不影響
# ---------------------------------------------------------------------------


def test_rollback_rename_does_not_touch_move_log(tmp_path, moved_state, move_log):
    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")
    before = moved_state["log_path"].read_bytes()

    output = mock_line_payload(
        f"回滾改名 {moved_state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert "找不到 transaction" in output, "move tx id 不存在於 rename log"
    assert moved_state["log_path"].read_bytes() == before
    assert moved_state["moved"].exists(), "「回滾改名」不可動到 move 的檔案"


def test_preview_rename_rollback_does_not_touch_move_log(
    tmp_path, moved_state, move_log
):
    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")
    before = moved_state["log_path"].read_bytes()

    output = mock_line_payload(
        f"預覽回滾改名 {moved_state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert "搬移回滾預覽" not in output
    assert moved_state["log_path"].read_bytes() == before
    assert moved_state["moved"].exists()


def test_confirm_move_does_not_trigger_rollback(
    tmp_path, moved_state, move_log, rollback_spy, monkeypatch
):
    from app.approvals.manager import approval_manager

    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})

    output = mock_line_payload("確認搬移 no-such-approval", move_transaction_log=move_log)

    assert rollback_spy == [], "「確認搬移」不可觸發 rollback"
    assert "approval_not_found" in output
    assert moved_state["moved"].exists()


def test_confirm_rename_does_not_trigger_move_rollback(
    tmp_path, moved_state, move_log, rollback_spy, monkeypatch
):
    from app.approvals.manager import approval_manager

    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})

    output = mock_line_payload(
        "確認改名 no-such-approval", move_transaction_log=move_log
    )

    assert rollback_spy == [], "「確認改名」不可觸發 move rollback"
    assert "找不到 approval" in output
    assert moved_state["moved"].exists()


# ---------------------------------------------------------------------------
# 測試 26–27：default log 與 filesystem 隔離
# ---------------------------------------------------------------------------


def test_rollback_command_uses_default_move_transaction_log(
    tmp_path, monkeypatch
):
    """未注入 move_transaction_log 時使用 default_move_transaction_log()。"""
    log = MoveTransactionLog(tmp_path / "log" / "move_transactions.json")
    tx, moved, original = _save_moved_file(tmp_path, log)
    monkeypatch.setattr(
        mock_line_module, "default_move_transaction_log", lambda: log
    )

    output = mock_line_payload(f"回滾搬移 {tx.transaction_id}")

    assert "已完成回滾搬移。" in output
    assert original.exists() and not moved.exists()
    assert log.load_transaction(tx.transaction_id).actions[0].status == "rolled_back"


def test_mock_line_does_not_touch_filesystem_directly():
    """AST 驗證：mock_line 不直接呼叫 .rename()/.replace()/.move()，
    不 import os / shutil。"""
    source = inspect.getsource(mock_line_module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("rename", "renames", "replace", "move"), (
                f"Mock LINE 不可直接呼叫 .{node.func.attr}()"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in ("os", "shutil"), (
                    f"Mock LINE 不可 import {alias.name}"
                )
