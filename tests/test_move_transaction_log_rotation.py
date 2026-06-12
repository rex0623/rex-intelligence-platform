"""Phase 15J 測試：Move Transaction Log Rotation / Cleanup。

prune_transactions() / prune_move_transactions() 是底層維運 API（鏡像 14F）：

- log 不存在 → 安全 no-op（不建立 log）
- 整檔 invalid JSON → 不刪、不覆寫、corrupted 計數
- 無法解析的 entry → 原樣保留（corrupted_entries）
- 仍可回滾（任一 success action）→ 永不刪除（protected）
- 全部 rolled_back / 只有 failed/pending → 過期才刪，未過期保留（retained）
- dry_run / no-op → 不重寫 log
- 只動 log JSON：不搬移、不回滾、不建資料夾、不改 action status
- 不接任何 Mock LINE 指令

所有測試使用 tmp_path，不污染 runtime/。
"""

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from app.folder_intelligence import (
    MoveTransactionLog,
    prune_move_transactions,
)
from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


_NOW = datetime.now(timezone.utc)


def _tx(
    statuses: list[str],
    age_days: int = 0,
    plan_id: str = "plan-1",
) -> MoveTransaction:
    return MoveTransaction(
        plan_id=plan_id,
        created_at=_NOW - timedelta(days=age_days),
        actions=[
            MoveTransactionAction(
                original_path=f"/inbox/f{i}.pdf",
                new_path=f"/電費單/f{i}.pdf",
                status=status,
                rollback_from=f"/電費單/f{i}.pdf",
                rollback_to=f"/inbox/f{i}.pdf",
            )
            for i, status in enumerate(statuses)
        ],
    )


@pytest.fixture
def log(tmp_path):
    return MoveTransactionLog(tmp_path / "move_tx.json")


# ---------------------------------------------------------------------------
# 測試 1–3：missing log / invalid JSON / corrupted entry
# ---------------------------------------------------------------------------


def test_prune_missing_log_is_safe_noop(tmp_path):
    log_path = tmp_path / "no-such" / "move_tx.json"
    log = MoveTransactionLog(log_path)

    result = log.prune_transactions(older_than_days=30)

    assert result.before_count == 0
    assert result.after_count == 0
    assert result.pruned_count == 0
    assert not log_path.exists(), "no-op 不可建立 log 檔"
    assert not log_path.parent.exists(), "no-op 不可建立資料夾"


def test_prune_invalid_json_does_not_rewrite(tmp_path):
    log_path = tmp_path / "move_tx.json"
    log_path.write_text("{ this is not valid json !!!", encoding="utf-8")
    before = log_path.read_bytes()

    result = MoveTransactionLog(log_path).prune_transactions(older_than_days=0)

    assert result.corrupted_count >= 1
    assert result.corrupted_entries >= 1
    assert result.pruned_count == 0
    assert log_path.read_bytes() == before, "invalid JSON 不可被覆寫"


def test_prune_preserves_corrupted_entry_raw(log):
    old = _tx(["rolled_back"], age_days=60)
    log.save_transaction(old)
    # 手動塞入一個無法解析的 raw entry
    data = json.loads(log._log_path.read_text(encoding="utf-8"))
    garbage = {"garbage": True, "未知欄位": "原樣保留"}
    data["transactions"].append(garbage)
    log._log_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1  # 過期的 rolled_back tx 被刪
    assert result.corrupted_entries == 1
    after = json.loads(log._log_path.read_text(encoding="utf-8"))
    assert garbage in after["transactions"], "corrupted entry 必須原樣保留"


# ---------------------------------------------------------------------------
# 測試 4–10：protected / 過期刪除 / 未過期保留
# ---------------------------------------------------------------------------


def test_prune_keeps_rollbackable_transaction_even_if_old(log):
    tx = _tx(["success", "rolled_back"], age_days=365)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 0
    assert result.protected_count == 1
    assert tx.transaction_id in result.protected_transaction_ids
    assert log.load_transaction(tx.transaction_id) is not None


def test_prune_deletes_old_fully_rolled_back_transaction(log):
    tx = _tx(["rolled_back", "rolled_back"], age_days=60)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1
    assert tx.transaction_id in result.pruned_transaction_ids
    assert log.load_transaction(tx.transaction_id) is None


def test_prune_keeps_recent_fully_rolled_back_transaction(log):
    tx = _tx(["rolled_back"], age_days=5)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 0
    assert result.retained_count == 1
    assert tx.transaction_id in result.retained_transaction_ids
    assert log.load_transaction(tx.transaction_id) is not None


def test_prune_deletes_old_failed_only_transaction(log):
    tx = _tx(["failed", "failed"], age_days=60)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1
    assert log.load_transaction(tx.transaction_id) is None


def test_prune_keeps_recent_failed_only_transaction(log):
    tx = _tx(["failed"], age_days=5)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 0
    assert log.load_transaction(tx.transaction_id) is not None


def test_prune_deletes_old_pending_only_transaction(log):
    tx = _tx(["pending"], age_days=60)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1
    assert log.load_transaction(tx.transaction_id) is None


def test_prune_keeps_recent_pending_only_transaction(log):
    tx = _tx(["pending"], age_days=5)
    log.save_transaction(tx)

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 0
    assert log.load_transaction(tx.transaction_id) is not None


# ---------------------------------------------------------------------------
# 測試 11–12：dry_run / no-op 不重寫 log
# ---------------------------------------------------------------------------


def test_prune_dry_run_reports_but_does_not_rewrite(log):
    tx = _tx(["rolled_back"], age_days=60)
    log.save_transaction(tx)
    before = log._log_path.read_bytes()

    result = log.prune_transactions(older_than_days=30, dry_run=True)

    assert result.dry_run is True
    assert result.pruned_count == 1
    assert tx.transaction_id in result.pruned_transaction_ids
    assert result.after_count == 0  # 預計刪除後的筆數
    assert log._log_path.read_bytes() == before, "dry_run 不可重寫 log"
    assert log.load_transaction(tx.transaction_id) is not None


def test_prune_noop_does_not_rewrite_log(log):
    tx = _tx(["rolled_back"], age_days=5)  # 未過期 → 無可刪
    log.save_transaction(tx)
    before_bytes = log._log_path.read_bytes()
    before_mtime = log._log_path.stat().st_mtime_ns

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 0
    assert log._log_path.read_bytes() == before_bytes
    assert log._log_path.stat().st_mtime_ns == before_mtime, (
        "無可清理項目時不可重寫 log"
    )


# ---------------------------------------------------------------------------
# 測試 13–17：result 計數與 id 清單
# ---------------------------------------------------------------------------


@pytest.fixture
def mixed_log(log):
    """protected（old success）+ pruned（old rolled_back）+
    retained（recent failed）+ corrupted entry。"""
    protected = _tx(["success"], age_days=90)
    prunable = _tx(["rolled_back"], age_days=90)
    retained = _tx(["failed"], age_days=1)
    for tx in (protected, prunable, retained):
        log.save_transaction(tx)
    data = json.loads(log._log_path.read_text(encoding="utf-8"))
    data["transactions"].append({"not": "a transaction"})
    log._log_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "log": log,
        "protected": protected,
        "prunable": prunable,
        "retained": retained,
    }


def test_prune_result_counts_are_correct(mixed_log):
    result = mixed_log["log"].prune_transactions(older_than_days=30)

    assert result.before_count == 4
    assert result.pruned_count == 1
    assert result.protected_count == 1
    assert result.retained_count == 1
    assert result.corrupted_entries == 1
    assert result.corrupted_count == 1
    assert result.after_count == 3


def test_protected_ids_are_reported(mixed_log):
    result = mixed_log["log"].prune_transactions(older_than_days=30)

    assert result.protected_transaction_ids == [
        mixed_log["protected"].transaction_id
    ]


def test_pruned_ids_are_reported(mixed_log):
    result = mixed_log["log"].prune_transactions(older_than_days=30)

    assert result.pruned_transaction_ids == [mixed_log["prunable"].transaction_id]


def test_retained_ids_are_reported(mixed_log):
    result = mixed_log["log"].prune_transactions(older_than_days=30)

    assert result.retained_transaction_ids == [
        mixed_log["retained"].transaction_id
    ]


def test_corrupted_entries_count_is_reported(mixed_log):
    result = mixed_log["log"].prune_transactions(older_than_days=30)

    assert result.corrupted_entries == 1
    after = json.loads(mixed_log["log"]._log_path.read_text(encoding="utf-8"))
    assert {"not": "a transaction"} in after["transactions"]


# ---------------------------------------------------------------------------
# 測試 18–22：cleanup 不碰實體檔案 / 不回滾 / 不改 status / 保留未知欄位
# ---------------------------------------------------------------------------


def test_prune_does_not_move_files_or_create_folders(tmp_path):
    """log 中的路徑指向 tmp_path 下真實檔案；prune 後檔案與目錄結構不變。"""
    moved = tmp_path / "電費單" / "bill.pdf"
    moved.parent.mkdir(parents=True)
    moved.write_text("content")
    log = MoveTransactionLog(tmp_path / "log" / "move_tx.json")
    tx = MoveTransaction(
        plan_id="plan-1",
        created_at=_NOW - timedelta(days=90),
        actions=[MoveTransactionAction(
            original_path=str(tmp_path / "inbox" / "bill.pdf"),
            new_path=str(moved),
            status="rolled_back",
            rollback_from=str(moved),
            rollback_to=str(tmp_path / "inbox" / "bill.pdf"),
        )],
    )
    log.save_transaction(tx)
    snapshot_before = sorted(str(p) for p in tmp_path.rglob("*") if "move_tx" not in str(p))

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1
    assert moved.exists() and moved.read_text() == "content"
    assert not (tmp_path / "inbox").exists(), "prune 不可建立資料夾"
    snapshot_after = sorted(str(p) for p in tmp_path.rglob("*") if "move_tx" not in str(p))
    assert snapshot_after == snapshot_before, "prune 只能動 log 檔"


def test_prune_does_not_call_rollback_api(log, monkeypatch):
    import app.folder_intelligence.executor as executor_module

    def _forbidden(*args, **kwargs):
        raise AssertionError("prune 不可呼叫 rollback API")

    monkeypatch.setattr(executor_module, "rollback_move_transaction", _forbidden)
    monkeypatch.setattr(
        executor_module, "rollback_move_transaction_by_id", _forbidden
    )
    log.save_transaction(_tx(["rolled_back"], age_days=90))

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1  # 正常完成，未觸發 guard


def test_prune_does_not_change_action_statuses(mixed_log):
    mixed_log["log"].prune_transactions(older_than_days=30)

    protected = mixed_log["log"].load_transaction(
        mixed_log["protected"].transaction_id
    )
    retained = mixed_log["log"].load_transaction(
        mixed_log["retained"].transaction_id
    )
    assert protected.actions[0].status == "success"
    assert retained.actions[0].status == "failed"


def test_prune_preserves_unknown_fields_on_kept_entries(log):
    """保留的 entry 以 raw 形式過濾，不重新序列化：未知欄位原樣保留。"""
    kept = _tx(["success"], age_days=90)  # protected
    prunable = _tx(["rolled_back"], age_days=90)
    log.save_transaction(kept)
    log.save_transaction(prunable)
    data = json.loads(log._log_path.read_text(encoding="utf-8"))
    for entry in data["transactions"]:
        if entry["transaction_id"] == kept.transaction_id:
            entry["future_field"] = {"nested": "value"}
    log._log_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = log.prune_transactions(older_than_days=30)

    assert result.pruned_count == 1
    after = json.loads(log._log_path.read_text(encoding="utf-8"))
    kept_entry = next(
        e for e in after["transactions"]
        if e.get("transaction_id") == kept.transaction_id
    )
    assert kept_entry["future_field"] == {"nested": "value"}, (
        "未知欄位必須原樣保留"
    )


# ---------------------------------------------------------------------------
# 測試 23–24 + safety scanning：不接 Mock LINE、不碰 filesystem API
# ---------------------------------------------------------------------------


def test_cleanup_not_wired_to_mock_line():
    source = inspect.getsource(mock_line_module)
    assert "prune" not in source, "cleanup 不可接任何 Mock LINE 指令"
    assert "prune_move_transactions" not in source
    assert "prune_transactions" not in source


def test_prune_functions_never_touch_filesystem_ast():
    """AST 驗證：prune 相關 function 不呼叫 rename/move/replace/mkdir、
    不呼叫 rollback API（寫 log 透過既有 _write）。"""
    import app.folder_intelligence.transaction_log as tx_log_module

    source = inspect.getsource(tx_log_module)
    tree = ast.parse(source)
    forbidden_calls = {"rename", "renames", "move", "replace", "mkdir", "makedirs"}
    forbidden_names = {
        "rollback_move_transaction",
        "rollback_move_transaction_by_id",
    }

    def _check_function(node: ast.FunctionDef) -> None:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                if isinstance(inner.func, ast.Attribute):
                    assert inner.func.attr not in forbidden_calls, (
                        f"{node.name} 不可呼叫 .{inner.func.attr}()"
                    )
                if isinstance(inner.func, ast.Name):
                    assert inner.func.id not in forbidden_names, (
                        f"{node.name} 不可呼叫 {inner.func.id}()"
                    )

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and "prune" in node.name:
            found.append(node.name)
            _check_function(node)
    assert "prune_transactions" in found
    assert "prune_move_transactions" in found


def test_module_level_wrapper_delegates(log):
    tx = _tx(["rolled_back"], age_days=90)
    log.save_transaction(tx)

    result = prune_move_transactions(log, older_than_days=30)

    assert result.pruned_count == 1
    assert log.load_transaction(tx.transaction_id) is None


def test_prune_dry_run_via_wrapper_does_not_rewrite(log):
    tx = _tx(["rolled_back"], age_days=90)
    log.save_transaction(tx)
    before = log._log_path.read_bytes()

    result = prune_move_transactions(log, older_than_days=30, dry_run=True)

    assert result.dry_run is True
    assert result.pruned_count == 1
    assert log._log_path.read_bytes() == before
