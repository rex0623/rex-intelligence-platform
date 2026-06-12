"""Phase 15H 測試：Mock LINE「預覽回滾搬移 {transaction_id}」指令。

- full match 才觸發；「回滾搬移 …」「預覽搬移回滾 …」「請幫我預覽回滾搬移 …」
  「預覽回滾搬移」「預覽回滾搬移一下 …」均不觸發
- 指令為 read-only：不 rollback、不搬移檔案、不寫 transaction log
- 「預覽回滾改名」「回滾改名」仍只作用於 rename transaction log
- Mock LINE 不呼叫 rollback_move_transaction / rollback_move_transaction_by_id
- 仍然沒有真實「回滾搬移」指令

所有測試使用 tmp_path 隔離，不污染 runtime/。
"""

import ast
import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.folder_intelligence import MoveTransactionLog
from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
)
from app.filename.transaction_log import RenameTransactionLog


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def move_log(tmp_path):
    return MoveTransactionLog(tmp_path / "log" / "move_transactions.json")


@pytest.fixture
def moved_state(tmp_path, move_log):
    """建立一筆「已成功搬移」的狀態：檔案在新位置、log 有 success action。"""
    moved = tmp_path / "電費單" / "24581234" / "bill.pdf"
    moved.parent.mkdir(parents=True)
    moved.write_text("moved-content")
    original = tmp_path / "inbox" / "bill.pdf"  # 已搬走，不存在

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
    return {
        "tx_id": tx.transaction_id,
        "moved": moved,
        "original": original,
        "log_path": move_log._log_path,
    }


@pytest.fixture
def preview_spy(monkeypatch):
    """側錄 mock_line 對 move rollback preview helper 的呼叫。"""
    calls: list[str] = []
    real = mock_line_module.preview_move_rollback_transaction_by_id

    def _spy(transaction_id, transaction_log):
        calls.append(transaction_id)
        return real(transaction_id, transaction_log)

    monkeypatch.setattr(
        mock_line_module, "preview_move_rollback_transaction_by_id", _spy
    )
    return calls


@pytest.fixture
def rollback_guard(monkeypatch):
    """任何路徑呼叫 move rollback API 都直接失敗（含 mock_line 在 15I
    綁定的 rollback_move_transaction_by_id 名稱）。"""
    import app.folder_intelligence.executor as executor_module

    def _forbidden(*args, **kwargs):
        raise AssertionError("此情境不可觸發真實 move rollback")

    monkeypatch.setattr(executor_module, "rollback_move_transaction", _forbidden)
    monkeypatch.setattr(
        executor_module, "rollback_move_transaction_by_id", _forbidden
    )
    monkeypatch.setattr(
        mock_line_module, "rollback_move_transaction_by_id", _forbidden
    )


# ---------------------------------------------------------------------------
# 測試 10–15：明確指令與 response 格式
# ---------------------------------------------------------------------------


def test_exact_preview_command_returns_preview(moved_state, move_log, rollback_guard):
    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "搬移回滾預覽" in output
    assert f"transaction_id：{moved_state['tx_id']}" in output


def test_preview_response_includes_counts(moved_state, move_log):
    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "total：1 筆" in output
    assert "rollbackable_count：1 筆" in output
    assert "already_rolled_back_count：0 筆" in output
    assert "failed_count：0 筆" in output


def test_preview_response_includes_rollback_paths(moved_state, move_log):
    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert f"rollback_from：{moved_state['moved']}" in output
    assert f"rollback_to：{moved_state['original']}" in output
    assert "狀態：success" in output
    assert "可回滾：是" in output


def test_preview_response_says_not_rolled_back_yet(moved_state, move_log):
    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "這只是預覽，尚未實際回滾任何檔案。" in output
    # 15I 起提示可用的執行指令（取代 15H 的「尚未開放」提示）
    assert f"回滾搬移 {moved_state['tx_id']}" in output


def test_preview_missing_transaction_returns_transaction_not_found(move_log):
    output = mock_line_payload(
        "預覽回滾搬移 no-such-id", move_transaction_log=move_log
    )

    assert "transaction_not_found" in output
    assert "找不到 transaction" in output


# ---------------------------------------------------------------------------
# 測試 16–20：非 full match 文字不可觸發 preview / rollback
# ---------------------------------------------------------------------------


def test_fuzzy_rollback_move_texts_do_not_trigger_anything(
    moved_state, move_log, preview_spy, rollback_guard
):
    """模糊的「回滾搬移」變形不是指令：不 rollback、不 preview
    （15I 的 full match「回滾搬移 {transaction_id}」行為見
    test_mock_line_move_rollback_execution.py）。"""
    before = moved_state["log_path"].read_bytes()

    for text in (
        "回滾搬移",
        f"回滾搬移一下 {moved_state['tx_id']}",
        f"請幫我回滾搬移 {moved_state['tx_id']}",
    ):
        output = mock_line_payload(text, move_transaction_log=move_log)
        assert "搬移回滾預覽" not in output
        assert "搬移回滾結果" not in output

    assert preview_spy == [], "模糊文字不可觸發 preview"
    assert moved_state["moved"].exists(), "檔案必須留在新位置（未被回滾）"
    assert not moved_state["original"].exists()
    assert moved_state["log_path"].read_bytes() == before, "log 不可被改動"


@pytest.mark.parametrize(
    "template",
    [
        "預覽搬移回滾 {tx_id}",
        "請幫我預覽回滾搬移 {tx_id}",
        "預覽回滾搬移",
        "預覽回滾搬移一下 {tx_id}",
    ],
)
def test_fuzzy_texts_do_not_trigger_preview(
    moved_state, move_log, preview_spy, rollback_guard, template
):
    output = mock_line_payload(
        template.format(tx_id=moved_state["tx_id"]), move_transaction_log=move_log
    )

    assert preview_spy == [], f"「{template}」不可觸發 preview"
    assert "搬移回滾預覽" not in output
    assert moved_state["moved"].exists()
    assert not moved_state["original"].exists()


# ---------------------------------------------------------------------------
# 測試 21–22：rename 預覽/回滾指令不受影響，且不作用於 move log
# ---------------------------------------------------------------------------


def test_preview_rename_rollback_still_targets_rename_only(
    tmp_path, moved_state, move_log, preview_spy
):
    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")

    output = mock_line_payload(
        f"預覽回滾改名 {moved_state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert preview_spy == [], "「預覽回滾改名」不可進入 move preview 路徑"
    assert "搬移回滾預覽" not in output
    assert "找不到 transaction" in output, "move tx id 不存在於 rename log"


def test_rollback_rename_still_targets_rename_only(
    tmp_path, moved_state, move_log, rollback_guard
):
    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")
    before = moved_state["log_path"].read_bytes()

    output = mock_line_payload(
        f"回滾改名 {moved_state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert "找不到 transaction" in output
    assert moved_state["moved"].exists(), "「回滾改名」不可動到 move 的檔案"
    assert moved_state["log_path"].read_bytes() == before


# ---------------------------------------------------------------------------
# 測試 23–25：read-only 與 rollback API 隔離
# ---------------------------------------------------------------------------


def test_repeated_preview_does_not_modify_log(moved_state, move_log):
    before = moved_state["log_path"].read_bytes()

    for _ in range(3):
        mock_line_payload(
            f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
        )

    assert moved_state["log_path"].read_bytes() == before, (
        "重複 preview 不可改動 log（byte-level）"
    )
    assert moved_state["moved"].exists()
    assert not moved_state["original"].exists()


def test_preview_command_does_not_call_rollback_apis(
    moved_state, move_log, rollback_guard
):
    """rollback_move_transaction / rollback_move_transaction_by_id 被 monkeypatch
    為直接 AssertionError；preview 指令完整執行代表沒有任何 rollback 呼叫。"""
    output = mock_line_payload(
        f"預覽回滾搬移 {moved_state['tx_id']}", move_transaction_log=move_log
    )

    assert "搬移回滾預覽" in output


# ---------------------------------------------------------------------------
# Safety scanning（Task 6）
# ---------------------------------------------------------------------------


def test_mock_line_imports_preview_but_not_rollback_apis():
    source = inspect.getsource(mock_line_module)
    assert "preview_move_rollback_transaction_by_id" in source

    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.name)
    # 15I 起允許 rollback_move_transaction_by_id（「回滾搬移」唯一執行路徑）；
    # executor 與非 by_id 低階 rollback API 仍不可 import（exact-name 比對）
    for forbidden in (
        "execute_move_plan",
        "rollback_move_transaction",
    ):
        assert forbidden not in imported, f"Mock LINE 不可 import {forbidden}"
    assert "rollback_move_transaction_by_id" in imported


def test_move_rollback_regexes_are_full_match():
    """「預覽回滾搬移」regex 允許（read-only）；15I 起「回滾搬移」真實
    rollback 指令 regex 允許，但兩者都必須 full match（^ 開頭、$ 結尾）。"""
    source = inspect.getsource(mock_line_module)
    tree = ast.parse(source)
    patterns: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            patterns.append(node.args[0].value)

    assert any("預覽回滾搬移" in p for p in patterns), (
        "15H 應有 read-only「預覽回滾搬移」regex"
    )
    assert any(p.lstrip("^").startswith("回滾搬移") for p in patterns), (
        "15I 應有「回滾搬移」指令 regex"
    )
    for pattern in patterns:
        if "回滾搬移" in pattern:
            assert pattern.startswith("^") and pattern.endswith("$"), (
                f"move rollback 相關 regex 必須 full match：{pattern}"
            )
