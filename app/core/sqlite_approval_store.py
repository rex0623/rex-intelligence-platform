"""Phase 20A — SQLite-backed approval store.

Provides SqliteApprovalStore: an approval store backend that persists approvals
in the shared runtime/rip.db SQLite database (approvals table, added in Phase 20A).

Design notes:
- Uses the same rip.db as SqliteRenameTransactionLog / SqliteMoveTransactionLog.
  All tables coexist; initialize_sqlite_schema() creates them idempotently.
- load() and save() accept a store_path argument (for API compatibility with
  JsonApprovalStore and ApprovalStoreProtocol) but derive the actual DB path
  from get_sqlite_db_path() — the store_path argument is ignored.
- payload is stored as a JSON TEXT blob. execution_status / executed_at /
  execution_transaction_id remain embedded in payload (no separate columns),
  preserving backward compatibility with ApprovalManager.mark_executed().
- save() uses a replace-all strategy: DELETE all rows then INSERT the full
  data dict in one transaction. This is correct because ApprovalManager always
  holds the complete in-memory _store dict and calls save() with the full state.
- No in-memory cache: each load() reads from DB, each save() writes to DB.
- WAL + busy_timeout=5000ms (set by initialize_sqlite_schema via _open_connection).
- Does NOT touch the filesystem at import time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.sqlite_transaction_log import _connection, initialize_sqlite_schema

if TYPE_CHECKING:
    from app.approvals.schemas import Approval


def _get_db_path() -> Path:
    from app.core.config import get_sqlite_db_path
    return get_sqlite_db_path()


class SqliteApprovalStore:
    """SQLite-backed approval store satisfying ApprovalStoreProtocol (Phase 20A).

    Persists approvals in the 'approvals' table of runtime/rip.db.
    store_path argument is accepted for API compatibility but ignored;
    the actual DB path is always get_sqlite_db_path().
    """

    def load(self, store_path: Path) -> dict[str, Approval]:
        """Read all approvals from DB → Dict[approval_id, Approval].

        Returns {} when the approvals table is empty.
        store_path is ignored; DB path is derived from get_sqlite_db_path().
        """
        from app.approvals.schemas import Approval

        db_path = _get_db_path()
        initialize_sqlite_schema(db_path)

        with _connection(db_path) as conn:
            rows = conn.execute(
                "SELECT approval_id, workflow_id, status, created_at,"
                " expires_at, payload FROM approvals"
            ).fetchall()

        result: dict[str, Approval] = {}
        for row in rows:
            raw_payload = row["payload"]
            payload = json.loads(raw_payload) if raw_payload is not None else None
            approval = Approval(
                approval_id=row["approval_id"],
                workflow_id=row["workflow_id"],
                status=row["status"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                payload=payload,
            )
            result[approval.approval_id] = approval
        return result

    def save(self, store_path: Path, data: dict[str, Approval]) -> None:
        """Write Dict[approval_id, Approval] → approvals table (replace-all).

        Deletes all existing rows then inserts the full data dict in one
        transaction. store_path is ignored; DB path is get_sqlite_db_path().
        """
        db_path = _get_db_path()
        initialize_sqlite_schema(db_path)

        rows = []
        for approval in data.values():
            payload_json = (
                json.dumps(approval.payload, ensure_ascii=False)
                if approval.payload is not None
                else None
            )
            expires_at_str = (
                approval.expires_at.isoformat() if approval.expires_at is not None else None
            )
            created_at_str = approval.created_at.isoformat()
            rows.append((
                approval.approval_id,
                approval.workflow_id,
                approval.status,
                created_at_str,
                expires_at_str,
                payload_json,
            ))

        with _connection(db_path) as conn:
            conn.execute("DELETE FROM approvals")
            conn.executemany(
                "INSERT INTO approvals"
                " (approval_id, workflow_id, status, created_at, expires_at, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
