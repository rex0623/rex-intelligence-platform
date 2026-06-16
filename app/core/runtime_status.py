"""Phase 22B — Runtime Status / Diagnostics (read-only).

Reports current backend settings, runtime JSON file existence/size, and
SQLite rip.db schema_version / table row counts.

Safety guarantees
------------------
- Never writes any file.
- Never creates runtime/rip.db (opens with sqlite3 mode=ro; if the file does
  not exist, reports exists=False instead of creating it).
- Never calls initialize_sqlite_schema().
- Never calls acquire_runtime_lock().
- Missing tables / corrupt schema are reported as None, not raised.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import (
    get_approval_store_path,
    get_move_transaction_log_path,
    get_rename_transaction_log_path,
    get_runtime_dir,
    get_sqlite_db_path,
    settings,
)

_SQLITE_TABLES = ("rename_transactions", "move_transactions", "approvals")


@dataclass
class RuntimeFileStatus:
    """Existence / size of a single runtime JSON file (no content parsing)."""

    path: str
    exists: bool
    size_bytes: Optional[int] = None


@dataclass
class SqliteStatus:
    """SQLite rip.db status (None fields mean "not available / not readable")."""

    exists: bool
    db_path: str
    schema_version: Optional[int] = None
    rename_transactions_count: Optional[int] = None
    move_transactions_count: Optional[int] = None
    approvals_count: Optional[int] = None


@dataclass
class RuntimeStatus:
    """Aggregate read-only snapshot of RIP runtime state."""

    transaction_log_backend: str
    approval_store_backend: str
    runtime_dir: str
    approvals_json: RuntimeFileStatus
    rename_transactions_json: RuntimeFileStatus
    move_transactions_json: RuntimeFileStatus
    sqlite: SqliteStatus


def _file_status(path: Path) -> RuntimeFileStatus:
    if path.exists():
        return RuntimeFileStatus(
            path=str(path), exists=True, size_bytes=path.stat().st_size
        )
    return RuntimeFileStatus(path=str(path), exists=False, size_bytes=None)


def _scalar(conn: sqlite3.Connection, query: str) -> Optional[int]:
    try:
        row = conn.execute(query).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return row[0]


def _table_count(conn: sqlite3.Connection, table: str) -> Optional[int]:
    if table not in _SQLITE_TABLES:
        raise ValueError(f"unexpected table name: {table}")
    return _scalar(conn, f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — fixed internal enum, not user input


def _sqlite_status(db_path: Path) -> SqliteStatus:
    if not db_path.exists():
        return SqliteStatus(exists=False, db_path=str(db_path))

    status = SqliteStatus(exists=True, db_path=str(db_path))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return status
    try:
        status.schema_version = _scalar(conn, "SELECT version FROM schema_version")
        status.rename_transactions_count = _table_count(conn, "rename_transactions")
        status.move_transactions_count = _table_count(conn, "move_transactions")
        status.approvals_count = _table_count(conn, "approvals")
    finally:
        conn.close()
    return status


def collect_runtime_status() -> RuntimeStatus:
    """Collect a read-only snapshot of the current RIP runtime state.

    Never writes, never creates runtime/rip.db, never acquires the runtime
    lock, never calls initialize_sqlite_schema().
    """
    return RuntimeStatus(
        transaction_log_backend=settings.TRANSACTION_LOG_BACKEND,
        approval_store_backend=settings.APPROVAL_STORE_BACKEND,
        runtime_dir=str(get_runtime_dir()),
        approvals_json=_file_status(get_approval_store_path()),
        rename_transactions_json=_file_status(get_rename_transaction_log_path()),
        move_transactions_json=_file_status(get_move_transaction_log_path()),
        sqlite=_sqlite_status(get_sqlite_db_path()),
    )
