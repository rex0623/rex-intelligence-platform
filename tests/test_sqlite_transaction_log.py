"""Phase 19B 測試：Experimental SQLite transaction log backend.

驗證重點：
- SqliteRenameTransactionLog 滿足 RenameTransactionLogProtocol（isinstance True）
- SqliteMoveTransactionLog 滿足 MoveTransactionLogProtocol（isinstance True）
- 所有操作行為與 JSON backend 合約相容（save/load/list/update/mark）
- action order 以 AUTOINCREMENT id 保留（ORDER BY id ASC）
- prune_transactions 明確 raise NotImplementedError
- 不建立 runtime/rip.db
- JSON default backend 不受影響
- 不 import sqlalchemy
- 所有測試使用 tmp_path，不碰 runtime/
"""

import ast
import importlib.util
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
from app.filename.schemas import RenameTransaction, RenameTransactionAction
from app.folder_intelligence.schemas import MoveTransaction, MoveTransactionAction


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


def test_sqlite_rename_prune_raises_not_implemented(tmp_path: Path):
    log = SqliteRenameTransactionLog(tmp_path / "test.db")
    with pytest.raises(
        NotImplementedError,
        match="prune_transactions not implemented for SQLite backend",
    ):
        log.prune_transactions()


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


def test_sqlite_move_prune_raises_not_implemented(tmp_path: Path):
    log = SqliteMoveTransactionLog(tmp_path / "test.db")
    with pytest.raises(
        NotImplementedError,
        match="prune_transactions not implemented for SQLite backend",
    ):
        log.prune_transactions()


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
