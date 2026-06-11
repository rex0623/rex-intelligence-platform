"""Phase 14F 測試：Rename Transaction Log Rotation / Cleanup。

prune_transactions() 是純維運 API：
- 只動 log 檔，不動任何已更名的檔案。
- 永不刪除仍可回滾（含 success action）的交易。
- 無法解析的 entry 永不刪除。
所有測試使用 pytest tmp_path，不污染 runtime/。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.filename.executor import rollback_transaction_by_id
from app.filename.schemas import RenameTransaction, RenameTransactionAction
from app.filename.transaction_log import RenameTransactionLog


NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _tx(
    tmp_path: Path,
    name: str,
    status: str,
    age_days: int,
) -> RenameTransaction:
    """建立指定狀態與建立時間（NOW 往前 age_days 天）的 transaction。"""
    return RenameTransaction(
        plan_id=f"plan-{name}",
        created_at=NOW - timedelta(days=age_days),
        actions=[
            RenameTransactionAction(
                original_path=str(tmp_path / f"{name}_orig.pdf"),
                new_path=str(tmp_path / f"{name}_new.pdf"),
                status=status,
                rollback_from=str(tmp_path / f"{name}_new.pdf"),
                rollback_to=str(tmp_path / f"{name}_orig.pdf"),
            )
        ],
    )


def _make_log(tmp_path: Path, transactions: list[RenameTransaction]) -> RenameTransactionLog:
    log = RenameTransactionLog(tmp_path / "tx_log.json")
    for tx in transactions:
        log.save_transaction(tx)
    return log


# ---------------------------------------------------------------------------
# 測試 1 + 2：max_age_days 刪除過舊的非可回滾交易，保留近期交易
# ---------------------------------------------------------------------------


def test_prune_by_max_age_removes_old_and_keeps_recent(tmp_path):
    old_tx = _tx(tmp_path, "old", "rolled_back", age_days=60)
    recent_tx = _tx(tmp_path, "recent", "rolled_back", age_days=1)
    log = _make_log(tmp_path, [old_tx, recent_tx])

    result = log.prune_transactions(max_age_days=30, now=NOW)

    assert result.total_before == 2
    assert result.total_after == 1
    assert result.pruned_count == 1
    assert result.pruned_transaction_ids == [old_tx.transaction_id]
    assert log.load_transaction(old_tx.transaction_id) is None
    assert log.load_transaction(recent_tx.transaction_id) is not None


# ---------------------------------------------------------------------------
# 測試 3：仍可回滾（success action）的交易即使過舊也不刪除
# ---------------------------------------------------------------------------


def test_prune_never_removes_rollbackable_transaction(tmp_path):
    old_rollbackable = _tx(tmp_path, "rb", "success", age_days=365)
    old_done = _tx(tmp_path, "done", "rolled_back", age_days=365)
    log = _make_log(tmp_path, [old_rollbackable, old_done])

    result = log.prune_transactions(max_age_days=30, now=NOW)

    assert result.pruned_count == 1
    assert result.kept_rollbackable_count == 1
    assert log.load_transaction(old_rollbackable.transaction_id) is not None, (
        "含 success action 的交易不可被 prune"
    )
    assert log.load_transaction(old_done.transaction_id) is None


def test_prune_keeps_mixed_status_transaction_with_success(tmp_path):
    mixed = RenameTransaction(
        plan_id="plan-mixed",
        created_at=NOW - timedelta(days=100),
        actions=[
            RenameTransactionAction(
                original_path=str(tmp_path / "a.pdf"),
                new_path=str(tmp_path / "b.pdf"),
                status="rolled_back",
            ),
            RenameTransactionAction(
                original_path=str(tmp_path / "c.pdf"),
                new_path=str(tmp_path / "d.pdf"),
                status="success",
            ),
        ],
    )
    log = _make_log(tmp_path, [mixed])

    result = log.prune_transactions(max_age_days=30, now=NOW)

    assert result.pruned_count == 0
    assert result.kept_rollbackable_count == 1
    assert log.load_transaction(mixed.transaction_id) is not None


# ---------------------------------------------------------------------------
# 測試 4 + 5：max_transactions 保留最新 N 筆；超額中的可回滾交易仍保留
# ---------------------------------------------------------------------------


def test_prune_by_max_transactions_keeps_newest(tmp_path):
    txs = [_tx(tmp_path, f"t{i}", "rolled_back", age_days=10 - i) for i in range(5)]
    # t0 最舊（age 10），t4 最新（age 6）
    log = _make_log(tmp_path, txs)

    result = log.prune_transactions(max_transactions=2, now=NOW)

    assert result.total_after == 2
    assert result.pruned_count == 3
    remaining_ids = {t.transaction_id for t in log.list_transactions()}
    assert remaining_ids == {txs[3].transaction_id, txs[4].transaction_id}, (
        "應保留最新 2 筆"
    )


def test_prune_by_max_transactions_skips_rollbackable_in_excess(tmp_path):
    oldest_rollbackable = _tx(tmp_path, "rb", "success", age_days=10)
    middle = _tx(tmp_path, "mid", "rolled_back", age_days=5)
    newest = _tx(tmp_path, "new", "rolled_back", age_days=1)
    log = _make_log(tmp_path, [oldest_rollbackable, middle, newest])

    result = log.prune_transactions(max_transactions=1, now=NOW)

    # 超額 2 筆（rb、mid），但 rb 可回滾 → 只刪 mid
    assert result.pruned_count == 1
    assert result.kept_rollbackable_count == 1
    assert result.pruned_transaction_ids == [middle.transaction_id]
    remaining_ids = {t.transaction_id for t in log.list_transactions()}
    assert remaining_ids == {oldest_rollbackable.transaction_id, newest.transaction_id}


# ---------------------------------------------------------------------------
# 測試 6：無參數為 no-op，檔案不重寫
# ---------------------------------------------------------------------------


def test_prune_without_criteria_is_noop(tmp_path):
    log = _make_log(tmp_path, [_tx(tmp_path, "t", "rolled_back", age_days=365)])
    log_path = tmp_path / "tx_log.json"
    before = log_path.read_bytes()

    result = log.prune_transactions(now=NOW)

    assert result.pruned_count == 0
    assert result.total_before == result.total_after == 1
    assert log_path.read_bytes() == before, "no-op 時不應重寫 log 檔"


def test_prune_with_nothing_matching_does_not_rewrite_file(tmp_path):
    log = _make_log(tmp_path, [_tx(tmp_path, "t", "rolled_back", age_days=1)])
    log_path = tmp_path / "tx_log.json"
    before = log_path.read_bytes()

    result = log.prune_transactions(max_age_days=30, max_transactions=10, now=NOW)

    assert result.pruned_count == 0
    assert log_path.read_bytes() == before


# ---------------------------------------------------------------------------
# 測試 7：兩種條件可同時使用
# ---------------------------------------------------------------------------


def test_prune_combines_age_and_count_criteria(tmp_path):
    too_old = _tx(tmp_path, "old", "rolled_back", age_days=90)      # 過期
    t1 = _tx(tmp_path, "t1", "rolled_back", age_days=3)             # 超額（最舊的近期）
    t2 = _tx(tmp_path, "t2", "rolled_back", age_days=2)
    t3 = _tx(tmp_path, "t3", "rolled_back", age_days=1)
    log = _make_log(tmp_path, [too_old, t1, t2, t3])

    result = log.prune_transactions(max_transactions=2, max_age_days=30, now=NOW)

    assert result.total_after == 2
    remaining_ids = {t.transaction_id for t in log.list_transactions()}
    assert remaining_ids == {t2.transaction_id, t3.transaction_id}


# ---------------------------------------------------------------------------
# 測試 8：無法解析的 entry 永不刪除
# ---------------------------------------------------------------------------


def test_prune_preserves_unparseable_entries(tmp_path):
    log = _make_log(tmp_path, [_tx(tmp_path, "old", "rolled_back", age_days=90)])
    log_path = tmp_path / "tx_log.json"

    # 手動塞入一筆損壞 entry
    data = json.loads(log_path.read_text(encoding="utf-8"))
    data["transactions"].append({"garbage": True, "no_required_fields": 1})
    log_path.write_text(json.dumps(data), encoding="utf-8")

    result = log.prune_transactions(max_age_days=30, now=NOW)

    assert result.total_before == 2
    assert result.pruned_count == 1
    data_after = json.loads(log_path.read_text(encoding="utf-8"))
    assert {"garbage": True, "no_required_fields": 1} in data_after["transactions"], (
        "損壞 entry 不可被 prune"
    )


# ---------------------------------------------------------------------------
# 測試 9：prune 只動 log 檔，不動任何實體檔案
# ---------------------------------------------------------------------------


def test_prune_does_not_touch_renamed_files(tmp_path):
    renamed = tmp_path / "done_new.pdf"
    renamed.write_text("content")
    log = _make_log(tmp_path, [_tx(tmp_path, "done", "rolled_back", age_days=90)])

    files_before = sorted(p.name for p in tmp_path.iterdir())
    result = log.prune_transactions(max_age_days=30, now=NOW)
    files_after = sorted(p.name for p in tmp_path.iterdir())

    assert result.pruned_count == 1
    assert files_before == files_after, "prune 不可新增/刪除/更名任何實體檔案"
    assert renamed.read_text() == "content"


# ---------------------------------------------------------------------------
# 測試 10：prune 後其餘交易的 rollback 行為不變
# ---------------------------------------------------------------------------


def test_rollback_still_works_after_prune(tmp_path):
    (tmp_path / "keep_new.pdf").write_text("content")
    old_done = _tx(tmp_path, "old", "rolled_back", age_days=90)
    keep = _tx(tmp_path, "keep", "success", age_days=90)
    log = _make_log(tmp_path, [old_done, keep])

    prune_result = log.prune_transactions(max_age_days=30, now=NOW)
    assert prune_result.pruned_count == 1

    rollback_result = rollback_transaction_by_id(keep.transaction_id, log)

    assert rollback_result.success_count == 1
    assert (tmp_path / "keep_orig.pdf").exists(), "prune 後 rollback 應照常運作"
    assert log.load_transaction(keep.transaction_id).actions[0].status == "rolled_back"


# ---------------------------------------------------------------------------
# 測試 11：完整生命週期 — rolled_back 後即可被 prune
# ---------------------------------------------------------------------------


def test_fully_rolled_back_transaction_becomes_prunable(tmp_path):
    (tmp_path / "cycle_new.pdf").write_text("content")
    tx = _tx(tmp_path, "cycle", "success", age_days=90)
    log = _make_log(tmp_path, [tx])

    # 可回滾時不可 prune
    first = log.prune_transactions(max_age_days=30, now=NOW)
    assert first.pruned_count == 0
    assert first.kept_rollbackable_count == 1

    # rollback 完成後變為可 prune
    rollback_transaction_by_id(tx.transaction_id, log)
    second = log.prune_transactions(max_age_days=30, now=NOW)
    assert second.pruned_count == 1
    assert log.list_transactions() == []


# ---------------------------------------------------------------------------
# 測試 12：空 log 與不存在的 log 檔安全處理
# ---------------------------------------------------------------------------


def test_prune_on_missing_or_empty_log(tmp_path):
    log = RenameTransactionLog(tmp_path / "does_not_exist.json")

    result = log.prune_transactions(max_age_days=30, max_transactions=5, now=NOW)

    assert result.total_before == 0
    assert result.total_after == 0
    assert result.pruned_count == 0
    assert not (tmp_path / "does_not_exist.json").exists(), "no-op 不應建立 log 檔"
