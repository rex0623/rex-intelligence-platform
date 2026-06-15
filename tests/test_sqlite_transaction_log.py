"""Phase 19B / 19L 測試：Experimental SQLite transaction log backend.

驗證重點：
- SqliteRenameTransactionLog 滿足 RenameTransactionLogProtocol（isinstance True）
- SqliteMoveTransactionLog 滿足 MoveTransactionLogProtocol（isinstance True）
- 所有操作行為與 JSON backend 合約相容（save/load/list/update/mark）
- action order 以 AUTOINCREMENT id 保留（ORDER BY id ASC）
- prune_transactions 對齊 JSON backend（Phase 19L）
- 不建立 runtime/rip.db
- JSON default backend 不受影響
- 不 import sqlalchemy
- 所有測試使用 tmp_path，不碰 runtime/
"""

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.sqlite_transaction_log import (
    SqliteMoveTransactionLog,
    SqliteRenameTransactionLog,
    initialize_sqlite_schema,
)
from app.core.transaction_log_protocol import (
    MoveTransactionLogProtocol,
    RenameTransactionLogProtocol,
)
from app.filename.schemas import (
    RenameTransaction,
    RenameTransactionAction,
    TransactionLogPruneResult,
)
from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
    MoveTransactionLogPruneResult,
)

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rename_tx(plan_id: str = "plan-1", n_actions: int = 2) -> RenameTransaction:
    actions = [
        RenameTransactionAction(
            original_path=f"/src/file{i}.pdf",
            new_path=f"/dst/file{i}_renamed.pdf",
            status="pending",
        )
        for i in range(n_actions)
    ]
    return RenameTransaction(plan_id=plan_id, actions=actions)


def _make_move_tx(plan_id: str = "plan-1", n_actions: int = 2) -> MoveTransaction:
    actions = [
        MoveTransactionAction(
            original_path=f"/src/file{i}.pdf",
            new_path=f"/dst/folder{i}/file{i}.pdf",
            status="pending",
        )
        for i in range(n_actions)
    ]
    return MoveTransaction(plan_id=plan_id, actions=actions)


# ---------------------------------------------------------------------------
# Connection / schema tests
# ---------------------------------------------------------------------------


def test_initialize_schema_creates_db_file(tmp_path: Path):
    db = tmp_path / "test.db"
    assert not db.exists()
    initialize_sqlite_schema(db)
    assert db.exists()


def test_initialize_schema_creates_expected_tables(tmp_path: Path):
    import sqlite3

    db = tmp_path / "test.db"
    initialize_sqlite_schema(db)
    conn = sqlite3.connect(str(db))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "schema_version" in tables
    assert "rename_transactions" in tables
    assert "rename_transaction_actions" in tables
    assert "move_transactions" in tables
    assert "move_transaction_actions" in tables


def test_initialize_schema_idempotent(tmp_path: Path):
    db = tmp_path / "test.db"
    initialize_sqlite_schema(db)
    initialize_sqlite_schema(db)
    initialize_sqlite_schema(db)


def test_sqlite_module_does_not_create_files_on_import():
    """Importing app.core.sqlite_transaction_log must not create any DB files."""
    import app.core.sqlite_transaction_log  # noqa: F401

    assert not Path("runtime/rip.db").exists()
    assert not Path("rip.db").exists()


def test_no_runtime_rip_db_created(tmp_path: Path):
    """Using SQLite classes with tmp_path must not create runtime/rip.db."""
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = _make_rename_tx()
    log.save_transaction(tx)
    assert not Path("runtime/rip.db").exists()


# ---------------------------------------------------------------------------
# Protocol isinstance tests
# ---------------------------------------------------------------------------


def test_sqlite_rename_satisfies_protocol(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    assert isinstance(log, RenameTransactionLogProtocol)


def test_sqlite_move_satisfies_protocol(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    assert isinstance(log, MoveTransactionLogProtocol)


# ---------------------------------------------------------------------------
# Rename backend tests
# ---------------------------------------------------------------------------


def test_sqlite_rename_save_and_load_roundtrip(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = _make_rename_tx(plan_id="plan-abc")
    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.transaction_id == tx.transaction_id
    assert loaded.plan_id == "plan-abc"
    assert len(loaded.actions) == 2
    assert loaded.actions[0].original_path == "/src/file0.pdf"
    assert loaded.actions[0].status == "pending"


def test_sqlite_rename_load_nonexistent_returns_none(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    assert log.load_transaction("nonexistent-id") is None


def test_sqlite_rename_list_transactions_empty(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    assert log.list_transactions() == []


def test_sqlite_rename_list_transactions_multiple(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx1 = _make_rename_tx(plan_id="plan-1")
    tx2 = _make_rename_tx(plan_id="plan-2")
    tx3 = _make_rename_tx(plan_id="plan-3")
    log.save_transaction(tx1)
    log.save_transaction(tx2)
    log.save_transaction(tx3)
    result = log.list_transactions()
    assert len(result) == 3
    ids = {tx.transaction_id for tx in result}
    assert tx1.transaction_id in ids
    assert tx2.transaction_id in ids
    assert tx3.transaction_id in ids


def test_sqlite_rename_update_transaction_replaces(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = _make_rename_tx()
    log.save_transaction(tx)
    tx.actions[0] = RenameTransactionAction(
        original_path=tx.actions[0].original_path,
        new_path=tx.actions[0].new_path,
        status="success",
        rollback_from="/dst/file0_renamed.pdf",
        rollback_to="/src/file0.pdf",
    )
    log.update_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.actions[0].status == "success"
    assert loaded.actions[0].rollback_from == "/dst/file0_renamed.pdf"


def test_sqlite_rename_mark_actions_by_original_path(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = _make_rename_tx()
    log.save_transaction(tx)
    updated = log.mark_transaction_actions(
        tx.transaction_id,
        {"/src/file0.pdf": "success"},
    )
    assert updated is not None
    assert updated.actions[0].status == "success"
    assert updated.actions[1].status == "pending"


def test_sqlite_rename_mark_actions_by_new_path(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = _make_rename_tx()
    log.save_transaction(tx)
    updated = log.mark_transaction_actions(
        tx.transaction_id,
        {"/dst/file1_renamed.pdf": "failed"},
    )
    assert updated is not None
    assert updated.actions[0].status == "pending"
    assert updated.actions[1].status == "failed"


def test_sqlite_rename_actions_preserve_order(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    tx = RenameTransaction(
        plan_id="ordered-plan",
        actions=[
            RenameTransactionAction(
                original_path=f"/src/z{i}.pdf",
                new_path=f"/dst/z{i}.pdf",
                status="pending",
            )
            for i in range(5)
        ],
    )
    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    for i, action in enumerate(loaded.actions):
        assert action.original_path == f"/src/z{i}.pdf"


# ---------------------------------------------------------------------------
# Rename prune tests (Phase 19L — mirrors test_transaction_log_rotation.py)
# ---------------------------------------------------------------------------


def _rename_tx(
    db_path: Path,
    name: str,
    status: str,
    age_days: int,
) -> RenameTransaction:
    tx = RenameTransaction(
        plan_id=f"plan-{name}",
        created_at=_NOW - timedelta(days=age_days),
        actions=[
            RenameTransactionAction(
                original_path=f"/src/{name}_orig.pdf",
                new_path=f"/dst/{name}_new.pdf",
                status=status,
                rollback_from=f"/dst/{name}_new.pdf",
                rollback_to=f"/src/{name}_orig.pdf",
            )
        ],
    )
    return tx


def _rename_log(tmp_path: Path, txs: list[RenameTransaction]) -> SqliteRenameTransactionLog:
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    for tx in txs:
        log.save_transaction(tx)
    return log


def test_sqlite_rename_prune_by_age_removes_old(tmp_path: Path):
    old = _rename_tx(tmp_path, "old", "rolled_back", age_days=60)
    recent = _rename_tx(tmp_path, "recent", "rolled_back", age_days=1)
    log = _rename_log(tmp_path, [old, recent])

    result = log.prune_transactions(max_age_days=30, now=_NOW)

    assert result.total_before == 2
    assert result.total_after == 1
    assert result.pruned_count == 1
    assert result.pruned_transaction_ids == [old.transaction_id]
    assert log.load_transaction(old.transaction_id) is None
    assert log.load_transaction(recent.transaction_id) is not None


def test_sqlite_rename_prune_never_removes_rollbackable(tmp_path: Path):
    old_rb = _rename_tx(tmp_path, "rb", "success", age_days=365)
    old_done = _rename_tx(tmp_path, "done", "rolled_back", age_days=365)
    log = _rename_log(tmp_path, [old_rb, old_done])

    result = log.prune_transactions(max_age_days=30, now=_NOW)

    assert result.pruned_count == 1
    assert result.kept_rollbackable_count == 1
    assert log.load_transaction(old_rb.transaction_id) is not None
    assert log.load_transaction(old_done.transaction_id) is None


def test_sqlite_rename_prune_keeps_mixed_status_with_success(tmp_path: Path):
    tx = RenameTransaction(
        plan_id="plan-mixed",
        created_at=_NOW - timedelta(days=100),
        actions=[
            RenameTransactionAction(
                original_path="/src/a.pdf", new_path="/dst/a.pdf", status="rolled_back"
            ),
            RenameTransactionAction(
                original_path="/src/b.pdf", new_path="/dst/b.pdf", status="success"
            ),
        ],
    )
    log = _rename_log(tmp_path, [tx])

    result = log.prune_transactions(max_age_days=30, now=_NOW)

    assert result.pruned_count == 0
    assert result.kept_rollbackable_count == 1
    assert log.load_transaction(tx.transaction_id) is not None


def test_sqlite_rename_prune_by_max_transactions_keeps_newest(tmp_path: Path):
    txs = [_rename_tx(tmp_path, f"t{i}", "rolled_back", age_days=10 - i) for i in range(5)]
    log = _rename_log(tmp_path, txs)

    result = log.prune_transactions(max_transactions=2, now=_NOW)

    assert result.total_after == 2
    assert result.pruned_count == 3
    remaining = {t.transaction_id for t in log.list_transactions()}
    assert remaining == {txs[3].transaction_id, txs[4].transaction_id}


def test_sqlite_rename_prune_max_transactions_skips_rollbackable(tmp_path: Path):
    oldest_rb = _rename_tx(tmp_path, "rb", "success", age_days=10)
    middle = _rename_tx(tmp_path, "mid", "rolled_back", age_days=5)
    newest = _rename_tx(tmp_path, "new", "rolled_back", age_days=1)
    log = _rename_log(tmp_path, [oldest_rb, middle, newest])

    result = log.prune_transactions(max_transactions=1, now=_NOW)

    assert result.pruned_count == 1
    assert result.kept_rollbackable_count == 1
    assert result.pruned_transaction_ids == [middle.transaction_id]
    remaining = {t.transaction_id for t in log.list_transactions()}
    assert remaining == {oldest_rb.transaction_id, newest.transaction_id}


def test_sqlite_rename_prune_no_criteria_is_noop(tmp_path: Path):
    log = _rename_log(tmp_path, [_rename_tx(tmp_path, "t", "rolled_back", age_days=365)])

    result = log.prune_transactions(now=_NOW)

    assert result.pruned_count == 0
    assert result.total_before == result.total_after == 1


def test_sqlite_rename_prune_combined_age_and_count(tmp_path: Path):
    too_old = _rename_tx(tmp_path, "old", "rolled_back", age_days=90)
    t1 = _rename_tx(tmp_path, "t1", "rolled_back", age_days=3)
    t2 = _rename_tx(tmp_path, "t2", "rolled_back", age_days=2)
    t3 = _rename_tx(tmp_path, "t3", "rolled_back", age_days=1)
    log = _rename_log(tmp_path, [too_old, t1, t2, t3])

    result = log.prune_transactions(max_transactions=2, max_age_days=30, now=_NOW)

    assert result.total_after == 2
    remaining = {t.transaction_id for t in log.list_transactions()}
    assert remaining == {t2.transaction_id, t3.transaction_id}


def test_sqlite_rename_prune_empty_db_is_noop(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")

    result = log.prune_transactions(max_age_days=30, max_transactions=5, now=_NOW)

    assert result.total_before == 0
    assert result.total_after == 0
    assert result.pruned_count == 0


def test_sqlite_rename_prune_result_is_correct_type(tmp_path: Path):
    log = _rename_log(tmp_path, [_rename_tx(tmp_path, "t", "rolled_back", age_days=60)])

    result = log.prune_transactions(max_age_days=30, now=_NOW)

    assert isinstance(result, TransactionLogPruneResult)
    assert hasattr(result, "total_before")
    assert hasattr(result, "total_after")
    assert hasattr(result, "pruned_count")
    assert hasattr(result, "kept_rollbackable_count")
    assert hasattr(result, "pruned_transaction_ids")


def test_sqlite_rename_prune_cascade_deletes_actions(tmp_path: Path):
    import sqlite3
    tx = _rename_tx(tmp_path, "old", "rolled_back", age_days=60)
    log = _rename_log(tmp_path, [tx])

    log.prune_transactions(max_age_days=30, now=_NOW)

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    action_count = conn.execute(
        "SELECT COUNT(*) FROM rename_transaction_actions WHERE transaction_id=?",
        (tx.transaction_id,),
    ).fetchone()[0]
    conn.close()
    assert action_count == 0, "ON DELETE CASCADE must remove orphaned actions"


# ---------------------------------------------------------------------------
# Move backend tests
# ---------------------------------------------------------------------------


def test_sqlite_move_save_and_load_roundtrip(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx = _make_move_tx(plan_id="move-plan-abc")
    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.transaction_id == tx.transaction_id
    assert loaded.plan_id == "move-plan-abc"
    assert len(loaded.actions) == 2
    assert loaded.actions[0].original_path == "/src/file0.pdf"
    assert loaded.actions[0].status == "pending"


def test_sqlite_move_load_nonexistent_returns_none(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    assert log.load_transaction("nonexistent-id") is None


def test_sqlite_move_list_transactions_empty(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    assert log.list_transactions() == []


def test_sqlite_move_list_transactions_multiple(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx1 = _make_move_tx(plan_id="plan-1")
    tx2 = _make_move_tx(plan_id="plan-2")
    tx3 = _make_move_tx(plan_id="plan-3")
    log.save_transaction(tx1)
    log.save_transaction(tx2)
    log.save_transaction(tx3)
    result = log.list_transactions()
    assert len(result) == 3
    ids = {tx.transaction_id for tx in result}
    assert tx1.transaction_id in ids
    assert tx2.transaction_id in ids
    assert tx3.transaction_id in ids


def test_sqlite_move_update_transaction_replaces(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx = _make_move_tx()
    log.save_transaction(tx)
    tx.actions[0] = MoveTransactionAction(
        original_path=tx.actions[0].original_path,
        new_path=tx.actions[0].new_path,
        status="success",
        rollback_from="/dst/folder0/file0.pdf",
        rollback_to="/src/file0.pdf",
    )
    log.update_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.actions[0].status == "success"
    assert loaded.actions[0].rollback_from == "/dst/folder0/file0.pdf"


def test_sqlite_move_mark_actions_by_original_path(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx = _make_move_tx()
    log.save_transaction(tx)
    updated = log.mark_transaction_actions(
        tx.transaction_id,
        {"/src/file0.pdf": "success"},
    )
    assert updated is not None
    assert updated.actions[0].status == "success"
    assert updated.actions[1].status == "pending"


def test_sqlite_move_mark_actions_by_new_path(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx = _make_move_tx()
    log.save_transaction(tx)
    updated = log.mark_transaction_actions(
        tx.transaction_id,
        {"/dst/folder1/file1.pdf": "failed"},
    )
    assert updated is not None
    assert updated.actions[0].status == "pending"
    assert updated.actions[1].status == "failed"


def test_sqlite_move_actions_preserve_order(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    tx = MoveTransaction(
        plan_id="ordered-move-plan",
        actions=[
            MoveTransactionAction(
                original_path=f"/src/z{i}.pdf",
                new_path=f"/dst/folder/z{i}.pdf",
                status="pending",
            )
            for i in range(5)
        ],
    )
    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    for i, action in enumerate(loaded.actions):
        assert action.original_path == f"/src/z{i}.pdf"


# ---------------------------------------------------------------------------
# Move prune tests (Phase 19L — mirrors test_move_transaction_log_rotation.py)
# ---------------------------------------------------------------------------


def _move_tx(
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


def _move_log(tmp_path: Path, txs: list[MoveTransaction]) -> SqliteMoveTransactionLog:
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    for tx in txs:
        log.save_transaction(tx)
    return log


def test_sqlite_move_prune_empty_db_is_noop(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.before_count == 0
    assert result.after_count == 0
    assert result.pruned_count == 0
    assert result.retained_count == 0
    assert result.protected_count == 0


def test_sqlite_move_prune_keeps_protected_even_if_old(tmp_path: Path):
    tx = _move_tx(["success", "rolled_back"], age_days=365)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_count == 0
    assert result.protected_count == 1
    assert tx.transaction_id in result.protected_transaction_ids
    assert log.load_transaction(tx.transaction_id) is not None


def test_sqlite_move_prune_deletes_old_rolled_back(tmp_path: Path):
    tx = _move_tx(["rolled_back", "rolled_back"], age_days=60)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_count == 1
    assert tx.transaction_id in result.pruned_transaction_ids
    assert log.load_transaction(tx.transaction_id) is None


def test_sqlite_move_prune_retains_recent(tmp_path: Path):
    tx = _move_tx(["rolled_back"], age_days=5)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_count == 0
    assert result.retained_count == 1
    assert tx.transaction_id in result.retained_transaction_ids
    assert log.load_transaction(tx.transaction_id) is not None


def test_sqlite_move_prune_deletes_old_failed(tmp_path: Path):
    tx = _move_tx(["failed", "failed"], age_days=60)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_count == 1
    assert log.load_transaction(tx.transaction_id) is None


def test_sqlite_move_prune_deletes_old_pending(tmp_path: Path):
    tx = _move_tx(["pending"], age_days=60)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_count == 1
    assert log.load_transaction(tx.transaction_id) is None


def test_sqlite_move_prune_dry_run_does_not_delete(tmp_path: Path):
    tx = _move_tx(["rolled_back"], age_days=60)
    log = _move_log(tmp_path, [tx])

    result = log.prune_transactions(older_than_days=30, dry_run=True, now=_NOW)

    assert result.dry_run is True
    assert result.pruned_count == 1
    assert tx.transaction_id in result.pruned_transaction_ids
    assert log.load_transaction(tx.transaction_id) is not None, "dry_run must not delete"


def test_sqlite_move_prune_dry_run_after_count_is_predicted(tmp_path: Path):
    prunable = _move_tx(["rolled_back"], age_days=60)
    retained = _move_tx(["rolled_back"], age_days=5)
    log = _move_log(tmp_path, [prunable, retained])

    result = log.prune_transactions(older_than_days=30, dry_run=True, now=_NOW)

    assert result.dry_run is True
    assert result.before_count == 2
    assert result.after_count == 1, "after_count must reflect predicted result"
    assert log.list_transactions().__len__() == 2, "DB unchanged in dry_run"


def test_sqlite_move_prune_corrupted_always_zero(tmp_path: Path):
    log = _move_log(tmp_path, [_move_tx(["rolled_back"], age_days=60)])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.corrupted_count == 0
    assert result.corrupted_entries == 0


def test_sqlite_move_prune_result_counts_correct(tmp_path: Path):
    protected = _move_tx(["success"], age_days=90)
    prunable = _move_tx(["rolled_back"], age_days=90)
    retained = _move_tx(["failed"], age_days=1)
    log = _move_log(tmp_path, [protected, prunable, retained])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.before_count == 3
    assert result.pruned_count == 1
    assert result.protected_count == 1
    assert result.retained_count == 1
    assert result.after_count == 2
    assert result.corrupted_count == 0


def test_sqlite_move_prune_protected_ids_reported(tmp_path: Path):
    protected = _move_tx(["success"], age_days=90)
    prunable = _move_tx(["rolled_back"], age_days=90)
    log = _move_log(tmp_path, [protected, prunable])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.protected_transaction_ids == [protected.transaction_id]


def test_sqlite_move_prune_pruned_ids_reported(tmp_path: Path):
    prunable = _move_tx(["rolled_back"], age_days=90)
    retained = _move_tx(["rolled_back"], age_days=5)
    log = _move_log(tmp_path, [prunable, retained])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.pruned_transaction_ids == [prunable.transaction_id]


def test_sqlite_move_prune_retained_ids_reported(tmp_path: Path):
    retained = _move_tx(["failed"], age_days=1)
    log = _move_log(tmp_path, [retained])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert result.retained_transaction_ids == [retained.transaction_id]


def test_sqlite_move_prune_result_is_correct_type(tmp_path: Path):
    log = _move_log(tmp_path, [_move_tx(["rolled_back"], age_days=60)])

    result = log.prune_transactions(older_than_days=30, now=_NOW)

    assert isinstance(result, MoveTransactionLogPruneResult)


def test_sqlite_move_prune_cascade_deletes_actions(tmp_path: Path):
    import sqlite3
    tx = _move_tx(["rolled_back"], age_days=60)
    log = _move_log(tmp_path, [tx])

    log.prune_transactions(older_than_days=30, now=_NOW)

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    action_count = conn.execute(
        "SELECT COUNT(*) FROM move_transaction_actions WHERE transaction_id=?",
        (tx.transaction_id,),
    ).fetchone()[0]
    conn.close()
    assert action_count == 0, "ON DELETE CASCADE must remove orphaned actions"


# ---------------------------------------------------------------------------
# Regression / safety tests
# ---------------------------------------------------------------------------


def test_default_rename_transaction_log_still_json():
    from app.filename.transaction_log import RenameTransactionLog

    assert RenameTransactionLog is not SqliteRenameTransactionLog


def test_default_move_transaction_log_still_json():
    from app.folder_intelligence.approval_bridge import default_move_transaction_log
    from app.folder_intelligence.transaction_log import MoveTransactionLog

    log = default_move_transaction_log()
    assert isinstance(log, MoveTransactionLog)
    assert not isinstance(log, SqliteMoveTransactionLog)


def test_sqlite_transaction_log_does_not_import_sqlalchemy():
    spec = importlib.util.find_spec("app.core.sqlite_transaction_log")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sqlalchemy" not in alias.name.lower(), (
                    f"Unexpected sqlalchemy import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "sqlalchemy" not in module.lower(), (
                f"Unexpected sqlalchemy import from: {module}"
            )


def test_sqlite_transaction_log_uses_stdlib_sqlite3():
    spec = importlib.util.find_spec("app.core.sqlite_transaction_log")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    assert "import sqlite3" in source
