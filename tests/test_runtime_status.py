"""Phase 22B tests: app/core/runtime_status.py (read-only diagnostics).

驗證重點：
- JSON backend default 回報正確
- APPROVAL_STORE_BACKEND / TRANSACTION_LOG_BACKEND 混合設定可正確回報
- runtime JSON 檔案 exists=False / exists=True + size_bytes
- rip.db 不存在時不建立、回報 exists=False
- rip.db 存在時可讀 schema_version 與三個 table row count
- table 不存在時不 crash（回報 None）
- collect_runtime_status 不呼叫 acquire_runtime_lock / initialize_sqlite_schema
- collect_runtime_status 不修改任何檔案 mtime
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.core.config as cfg
from app.core.runtime_status import collect_runtime_status
from app.core.sqlite_transaction_log import initialize_sqlite_schema


# ---------------------------------------------------------------------------
# Backend reporting
# ---------------------------------------------------------------------------


def test_reports_json_backend_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "TRANSACTION_LOG_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    status = collect_runtime_status()

    assert status.transaction_log_backend == "json"
    assert status.approval_store_backend == "json"
    assert status.runtime_dir == str(tmp_path)


def test_reports_mixed_backend_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "TRANSACTION_LOG_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    status = collect_runtime_status()

    assert status.transaction_log_backend == "sqlite"
    assert status.approval_store_backend == "json"


def test_reports_mixed_backend_settings_reverse(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "TRANSACTION_LOG_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    status = collect_runtime_status()

    assert status.transaction_log_backend == "json"
    assert status.approval_store_backend == "sqlite"


# ---------------------------------------------------------------------------
# Runtime JSON files
# ---------------------------------------------------------------------------


def test_json_files_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    status = collect_runtime_status()

    assert status.approvals_json.exists is False
    assert status.approvals_json.size_bytes is None
    assert status.rename_transactions_json.exists is False
    assert status.move_transactions_json.exists is False


def test_json_files_exist_report_size(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    content = b'{"hello": "world"}'
    (tmp_path / "approvals.json").write_bytes(content)
    (tmp_path / "rename_transactions.json").write_bytes(content)
    (tmp_path / "move_transactions.json").write_bytes(content)

    status = collect_runtime_status()

    assert status.approvals_json.exists is True
    assert status.approvals_json.size_bytes == len(content)
    assert status.rename_transactions_json.exists is True
    assert status.rename_transactions_json.size_bytes == len(content)
    assert status.move_transactions_json.exists is True
    assert status.move_transactions_json.size_bytes == len(content)


# ---------------------------------------------------------------------------
# SQLite rip.db
# ---------------------------------------------------------------------------


def test_sqlite_db_not_found_reports_exists_false(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    status = collect_runtime_status()

    assert status.sqlite.exists is False
    assert status.sqlite.schema_version is None
    assert status.sqlite.rename_transactions_count is None
    assert status.sqlite.move_transactions_count is None
    assert status.sqlite.approvals_count is None
    assert not (tmp_path / "rip.db").exists()


def test_sqlite_db_not_created_by_status_check(tmp_path, monkeypatch):
    """collect_runtime_status() must never create runtime/rip.db."""
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    collect_runtime_status()
    collect_runtime_status()

    assert not (tmp_path / "rip.db").exists()


def test_sqlite_db_exists_reports_schema_version(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))
    db_path = tmp_path / "rip.db"
    initialize_sqlite_schema(db_path)

    status = collect_runtime_status()

    assert status.sqlite.exists is True
    assert status.sqlite.schema_version == 1


def test_sqlite_db_exists_reports_table_row_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))
    db_path = tmp_path / "rip.db"
    initialize_sqlite_schema(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO rename_transactions(transaction_id, plan_id, created_at) "
        "VALUES ('t1', 'p1', '2026-06-16T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO approvals(approval_id, workflow_id, status, created_at) "
        "VALUES ('a1', 'wf', 'pending', '2026-06-16T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    status = collect_runtime_status()

    assert status.sqlite.rename_transactions_count == 1
    assert status.sqlite.move_transactions_count == 0
    assert status.sqlite.approvals_count == 1


def test_sqlite_db_missing_table_does_not_crash(tmp_path, monkeypatch):
    """A corrupt/partial DB (missing expected tables) must report None, not raise."""
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))
    db_path = tmp_path / "rip.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    status = collect_runtime_status()

    assert status.sqlite.exists is True
    assert status.sqlite.schema_version is None
    assert status.sqlite.rename_transactions_count is None
    assert status.sqlite.move_transactions_count is None
    assert status.sqlite.approvals_count is None


# ---------------------------------------------------------------------------
# Safety guarantees
# ---------------------------------------------------------------------------


def test_does_not_acquire_runtime_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))
    db_path = tmp_path / "rip.db"
    initialize_sqlite_schema(db_path)

    with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
        collect_runtime_status()
        mock_lock.assert_not_called()


def test_does_not_call_initialize_sqlite_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    with patch(
        "app.core.sqlite_transaction_log.initialize_sqlite_schema"
    ) as mock_init:
        collect_runtime_status()
        mock_init.assert_not_called()


def test_does_not_modify_file_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    (tmp_path / "approvals.json").write_text("[]")
    db_path = tmp_path / "rip.db"
    initialize_sqlite_schema(db_path)

    approvals_mtime_before = (tmp_path / "approvals.json").stat().st_mtime
    db_mtime_before = db_path.stat().st_mtime

    collect_runtime_status()

    assert (tmp_path / "approvals.json").stat().st_mtime == approvals_mtime_before
    assert db_path.stat().st_mtime == db_mtime_before
