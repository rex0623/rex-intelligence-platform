"""Phase 15H 測試：Move rollback preview helpers（read-only）。

preview_move_rollback_transaction() / preview_move_rollback_transaction_by_id()
是純讀取 API：

- success + rollback_from/rollback_to 存在 → rollbackable=True
- rolled_back → already_rolled_back；failed → action_failed；
  success 但缺 rollback 路徑 → missing_rollback_paths
- 不搬移檔案、不建資料夾、不修改 transaction、不更新 log
- transaction 找不到 → None
"""

import ast
import inspect
from pathlib import Path

from app.folder_intelligence import (
    MoveTransactionLog,
    preview_move_rollback_transaction,
    preview_move_rollback_transaction_by_id,
)
from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _action(
    original: str = "/inbox/bill.pdf",
    new: str = "/電費單/bill.pdf",
    status: str = "success",
    with_paths: bool = True,
) -> MoveTransactionAction:
    return MoveTransactionAction(
        original_path=original,
        new_path=new,
        status=status,
        rollback_from=new if with_paths else None,
        rollback_to=original if with_paths else None,
    )


def _tx(actions: list[MoveTransactionAction]) -> MoveTransaction:
    return MoveTransaction(plan_id="plan-1", actions=actions)


# ---------------------------------------------------------------------------
# 測試 1–4：per-action 語意
# ---------------------------------------------------------------------------


def test_success_action_is_rollbackable():
    preview = preview_move_rollback_transaction(_tx([_action(status="success")]))

    action = preview.actions[0]
    assert action.rollbackable is True
    assert action.reason is None
    assert action.rollback_from == "/電費單/bill.pdf"
    assert action.rollback_to == "/inbox/bill.pdf"
    assert preview.rollbackable_count == 1
    assert preview.has_rollbackable_actions is True


def test_rolled_back_action_is_already_rolled_back():
    preview = preview_move_rollback_transaction(_tx([_action(status="rolled_back")]))

    action = preview.actions[0]
    assert action.rollbackable is False
    assert action.reason == "already_rolled_back"
    assert preview.already_rolled_back_count == 1
    assert preview.rollbackable_count == 0
    assert preview.is_fully_rolled_back is True


def test_failed_action_is_action_failed():
    preview = preview_move_rollback_transaction(_tx([_action(status="failed")]))

    action = preview.actions[0]
    assert action.rollbackable is False
    assert action.reason == "action_failed"
    assert preview.failed_count == 1
    assert preview.rollbackable_count == 0


def test_success_without_rollback_paths_is_not_rollbackable():
    preview = preview_move_rollback_transaction(
        _tx([_action(status="success", with_paths=False)])
    )

    action = preview.actions[0]
    assert action.rollbackable is False
    assert action.reason == "missing_rollback_paths"
    assert preview.rollbackable_count == 0


# ---------------------------------------------------------------------------
# 測試 5：total 與計數
# ---------------------------------------------------------------------------


def test_preview_counts_are_correct():
    preview = preview_move_rollback_transaction(_tx([
        _action(original="/a", new="/A", status="success"),
        _action(original="/b", new="/B", status="rolled_back"),
        _action(original="/c", new="/C", status="failed"),
        _action(original="/d", new="/D", status="pending"),
        _action(original="/e", new="/E", status="success", with_paths=False),
    ]))

    assert preview.total == 5
    assert preview.rollbackable_count == 1
    assert preview.already_rolled_back_count == 1
    assert preview.failed_count == 1
    assert preview.is_fully_rolled_back is False
    assert preview.has_rollbackable_actions is True


# ---------------------------------------------------------------------------
# 測試 6–7：by_id 載入
# ---------------------------------------------------------------------------


def test_preview_by_id_returns_none_when_not_found(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")

    assert preview_move_rollback_transaction_by_id("no-such-id", log) is None


def test_preview_by_id_loads_persisted_transaction(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx = _tx([_action(status="success")])
    log.save_transaction(tx)

    preview = preview_move_rollback_transaction_by_id(tx.transaction_id, log)

    assert preview is not None
    assert preview.transaction_id == tx.transaction_id
    assert preview.total == 1
    assert preview.rollbackable_count == 1


# ---------------------------------------------------------------------------
# 測試 8–9：read-only 保證
# ---------------------------------------------------------------------------


def test_preview_does_not_update_log(tmp_path):
    log_path = tmp_path / "move_tx.json"
    log = MoveTransactionLog(log_path)
    tx = _tx([_action(status="success"), _action(original="/b", new="/B", status="rolled_back")])
    log.save_transaction(tx)
    before = log_path.read_bytes()

    preview_move_rollback_transaction_by_id(tx.transaction_id, log)
    preview_move_rollback_transaction_by_id(tx.transaction_id, log)

    assert log_path.read_bytes() == before, "preview 不可改動 log（byte-level）"


def test_preview_does_not_move_files(tmp_path):
    """preview 不搬移檔案、不建立資料夾。"""
    moved = tmp_path / "電費單" / "bill.pdf"
    moved.parent.mkdir(parents=True)
    moved.write_text("moved-content")
    original = tmp_path / "inbox" / "bill.pdf"  # 不存在（已被搬走）

    log = MoveTransactionLog(tmp_path / "log" / "move_tx.json")
    tx = _tx([MoveTransactionAction(
        original_path=str(original),
        new_path=str(moved),
        status="success",
        rollback_from=str(moved),
        rollback_to=str(original),
    )])
    log.save_transaction(tx)
    snapshot_before = sorted(str(p) for p in tmp_path.rglob("*"))

    preview = preview_move_rollback_transaction_by_id(tx.transaction_id, log)

    assert preview.rollbackable_count == 1
    assert moved.exists() and moved.read_text() == "moved-content"
    assert not original.exists(), "preview 不可把檔案搬回原位置"
    assert sorted(str(p) for p in tmp_path.rglob("*")) == snapshot_before, (
        "preview 不可建立或移動任何檔案/資料夾"
    )


def test_preview_functions_never_touch_filesystem_ast():
    """AST 驗證：preview helpers 不呼叫 rename/move/replace/mkdir/write。"""
    import app.folder_intelligence.transaction_log as tx_log_module

    source = inspect.getsource(tx_log_module)
    tree = ast.parse(source)
    forbidden = {"rename", "move", "replace", "mkdir", "makedirs"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith(
            "preview_move_rollback"
        ):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(
                    inner.func, ast.Attribute
                ):
                    assert inner.func.attr not in forbidden, (
                        f"{node.name} 不可呼叫 .{inner.func.attr}()"
                    )
                    assert not inner.func.attr.startswith("write"), (
                        f"{node.name} 不可寫入檔案"
                    )
