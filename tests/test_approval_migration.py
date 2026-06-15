"""Phase 20E tests: approvals.json → SQLite migration.

驗證重點：
- _load_approvals_strict: file_not_found / corrupt_json / invalid_structure / valid list
- dry-run 不建立 rip.db / 不修改 approvals.json mtime
- dry-run missing source → missing_source=True，非 fatal
- apply 正確 migrate approvals → SqliteApprovalStore 可讀回
- idempotency：第二次 migrate → already_present_count 正確
- 單筆 invalid approval fail_on_corrupt=False 時 skip，其他照常
- 單筆 invalid approval fail_on_corrupt=True 時 has_errors=True
- empty array
- payload=None round-trip
- expires_at=None round-trip
- unicode payload round-trip
- apply + backup 建立 approvals.json backup
- apply + backup + existing rip.db 建立 db backup（sqlite3.backup WAL-safe）
- dry-run + backup 不建立 backup
- --apply 取得 runtime lock；lock busy → exit 1
- --dry-run 不需要 lock（lock 持有時仍 exit 0）
- CLI --source-json-path override
- CLI --db-path override
- CLI --json-report 輸出合法 JSON
- CLI --fail-on-corrupt 輸出 exit code 2
- approvals.json mtime 不變（apply 後）
- JSON backend 預設不受影響（regression）
- CLI script 可 import 無 side effects
- approval_migration.py 不需要新 pyproject.toml 相依（stdlib only）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.approvals.schemas import Approval
from app.core.approval_migration import (
    ApprovalMigrationResult,
    _load_approvals_strict,
    migrate_approvals,
)

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_EXPIRES = _NOW + timedelta(hours=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approval(
    approval_id: str = "aid-001",
    workflow_id: str = "wf-001",
    status: str = "pending",
    payload: dict | None = None,
    expires_at: datetime | None = None,
) -> Approval:
    return Approval(
        approval_id=approval_id,
        workflow_id=workflow_id,
        status=status,
        created_at=_NOW,
        expires_at=expires_at if expires_at is not None else _EXPIRES,
        payload=payload if payload is not None else {"workflow_id": workflow_id, "title": "test"},
    )


def _write_approvals_json(path: Path, approvals: list[Approval]) -> None:
    """Write approvals as flat JSON array (matches JsonApprovalStore.save schema)."""
    data = [a.model_dump(mode="json") for a in approvals]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_approvals_strict
# ---------------------------------------------------------------------------


def test_load_approvals_strict_file_not_found(tmp_path: Path):
    data, err = _load_approvals_strict(tmp_path / "nonexistent.json")
    assert data is None
    assert err == "file_not_found"


def test_load_approvals_strict_corrupt_json(tmp_path: Path):
    p = tmp_path / "approvals.json"
    p.write_bytes(b"{not valid json")
    data, err = _load_approvals_strict(p)
    assert data is None
    assert err is not None and err.startswith("corrupt_json")


def test_load_approvals_strict_invalid_structure_not_list(tmp_path: Path):
    """Valid JSON but not a list (e.g. dict) → invalid_structure."""
    p = tmp_path / "approvals.json"
    p.write_text(json.dumps({"approvals": []}), encoding="utf-8")
    data, err = _load_approvals_strict(p)
    assert data is None
    assert err == "invalid_structure"


def test_load_approvals_strict_valid_list(tmp_path: Path):
    p = tmp_path / "approvals.json"
    _write_approvals_json(p, [_approval()])
    data, err = _load_approvals_strict(p)
    assert err is None
    assert isinstance(data, list)
    assert len(data) == 1


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_create_rip_db(tmp_path: Path):
    """dry_run=True → rip.db must not be created."""
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=True)

    assert not db.exists()
    assert result.dry_run is True
    assert result.migrated_count == 1


def test_dry_run_does_not_modify_approvals_json(tmp_path: Path):
    """dry_run=True → approvals.json mtime unchanged."""
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    mtime_before = approvals_json.stat().st_mtime

    migrate_approvals(approvals_json, tmp_path / "rip.db", dry_run=True)

    assert approvals_json.stat().st_mtime == mtime_before


def test_dry_run_missing_source(tmp_path: Path):
    """dry_run + missing approvals.json → missing_source=True, not fatal."""
    result = migrate_approvals(tmp_path / "approvals.json", tmp_path / "rip.db", dry_run=True)
    assert result.missing_source is True
    assert result.migrated_count == 0
    assert not result.has_errors


def test_dry_run_migrated_count_reflects_source(tmp_path: Path):
    """dry_run migrated_count = number of valid entries in source."""
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(
        approvals_json,
        [_approval("aid-1"), _approval("aid-2"), _approval("aid-3")],
    )
    result = migrate_approvals(approvals_json, tmp_path / "rip.db", dry_run=True)
    assert result.migrated_count == 3
    assert result.already_present_count == 0


# ---------------------------------------------------------------------------
# apply — basic
# ---------------------------------------------------------------------------


def test_apply_writes_to_sqlite(tmp_path: Path, monkeypatch):
    """apply migrates approvals to SQLite; SqliteApprovalStore can read them back."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    a = _approval("aid-migrate", "wf-migrate", "approved")
    _write_approvals_json(approvals_json, [a])

    db = tmp_path / "rip.db"
    result = migrate_approvals(approvals_json, db, dry_run=False)

    assert result.migrated_count == 1
    assert result.already_present_count == 0
    assert db.exists()

    from app.core.sqlite_approval_store import SqliteApprovalStore

    loaded = SqliteApprovalStore().load(Path())
    assert "aid-migrate" in loaded
    assert loaded["aid-migrate"].status == "approved"
    assert loaded["aid-migrate"].workflow_id == "wf-migrate"


def test_apply_idempotent_second_run(tmp_path: Path, monkeypatch):
    """Second migrate → all already_present_count, migrated_count = 0."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(
        approvals_json,
        [_approval("aid-A"), _approval("aid-B")],
    )
    db = tmp_path / "rip.db"

    r1 = migrate_approvals(approvals_json, db, dry_run=False)
    assert r1.migrated_count == 2
    assert r1.already_present_count == 0

    r2 = migrate_approvals(approvals_json, db, dry_run=False)
    assert r2.migrated_count == 0
    assert r2.already_present_count == 2


def test_apply_empty_array(tmp_path: Path):
    """Empty JSON array → migrated_count=0, no DB rows."""
    approvals_json = tmp_path / "approvals.json"
    approvals_json.write_text("[]", encoding="utf-8")
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False)

    assert result.migrated_count == 0
    assert result.corrupted_count == 0


def test_apply_mtime_not_changed(tmp_path: Path):
    """apply must not modify approvals.json (mtime unchanged)."""
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    mtime_before = approvals_json.stat().st_mtime

    migrate_approvals(approvals_json, tmp_path / "rip.db", dry_run=False)

    assert approvals_json.stat().st_mtime == mtime_before


# ---------------------------------------------------------------------------
# apply — corrupt / fail_on_corrupt
# ---------------------------------------------------------------------------


def test_apply_skip_corrupt_entry_fail_on_corrupt_false(tmp_path: Path, monkeypatch):
    """fail_on_corrupt=False: invalid entry skipped, valid entries continue."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    valid_a = _approval("aid-valid")
    # Write one valid + one invalid (missing approval_id) entry
    data = [
        valid_a.model_dump(mode="json"),
        {"workflow_id": "wf-bad", "status": "invalid-status-value"},  # invalid
    ]
    approvals_json.write_text(json.dumps(data), encoding="utf-8")
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False, fail_on_corrupt=False)

    assert result.corrupted_count == 1
    assert result.migrated_count == 1
    assert not result.has_errors
    assert len(result.warnings) >= 1

    from app.core.sqlite_approval_store import SqliteApprovalStore
    loaded = SqliteApprovalStore().load(Path())
    assert "aid-valid" in loaded


def test_apply_fail_on_corrupt_true_sets_has_errors(tmp_path: Path):
    """fail_on_corrupt=True: invalid entry → has_errors=True."""
    approvals_json = tmp_path / "approvals.json"
    data = [{"workflow_id": "wf-bad", "status": "not-a-real-status"}]
    approvals_json.write_text(json.dumps(data), encoding="utf-8")

    result = migrate_approvals(
        approvals_json, tmp_path / "rip.db", dry_run=False, fail_on_corrupt=True
    )

    assert result.has_errors is True
    assert result.corrupted_count >= 1
    assert len(result.errors) >= 1


# ---------------------------------------------------------------------------
# apply — edge cases
# ---------------------------------------------------------------------------


def test_apply_payload_none_roundtrip(tmp_path: Path, monkeypatch):
    """payload=None → stored as NULL → loaded back as None."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    a = Approval(
        approval_id="aid-no-payload",
        workflow_id="wf-np",
        status="pending",
        created_at=_NOW,
        expires_at=_EXPIRES,
        payload=None,
    )
    _write_approvals_json(approvals_json, [a])
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False)
    assert result.migrated_count == 1

    from app.core.sqlite_approval_store import SqliteApprovalStore
    loaded = SqliteApprovalStore().load(Path())
    assert loaded["aid-no-payload"].payload is None


def test_apply_expires_at_none_roundtrip(tmp_path: Path, monkeypatch):
    """expires_at=None → stored as NULL → loaded back as None."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    a = Approval(
        approval_id="aid-no-expiry",
        workflow_id="wf-ne",
        status="pending",
        created_at=_NOW,
        expires_at=None,
        payload={"title": "no expiry"},
    )
    _write_approvals_json(approvals_json, [a])
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False)
    assert result.migrated_count == 1

    from app.core.sqlite_approval_store import SqliteApprovalStore
    loaded = SqliteApprovalStore().load(Path())
    assert loaded["aid-no-expiry"].expires_at is None


def test_apply_unicode_payload_roundtrip(tmp_path: Path, monkeypatch):
    """payload 含中文 / emoji → ensure_ascii=False → 正確 round-trip。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    a = _approval(
        "aid-unicode",
        payload={"title": "電費單整理", "summary": "台電 💡 2025/12"},
    )
    _write_approvals_json(approvals_json, [a])
    db = tmp_path / "rip.db"

    migrate_approvals(approvals_json, db, dry_run=False)

    from app.core.sqlite_approval_store import SqliteApprovalStore
    loaded = SqliteApprovalStore().load(Path())
    assert loaded["aid-unicode"].payload["title"] == "電費單整理"
    assert loaded["aid-unicode"].payload["summary"] == "台電 💡 2025/12"


def test_apply_all_status_values_roundtrip(tmp_path: Path, monkeypatch):
    """pending / approved / rejected / expired 四種 status 全部正確 round-trip。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    approvals_json = tmp_path / "approvals.json"
    statuses = ["pending", "approved", "rejected", "expired"]
    approvals = [_approval(f"aid-{s}", status=s) for s in statuses]
    _write_approvals_json(approvals_json, approvals)
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False)
    assert result.migrated_count == 4

    from app.core.sqlite_approval_store import SqliteApprovalStore
    loaded = SqliteApprovalStore().load(Path())
    for s in statuses:
        assert loaded[f"aid-{s}"].status == s


# ---------------------------------------------------------------------------
# backup
# ---------------------------------------------------------------------------


def test_backup_creates_approvals_json_backup(tmp_path: Path):
    """--apply --backup → approvals.json.bak_* 建立。"""
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        code = main(
            [
                "--apply",
                "--backup",
                "--source-json-path",
                str(approvals_json),
                "--db-path",
                str(db),
            ]
        )

    assert code == 0
    bak_files = list(tmp_path.glob("approvals.json.bak_*"))
    assert len(bak_files) == 1


def test_backup_creates_db_backup_when_db_exists(tmp_path: Path):
    """--apply --backup + existing rip.db → db.bak_* 建立（sqlite3.backup）。"""
    from app.core.sqlite_transaction_log import initialize_sqlite_schema
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"
    initialize_sqlite_schema(db)  # pre-create the DB

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        code = main(
            [
                "--apply",
                "--backup",
                "--source-json-path",
                str(approvals_json),
                "--db-path",
                str(db),
            ]
        )

    assert code == 0
    bak_files = list(tmp_path.glob("rip.db.bak_*"))
    assert len(bak_files) == 1


def test_dry_run_backup_does_not_create_backup(tmp_path: Path):
    """dry-run + --backup → backup ファイル不建立。"""
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"

    code = main(
        [
            "--dry-run",
            "--backup",
            "--source-json-path",
            str(approvals_json),
            "--db-path",
            str(db),
        ]
    )

    assert code == 0
    assert not list(tmp_path.glob("*.bak_*"))


# ---------------------------------------------------------------------------
# runtime lock
# ---------------------------------------------------------------------------


def test_apply_acquires_runtime_lock(tmp_path: Path):
    """--apply 必須取得 runtime lock；lock busy → exit 1。"""
    from app.core.runtime_lock import acquire_runtime_lock
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        with acquire_runtime_lock():
            code = main(
                [
                    "--apply",
                    "--source-json-path",
                    str(approvals_json),
                    "--db-path",
                    str(db),
                ]
            )

    assert code == 1
    assert not db.exists()  # lock busy → no writes


def test_dry_run_does_not_need_lock(tmp_path: Path):
    """dry-run 不需要 runtime lock（lock busy 時仍 exit 0，不建立 rip.db）。"""
    from app.core.runtime_lock import acquire_runtime_lock
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])
    db = tmp_path / "rip.db"

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        with acquire_runtime_lock():
            code = main(
                [
                    "--dry-run",
                    "--source-json-path",
                    str(approvals_json),
                    "--db-path",
                    str(db),
                ]
            )

    assert code == 0
    assert not db.exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_source_json_path_override(tmp_path: Path):
    """--source-json-path 指定非預設路徑的 approvals.json。"""
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    approvals_json = other_dir / "approvals.json"
    _write_approvals_json(approvals_json, [_approval("aid-override")])
    db = tmp_path / "rip.db"

    result = migrate_approvals(approvals_json, db, dry_run=False)
    assert result.migrated_count == 1
    assert result.source_path == approvals_json


def test_cli_db_path_override(tmp_path: Path):
    """--db-path 寫入非預設路徑的 SQLite DB。"""
    custom_db = tmp_path / "custom" / "mydb.db"
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])

    result = migrate_approvals(approvals_json, custom_db, dry_run=False)
    assert result.migrated_count == 1
    assert custom_db.exists()


def test_cli_json_report_outputs_valid_json(tmp_path: Path, capsys):
    """--json-report 輸出合法 JSON。"""
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval()])

    code = main(
        [
            "--dry-run",
            "--source-json-path",
            str(approvals_json),
            "--db-path",
            str(tmp_path / "rip.db"),
            "--json-report",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, dict)
    assert parsed["kind"] == "approval"
    assert "migrated_count" in parsed


def test_cli_fail_on_corrupt_exit_code_2(tmp_path: Path):
    """corrupt entry + --fail-on-corrupt → exit code 2。"""
    from scripts.migrate_approvals import main

    approvals_json = tmp_path / "approvals.json"
    data = [{"workflow_id": "wf-bad", "status": "NOT_VALID"}]
    approvals_json.write_text(json.dumps(data), encoding="utf-8")

    with patch("app.core.runtime_lock.get_runtime_dir", return_value=tmp_path):
        code = main(
            [
                "--apply",
                "--source-json-path",
                str(approvals_json),
                "--db-path",
                str(tmp_path / "rip.db"),
                "--fail-on-corrupt",
            ]
        )

    assert code == 2


def test_cli_script_importable():
    """scripts/migrate_approvals.py 可 import，無 side effects。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migrate_approvals",
        Path(__file__).parent.parent / "scripts" / "migrate_approvals.py",
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert hasattr(mod, "main")


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def test_json_backend_not_affected(tmp_path: Path, monkeypatch):
    """APPROVAL_STORE_BACKEND=json → JsonApprovalStore 行為不受 migration 影響。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    # Migration from JSON source to SQLite DB
    approvals_json = tmp_path / "approvals.json"
    _write_approvals_json(approvals_json, [_approval("aid-json-safe")])
    migrate_approvals(approvals_json, tmp_path / "rip.db", dry_run=False)

    # JSON backend should still read from approvals.json, not SQLite
    from app.approvals.store import JsonApprovalStore
    loaded = JsonApprovalStore.load(approvals_json)
    assert "aid-json-safe" in loaded
    assert loaded["aid-json-safe"].workflow_id == "wf-001"


def test_no_pyproject_dependency_needed():
    """approval_migration.py は stdlib + app only（新 third-party dependency なし）。"""
    import ast

    src = (
        Path(__file__).parent.parent / "app" / "core" / "approval_migration.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)

    third_party_suspects: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    third_party_suspects.add(alias.name.split(".")[0])
            else:
                if node.module:
                    third_party_suspects.add(node.module.split(".")[0])

    stdlib_and_allowed = {
        "__future__",
        "json",
        "sqlite3",
        "dataclasses",
        "pathlib",
        "typing",
        "app",
    }
    unexpected = third_party_suspects - stdlib_and_allowed
    assert not unexpected, f"Unexpected imports in approval_migration.py: {unexpected}"
