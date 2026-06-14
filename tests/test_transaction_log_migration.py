"""Phase 19J tests: JSON → SQLite transaction log migration.

驗證重點：
- dry-run 不寫 DB / 不建立 DB 檔案
- apply 正確 migrate rename / move transactions
- idempotency：同一 transaction_id 第二次 skip（already_present_count++）
- action order 保留
- rollback_from / rollback_to nullable 欄位正確 migrate
- source JSON 不存在 → safe no-op
- empty {"transactions": []} → safe no-op
- corrupt JSON file → error reported
- corrupt transaction entry → skip，其餘繼續
- illegal status → Pydantic validation error → skip
- migration_result counts 正確
- backup 建立 bak 檔
- DB 備份使用 sqlite3 backup
- dry-run 不建立 backup
- apply 取得 runtime lock
- lock busy → return 1
- --source-json-dir / --db-path override
- --rename-only / --move-only
- --fail-on-corrupt exit code
- --json-report 輸出合法 JSON
- approvals.json 不被碰
- dry-run 不建立 rip.db
- backend=sqlite 能讀到 migrated data
- backend=json 不受影響
- CLI script 可 import
- 不需要 pyproject.toml 異動（stdlib only）
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.transaction_log_migration import (
    MigrationResult,
    _load_json_strict,
    migrate_all,
    migrate_move_transactions,
    migrate_rename_transactions,
)
from app.filename.schemas import RenameTransaction, RenameTransactionAction
from app.folder_intelligence.schemas import MoveTransaction, MoveTransactionAction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rename_tx(
    plan_id: str = "plan-r",
    n: int = 2,
    statuses: list[str] | None = None,
) -> RenameTransaction:
    statuses = statuses or ["success"] * n
    actions = [
        RenameTransactionAction(
            original_path=f"/src/a{i}.pdf",
            new_path=f"/dst/a{i}_new.pdf",
            status=statuses[i],
            rollback_from=f"/dst/a{i}_new.pdf" if statuses[i] == "success" else None,
            rollback_to=f"/src/a{i}.pdf" if statuses[i] == "success" else None,
        )
        for i in range(n)
    ]
    return RenameTransaction(plan_id=plan_id, actions=actions)


def _make_move_tx(
    plan_id: str = "plan-m",
    n: int = 2,
    statuses: list[str] | None = None,
) -> MoveTransaction:
    statuses = statuses or ["success"] * n
    actions = [
        MoveTransactionAction(
            original_path=f"/src/b{i}.pdf",
            new_path=f"/dst/b{i}_moved.pdf",
            status=statuses[i],
            rollback_from=f"/dst/b{i}_moved.pdf" if statuses[i] == "success" else None,
            rollback_to=f"/src/b{i}.pdf" if statuses[i] == "success" else None,
        )
        for i in range(n)
    ]
    return MoveTransaction(plan_id=plan_id, actions=actions)


def _write_rename_json(path: Path, transactions: list[RenameTransaction]) -> None:
    data = {"transactions": [tx.model_dump(mode="json") for tx in transactions]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_move_json(path: Path, transactions: list[MoveTransaction]) -> None:
    data = {"transactions": [tx.model_dump(mode="json") for tx in transactions]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_json_strict
# ---------------------------------------------------------------------------


def test_load_json_strict_file_not_found(tmp_path):
    data, err = _load_json_strict(tmp_path / "nonexistent.json")
    assert data is None
    assert err == "file_not_found"


def test_load_json_strict_corrupt_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_bytes(b"{not valid json")
    data, err = _load_json_strict(p)
    assert data is None
    assert err is not None and err.startswith("corrupt_json")


def test_load_json_strict_invalid_structure(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
    data, err = _load_json_strict(p)
    assert data is None
    assert err == "invalid_structure"


def test_load_json_strict_valid(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"transactions": []}), encoding="utf-8")
    data, err = _load_json_strict(p)
    assert err is None
    assert data == {"transactions": []}


# ---------------------------------------------------------------------------
# Core migration — dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write_db(tmp_path):
    """dry-run must not create runtime/rip.db."""
    tx = _make_rename_tx()
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=True)

    assert not db.exists(), "dry-run must not create rip.db"
    assert result.dry_run is True
    assert result.migrated_count == 1
    assert result.missing_source is False


def test_runtime_rip_db_not_created_on_dry_run(tmp_path):
    """migrate_all dry-run leaves DB absent."""
    move_json = tmp_path / "move_transactions.json"
    _write_move_json(move_json, [_make_move_tx()])
    db = tmp_path / "rip.db"

    migrate_all(tmp_path, db, dry_run=True, rename=False, move=True)
    assert not db.exists()


# ---------------------------------------------------------------------------
# Core migration — apply
# ---------------------------------------------------------------------------


def test_apply_migrates_rename_transactions(tmp_path):
    tx = _make_rename_tx(n=3)
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert result.corrupted_count == 0
    assert result.missing_source is False
    assert db.exists()

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    log = SqliteRenameTransactionLog(db)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.transaction_id == tx.transaction_id
    assert len(loaded.actions) == 3


def test_apply_migrates_move_transactions(tmp_path):
    tx = _make_move_tx(n=2)
    move_json = tmp_path / "move_transactions.json"
    _write_move_json(move_json, [tx])
    db = tmp_path / "rip.db"

    result = migrate_move_transactions(move_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert db.exists()

    from app.core.sqlite_transaction_log import SqliteMoveTransactionLog

    log = SqliteMoveTransactionLog(db)
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert len(loaded.actions) == 2


def test_apply_migrates_both(tmp_path):
    rename_tx = _make_rename_tx()
    move_tx = _make_move_tx()
    _write_rename_json(tmp_path / "rename_transactions.json", [rename_tx])
    _write_move_json(tmp_path / "move_transactions.json", [move_tx])
    db = tmp_path / "rip.db"

    results = migrate_all(tmp_path, db, dry_run=False)

    assert results["rename"].migrated_count == 1
    assert results["move"].migrated_count == 1
    assert db.exists()


# ---------------------------------------------------------------------------
# Edge cases — source JSON
# ---------------------------------------------------------------------------


def test_source_json_missing_is_noop(tmp_path):
    db = tmp_path / "rip.db"
    result = migrate_rename_transactions(
        tmp_path / "rename_transactions.json", db, dry_run=False
    )
    assert result.missing_source is True
    assert result.migrated_count == 0
    assert not db.exists()


def test_empty_transactions_is_noop(tmp_path):
    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_text(json.dumps({"transactions": []}), encoding="utf-8")
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 0
    assert result.missing_source is False
    assert not db.exists()


def test_corrupted_json_file_reported(tmp_path):
    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_bytes(b"NOT JSON {{{")
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 0
    assert len(result.errors) >= 1 or len(result.warnings) >= 1
    assert not db.exists()


def test_corrupted_transaction_entry_skipped(tmp_path):
    """A single corrupt entry is skipped; valid entries are migrated."""
    good_tx = _make_rename_tx(plan_id="good")
    good_dict = good_tx.model_dump(mode="json")
    # action with illegal status makes the whole transaction fail model_validate
    bad_dict = {
        "transaction_id": "bad-id",
        "plan_id": "x",
        "created_at": "2024-01-01T00:00:00+00:00",
        "actions": [
            {"original_path": "/a", "new_path": "/b", "status": "ILLEGAL_STATUS"}
        ],
    }

    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_text(
        json.dumps({"transactions": [good_dict, bad_dict]}), encoding="utf-8"
    )
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert result.corrupted_count == 1


def test_illegal_status_in_action_skipped(tmp_path):
    """An action with an illegal status value causes the whole transaction to be skipped."""
    good_tx = _make_rename_tx(plan_id="good")
    good_dict = good_tx.model_dump(mode="json")

    bad_dict = good_tx.model_dump(mode="json")
    bad_dict["transaction_id"] = "bad-status-tx"
    bad_dict["actions"][0]["status"] = "invalid_status_value"

    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_text(
        json.dumps({"transactions": [good_dict, bad_dict]}), encoding="utf-8"
    )
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert result.corrupted_count == 1


def test_action_order_preserved(tmp_path):
    """Actions in SQLite must appear in the same order as in the JSON array."""
    paths = [f"/src/file{i}.pdf" for i in range(5)]
    actions = [
        RenameTransactionAction(
            original_path=p,
            new_path=p.replace("/src/", "/dst/"),
            status="success",
        )
        for p in paths
    ]
    tx = RenameTransaction(plan_id="order-test", actions=actions)
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    migrate_rename_transactions(rename_json, db, dry_run=False)

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    loaded = SqliteRenameTransactionLog(db).load_transaction(tx.transaction_id)
    assert loaded is not None
    loaded_paths = [a.original_path for a in loaded.actions]
    assert loaded_paths == paths


def test_rollback_fields_preserved(tmp_path):
    """rollback_from and rollback_to (nullable) must survive the migration."""
    tx = _make_rename_tx(n=2, statuses=["success", "failed"])
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    migrate_rename_transactions(rename_json, db, dry_run=False)

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    loaded = SqliteRenameTransactionLog(db).load_transaction(tx.transaction_id)
    assert loaded is not None
    success_action = loaded.actions[0]
    assert success_action.rollback_from is not None
    assert success_action.rollback_to is not None
    failed_action = loaded.actions[1]
    assert failed_action.rollback_from is None
    assert failed_action.rollback_to is None


def test_migration_result_counts(tmp_path):
    """MigrationResult fields must accurately reflect what happened."""
    good_tx = _make_rename_tx(plan_id="good")
    good_dict = good_tx.model_dump(mode="json")
    bad_dict = {
        "transaction_id": "bad-id",
        "plan_id": "x",
        "created_at": "2024-01-01T00:00:00+00:00",
        "actions": [
            {"original_path": "/a", "new_path": "/b", "status": "ILLEGAL_STATUS"}
        ],
    }

    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_text(
        json.dumps({"transactions": [good_dict, bad_dict]}), encoding="utf-8"
    )
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert result.corrupted_count == 1
    assert result.already_present_count == 0
    assert result.skipped_count == 0
    assert result.missing_source is False
    assert result.kind == "rename"
    assert result.dry_run is False
    assert result.total_in_source == 2


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_rename_rerun(tmp_path):
    """Running migration twice must not raise and must not change migrated data."""
    tx = _make_rename_tx(n=2)
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    r1 = migrate_rename_transactions(rename_json, db, dry_run=False)
    r2 = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert r1.migrated_count == 1
    assert r2.migrated_count == 0
    assert r2.already_present_count == 1

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    all_txs = SqliteRenameTransactionLog(db).list_transactions()
    assert len(all_txs) == 1


def test_idempotent_move_rerun(tmp_path):
    tx = _make_move_tx(n=2)
    move_json = tmp_path / "move_transactions.json"
    _write_move_json(move_json, [tx])
    db = tmp_path / "rip.db"

    r1 = migrate_move_transactions(move_json, db, dry_run=False)
    r2 = migrate_move_transactions(move_json, db, dry_run=False)

    assert r1.migrated_count == 1
    assert r2.already_present_count == 1

    from app.core.sqlite_transaction_log import SqliteMoveTransactionLog

    assert len(SqliteMoveTransactionLog(db).list_transactions()) == 1


def test_existing_sqlite_transaction_skipped_not_duplicated(tmp_path):
    """A transaction already in SQLite before migration is skipped (not replaced)."""
    tx = _make_rename_tx(plan_id="existing")
    db = tmp_path / "rip.db"

    # Pre-populate SQLite
    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    SqliteRenameTransactionLog(db).save_transaction(tx)

    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])

    result = migrate_rename_transactions(rename_json, db, dry_run=False)

    assert result.already_present_count == 1
    assert result.migrated_count == 0


def test_no_duplicate_action_rows_after_rerun(tmp_path):
    """Repeated migration must not accumulate duplicate action rows."""
    tx = _make_rename_tx(n=3)
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    migrate_rename_transactions(rename_json, db, dry_run=False)
    migrate_rename_transactions(rename_json, db, dry_run=False)

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog

    loaded = SqliteRenameTransactionLog(db).load_transaction(tx.transaction_id)
    assert loaded is not None
    assert len(loaded.actions) == 3  # not 6


# ---------------------------------------------------------------------------
# Integration: SQLite backend reads migrated data
# ---------------------------------------------------------------------------


def test_sqlite_backend_reads_migrated_rename_data(tmp_path, monkeypatch):
    """After migration, make_rename_transaction_log() with sqlite backend can read data."""
    tx = _make_rename_tx(n=2)
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    migrate_rename_transactions(rename_json, db, dry_run=False)

    from app.core.config import settings

    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))

    from app.core.transaction_log_factory import make_rename_transaction_log

    log = make_rename_transaction_log()
    txs = log.list_transactions()
    assert len(txs) == 1
    assert txs[0].transaction_id == tx.transaction_id


def test_sqlite_backend_reads_migrated_move_data(tmp_path, monkeypatch):
    tx = _make_move_tx(n=2)
    move_json = tmp_path / "move_transactions.json"
    _write_move_json(move_json, [tx])
    db = tmp_path / "rip.db"

    migrate_move_transactions(move_json, db, dry_run=False)

    from app.core.config import settings

    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))

    from app.core.transaction_log_factory import make_move_transaction_log

    log = make_move_transaction_log()
    txs = log.list_transactions()
    assert len(txs) == 1
    assert txs[0].transaction_id == tx.transaction_id


def test_rollback_preview_after_migration(tmp_path, monkeypatch):
    """After migration, rollback preview via SQLite backend works."""
    tx = _make_rename_tx(n=2, statuses=["success", "success"])
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"

    migrate_rename_transactions(rename_json, db, dry_run=False)

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog
    from app.filename.transaction_log import preview_rollback_transaction

    log = SqliteRenameTransactionLog(db)
    preview = preview_rollback_transaction(tx.transaction_id, log)
    assert preview is not None
    assert preview.rollbackable_count == 2


def test_backend_json_unaffected(tmp_path, monkeypatch):
    """JSON backend operations are unaffected by migration."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))

    from app.core.transaction_log_factory import make_rename_transaction_log

    log = make_rename_transaction_log()
    assert log.list_transactions() == []

    # Migration does not touch json backend files
    rename_json = tmp_path / "rename_transactions.json"
    tx = _make_rename_tx()
    _write_rename_json(rename_json, [tx])
    db = tmp_path / "rip.db"
    migrate_rename_transactions(rename_json, db, dry_run=False)

    # json backend still reads from the original JSON file
    log2 = make_rename_transaction_log()
    assert len(log2.list_transactions()) == 1


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def test_backup_json_files_created_on_apply_with_backup(tmp_path):
    """--backup creates .bak files for existing JSON source files."""
    rename_json = tmp_path / "rename_transactions.json"
    move_json = tmp_path / "move_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])
    _write_move_json(move_json, [_make_move_tx()])
    db = tmp_path / "rip.db"

    migrate_all(tmp_path, db, dry_run=False, backup=True)

    bak_files = list(tmp_path.glob("*.bak_*"))
    bak_names = [f.name for f in bak_files]
    assert any("rename_transactions" in n for n in bak_names)
    assert any("move_transactions" in n for n in bak_names)


def test_backup_db_created_when_db_exists(tmp_path):
    """--backup creates a DB backup when rip.db already exists."""
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])
    db = tmp_path / "rip.db"

    # First migration creates the DB
    migrate_all(tmp_path, db, dry_run=False, rename=True, move=False)

    # Second migration with backup should back up existing DB
    migrate_all(tmp_path, db, dry_run=False, backup=True, rename=True, move=False)

    db_baks = list(tmp_path.glob("*.db.bak_*"))
    assert len(db_baks) >= 1


def test_no_backup_on_dry_run(tmp_path):
    """dry-run must not create any backup files."""
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])

    migrate_all(tmp_path, tmp_path / "rip.db", dry_run=True, backup=True)

    bak_files = list(tmp_path.glob("*.bak_*"))
    assert len(bak_files) == 0


# ---------------------------------------------------------------------------
# Runtime lock
# ---------------------------------------------------------------------------


def test_apply_acquires_runtime_lock(tmp_path):
    """--apply must acquire the runtime lock; a concurrent holder causes exit code 1."""
    from app.core.runtime_lock import acquire_runtime_lock
    from scripts.migrate_transaction_logs import main

    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])
    db = tmp_path / "rip.db"

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        with acquire_runtime_lock():
            # Lock is held; --apply should return 1
            exit_code = main(
                [
                    "--apply",
                    "--source-json-dir",
                    str(tmp_path),
                    "--db-path",
                    str(db),
                ]
            )
    assert exit_code == 1


def test_runtime_lock_busy_exits_nonzero(tmp_path):
    """main() with --apply returns 1 when lock is busy."""
    from app.core.runtime_lock import acquire_runtime_lock
    from scripts.migrate_transaction_logs import main

    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        with acquire_runtime_lock():
            code = main(
                [
                    "--apply",
                    "--source-json-dir",
                    str(tmp_path),
                    "--db-path",
                    str(tmp_path / "rip.db"),
                ]
            )
    assert code == 1


# ---------------------------------------------------------------------------
# CLI overrides
# ---------------------------------------------------------------------------


def test_source_json_dir_override(tmp_path):
    """--source-json-dir reads JSON from a non-default path."""
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    tx = _make_rename_tx()
    _write_rename_json(other_dir / "rename_transactions.json", [tx])
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(
        other_dir / "rename_transactions.json", db, dry_run=False
    )
    assert result.migrated_count == 1


def test_db_path_override(tmp_path):
    """--db-path writes to a non-default path."""
    custom_db = tmp_path / "custom" / "mydb.db"
    rename_json = tmp_path / "rename_transactions.json"
    _write_rename_json(rename_json, [_make_rename_tx()])

    result = migrate_rename_transactions(rename_json, custom_db, dry_run=False)
    assert result.migrated_count == 1
    assert custom_db.exists()


def test_rename_only_flag(tmp_path):
    """--rename-only skips move migration."""
    _write_move_json(tmp_path / "move_transactions.json", [_make_move_tx()])
    db = tmp_path / "rip.db"

    results = migrate_all(tmp_path, db, dry_run=False, rename=True, move=False)

    assert "move" not in results
    assert "rename" in results
    assert results["rename"].missing_source is True  # no rename JSON present


def test_move_only_flag(tmp_path):
    """--move-only skips rename migration."""
    _write_rename_json(tmp_path / "rename_transactions.json", [_make_rename_tx()])
    db = tmp_path / "rip.db"

    results = migrate_all(tmp_path, db, dry_run=False, rename=False, move=True)

    assert "rename" not in results
    assert "move" in results
    assert results["move"].missing_source is True  # no move JSON present


def test_cli_script_importable():
    """scripts/migrate_transaction_logs.py must be importable without side effects."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migrate_transaction_logs",
        Path(__file__).parent.parent / "scripts" / "migrate_transaction_logs.py",
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert hasattr(mod, "main")


def test_fail_on_corrupt_exit_code(tmp_path):
    """--fail-on-corrupt: corrupt file → result.has_errors=True."""
    rename_json = tmp_path / "rename_transactions.json"
    rename_json.write_bytes(b"NOT JSON")
    db = tmp_path / "rip.db"

    result = migrate_rename_transactions(
        rename_json, db, dry_run=False, fail_on_corrupt=True
    )
    assert result.has_errors is True
    assert len(result.errors) >= 1


def test_json_report_outputs_valid_json(tmp_path, capsys):
    """--json-report outputs valid JSON."""
    _write_rename_json(tmp_path / "rename_transactions.json", [_make_rename_tx()])

    from scripts.migrate_transaction_logs import main

    code = main(
        [
            "--dry-run",
            "--source-json-dir",
            str(tmp_path),
            "--db-path",
            str(tmp_path / "rip.db"),
            "--json-report",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def test_approvals_json_not_touched(tmp_path):
    """Migration must never read or write approvals.json."""
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"approvals": {}}), encoding="utf-8")
    original_mtime = approvals.stat().st_mtime

    _write_rename_json(tmp_path / "rename_transactions.json", [_make_rename_tx()])
    migrate_all(tmp_path, tmp_path / "rip.db", dry_run=False)

    assert approvals.stat().st_mtime == original_mtime


def test_no_pyproject_dependency_needed():
    """Migration module must not require any new pyproject.toml dependencies."""
    import ast
    from pathlib import Path

    src = (
        Path(__file__).parent.parent
        / "app"
        / "core"
        / "transaction_log_migration.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Collect all top-level imports
    third_party_suspects = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    third_party_suspects.add(alias.name.split(".")[0])
            else:
                if node.module:
                    third_party_suspects.add(node.module.split(".")[0])

    # Must not import anything outside stdlib / app/
    stdlib_and_allowed = {
        "__future__", "json", "dataclasses", "pathlib",
        "sqlite3", "datetime", "typing", "app",
    }
    unexpected = third_party_suspects - stdlib_and_allowed
    assert not unexpected, f"Unexpected imports in migration library: {unexpected}"
