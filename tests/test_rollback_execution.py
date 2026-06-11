"""Phase 14D-3B 測試：Explicit Mock LINE Rollback Execution Command。

「回滾改名 {transaction_id}」是唯一可觸發真實 rollback 的指令，
必須完全比對，且一律透過 rollback_transaction_by_id() 執行。
所有會異動檔案的測試一律使用 pytest tmp_path 並注入隔離的 transaction log。
"""

import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.filename.schemas import RenameTransaction, RenameTransactionAction
from app.filename.transaction_log import RenameTransactionLog


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
# 測試 1 + 2 + 3：「回滾改名 {transaction_id}」執行 rollback，
#   檔案回到原始檔名，log 狀態更新為 rolled_back
# ---------------------------------------------------------------------------


def test_rollback_command_executes_rollback(tmp_path):
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    # 回覆摘要
    assert "已執行回滾改名" in output
    assert tx.transaction_id in output
    assert "成功：1 筆" in output
    assert "失敗：0 筆" in output

    # 檔案回到原始檔名
    assert (tmp_path / "orig_0.pdf").exists(), "rollback 後檔案應回到原名"
    assert (tmp_path / "orig_0.pdf").read_text() == "content"
    assert not renamed.exists(), "rollback 後更名後的檔案應消失"

    # log action 狀態更新為 rolled_back
    reloaded = log.load_transaction(tx.transaction_id)
    assert reloaded.actions[0].status == "rolled_back"


# ---------------------------------------------------------------------------
# 測試 4：transaction_id 不存在時回覆找不到
# ---------------------------------------------------------------------------


def test_rollback_command_unknown_transaction_id(tmp_path):
    log = RenameTransactionLog(tmp_path / "empty_log.json")

    output = mock_line_payload("回滾改名 unknown_tx_id", transaction_log=log)

    assert "找不到 transaction" in output
    assert "unknown_tx_id" in output
    assert "已執行回滾改名" not in output


# ---------------------------------------------------------------------------
# 測試 5：rollback source 不存在時回覆 rollback_source_not_found
# ---------------------------------------------------------------------------


def test_rollback_command_source_not_found(tmp_path):
    # 刻意不建立 new_0.pdf
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "rollback_source_not_found" in output
    assert "失敗：1 筆" in output
    assert "成功：0 筆" in output
    # rollback 失敗的 action 狀態維持 success（檔案仍視為在更名位置）
    reloaded = log.load_transaction(tx.transaction_id)
    assert reloaded.actions[0].status == "success"


# ---------------------------------------------------------------------------
# 測試 6：rollback target 已存在時回覆 rollback_target_already_exists
# ---------------------------------------------------------------------------


def test_rollback_command_target_already_exists(tmp_path):
    (tmp_path / "new_0.pdf").write_text("renamed content")
    (tmp_path / "orig_0.pdf").write_text("occupied")  # 回滾目標已被佔用
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "rollback_target_already_exists" in output
    assert "失敗：1 筆" in output
    assert (tmp_path / "orig_0.pdf").read_text() == "occupied", "佔用檔案不可被覆寫"
    assert (tmp_path / "new_0.pdf").exists(), "rollback 失敗時來源檔案不應被動到"


# ---------------------------------------------------------------------------
# 測試 6b：沒有可回滾項目（全部已 rolled_back / failed / pending）
# ---------------------------------------------------------------------------


def test_rollback_command_nothing_to_rollback(tmp_path):
    log, tx = _make_log_with_tx(tmp_path, ["rolled_back", "failed", "pending"])

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "沒有可回滾項目" in output
    assert "已執行回滾改名" not in output


# ---------------------------------------------------------------------------
# 測試 7–12：模糊文字與不完全格式不會觸發 rollback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vague_text",
    ["回滾", "回滾改名", "確認", "好", "OK", "執行"],
)
def test_vague_text_does_not_trigger_rollback(vague_text, tmp_path):
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    output = mock_line_payload(vague_text, transaction_log=log)

    assert "已執行回滾改名" not in output, f"「{vague_text}」不應觸發 rollback"
    assert renamed.exists(), f"「{vague_text}」不應移動任何檔案"
    assert log.load_transaction(tx.transaction_id).actions[0].status == "success"


def test_malformed_rollback_text_does_not_trigger_rollback(tmp_path):
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
        assert log.load_transaction(tx.transaction_id).actions[0].status == "success"


# ---------------------------------------------------------------------------
# 測試 13：「預覽回滾改名 {id}」仍只預覽，不會 rollback
# ---------------------------------------------------------------------------


def test_preview_command_still_does_not_rollback(tmp_path):
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])
    log_path = tmp_path / "tx_log.json"
    before = log_path.read_bytes()

    output = mock_line_payload(f"預覽回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "回滾預覽" in output
    assert "目前僅預覽，尚未執行回滾" in output
    assert "已執行回滾改名" not in output
    assert renamed.exists(), "preview 不應移動任何檔案"
    assert not (tmp_path / "orig_0.pdf").exists()
    assert log_path.read_bytes() == before, "preview 不應改動 transaction log"


# ---------------------------------------------------------------------------
# 測試 14：Mock LINE 不直接呼叫 Path.rename / os.rename / shutil.move（AST 驗證）
# ---------------------------------------------------------------------------


def test_mock_line_does_not_directly_call_rename_or_move():
    import ast

    tree = ast.parse(inspect.getsource(mock_line_module))

    forbidden_imports = {"os", "shutil"}
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_imports, (
                    f"mock_line 不可 import {alias.name}"
                )
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("rename", "move", "replace"), (
                    f"mock_line 不可直接呼叫 .{node.func.attr}()"
                )
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

    # 真實 rollback 必須透過 rollback_transaction_by_id
    assert "rollback_transaction_by_id" in called_names


# ---------------------------------------------------------------------------
# 測試 15：rollback 指令確實透過 rollback_transaction_by_id()（monkeypatch 驗證）
# ---------------------------------------------------------------------------


def test_rollback_command_delegates_to_rollback_by_id(tmp_path, monkeypatch):
    renamed = tmp_path / "new_0.pdf"
    renamed.write_text("content")
    log, tx = _make_log_with_tx(tmp_path, ["success"])

    calls = {}
    real = mock_line_module.rollback_transaction_by_id

    def spy(transaction_id, transaction_log):
        calls["transaction_id"] = transaction_id
        calls["transaction_log"] = transaction_log
        return real(transaction_id, transaction_log)

    monkeypatch.setattr(mock_line_module, "rollback_transaction_by_id", spy)

    output = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert calls["transaction_id"] == tx.transaction_id
    assert calls["transaction_log"] is log
    assert "已執行回滾改名" in output
    assert (tmp_path / "orig_0.pdf").exists()


# ---------------------------------------------------------------------------
# 額外：混合 action 的 rollback（success 回滾、其他不動）+ 重複回滾
# ---------------------------------------------------------------------------


def test_rollback_command_mixed_actions_and_repeat(tmp_path):
    (tmp_path / "new_0.pdf").write_text("a")  # success → 會回滾
    (tmp_path / "new_2.pdf").write_text("c")  # pending → 不動
    log, tx = _make_log_with_tx(tmp_path, ["success", "rolled_back", "pending"])

    first = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)

    assert "已執行回滾改名" in first
    assert "成功：1 筆" in first
    assert (tmp_path / "orig_0.pdf").exists(), "success action 應回滾"
    assert (tmp_path / "new_2.pdf").exists(), "pending action 不應被動到"

    reloaded = log.load_transaction(tx.transaction_id)
    statuses = [a.status for a in reloaded.actions]
    assert statuses == ["rolled_back", "rolled_back", "pending"]

    # 重複回滾：已無 success action → 沒有可回滾項目
    second = mock_line_payload(f"回滾改名 {tx.transaction_id}", transaction_log=log)
    assert "沒有可回滾項目" in second
    assert (tmp_path / "orig_0.pdf").read_text() == "a", "重複回滾不可再動檔案"
