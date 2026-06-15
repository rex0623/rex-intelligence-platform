"""Phase 19B — Experimental SQLite transaction log backend.

Provides SQLite-backed implementations of RenameTransactionLogProtocol and
MoveTransactionLogProtocol (Phase 18E).

Design notes:
- Uses Python stdlib sqlite3 only; no SQLAlchemy, no new dependencies.
- Does NOT touch the filesystem at import time. sqlite3.connect() is only
  called inside _open_connection(), which is invoked only from _connection()
  and initialize_sqlite_schema() — never at module level.
- class __init__ requires an explicit db_path; no default runtime path is
  provided. Use tmp_path in tests. Production code continues to use the
  JSON backend (RenameTransactionLog / MoveTransactionLog).
- JSON backend remains the default and only production backend. This module
  is experimental and not connected to any runtime default path.
- prune_transactions() is implemented (Phase 19L). Rename/Move signatures
  diverge (as in the JSON backends), so prune is not part of any Protocol.
- WAL mode note: PRAGMA journal_mode=WAL may not function correctly on
  Windows filesystem paths (e.g. /mnt/c/ in WSL2 DrvFs/NTFS). Use Linux
  filesystem paths (e.g. inside the repo or /tmp) for reliable WAL support.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
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

_SCHEMA_VERSION = 1
_BUSY_TIMEOUT_MS = 5000

_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rename_transactions (
    transaction_id  TEXT NOT NULL PRIMARY KEY,
    plan_id         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rename_transaction_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  TEXT    NOT NULL
                    REFERENCES rename_transactions(transaction_id) ON DELETE CASCADE,
    original_path   TEXT    NOT NULL,
    new_path        TEXT    NOT NULL,
    status          TEXT    NOT NULL
                    CHECK(status IN ('pending','success','failed','rolled_back')),
    rollback_from   TEXT,
    rollback_to     TEXT
);

CREATE TABLE IF NOT EXISTS move_transactions (
    transaction_id  TEXT NOT NULL PRIMARY KEY,
    plan_id         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS move_transaction_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  TEXT    NOT NULL
                    REFERENCES move_transactions(transaction_id) ON DELETE CASCADE,
    original_path   TEXT    NOT NULL,
    new_path        TEXT    NOT NULL,
    status          TEXT    NOT NULL
                    CHECK(status IN ('pending','success','failed','rolled_back')),
    rollback_from   TEXT,
    rollback_to     TEXT
);

CREATE INDEX IF NOT EXISTS idx_rename_actions_tx
    ON rename_transaction_actions(transaction_id);

CREATE INDEX IF NOT EXISTS idx_move_actions_tx
    ON move_transaction_actions(transaction_id);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id   TEXT NOT NULL PRIMARY KEY,
    workflow_id   TEXT NOT NULL,
    status        TEXT NOT NULL
                  CHECK(status IN ('pending','approved','rejected','expired')),
    created_at    TEXT NOT NULL,
    expires_at    TEXT,
    payload       TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_status
    ON approvals(status);
"""


def _open_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode, foreign keys, and busy timeout.

    WAL mode note: PRAGMA journal_mode=WAL may behave unexpectedly on Windows
    filesystem paths (e.g. /mnt/c/ in WSL2 DrvFs/NTFS). Use Linux filesystem
    paths for reliable WAL support.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def _connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Context manager: open connection, commit on success, rollback on error, close."""
    conn = _open_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_sqlite_schema(db_path: Path) -> None:
    """Create all tables and indexes if they do not exist. Idempotent.

    Creates parent directories as needed. Safe to call multiple times on the
    same db_path — all CREATE statements use IF NOT EXISTS.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(db_path) as conn:
        conn.executescript(_DDL)
        existing = conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO schema_version(version) VALUES(?)",
                (_SCHEMA_VERSION,),
            )


class SqliteRenameTransactionLog:
    """Experimental SQLite-backed rename transaction log.

    Satisfies RenameTransactionLogProtocol (Phase 18E) via structural
    subtyping (PEP 544). Not connected to the default runtime path.

    Experimental: not for production use. The JSON backend
    (RenameTransactionLog) remains the default and only production backend.

    prune_transactions() is implemented (Phase 19L); signature mirrors the
    JSON RenameTransactionLog backend.
    All DB file operations require an explicit db_path passed to __init__.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        initialize_sqlite_schema(self._db_path)

    def save_transaction(self, transaction: RenameTransaction) -> None:
        """Upsert the transaction row and replace all its action rows atomically."""
        with _connection(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rename_transactions"
                "(transaction_id, plan_id, created_at) VALUES(?,?,?)",
                (
                    transaction.transaction_id,
                    transaction.plan_id,
                    transaction.created_at.isoformat(),
                ),
            )
            conn.execute(
                "DELETE FROM rename_transaction_actions WHERE transaction_id=?",
                (transaction.transaction_id,),
            )
            for action in transaction.actions:
                conn.execute(
                    "INSERT INTO rename_transaction_actions"
                    "(transaction_id, original_path, new_path, status,"
                    " rollback_from, rollback_to)"
                    " VALUES(?,?,?,?,?,?)",
                    (
                        transaction.transaction_id,
                        action.original_path,
                        action.new_path,
                        action.status,
                        action.rollback_from,
                        action.rollback_to,
                    ),
                )

    def load_transaction(self, transaction_id: str) -> RenameTransaction | None:
        """Return transaction by id, or None if not found."""
        from app.filename.schemas import RenameTransaction, RenameTransactionAction

        with _connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT transaction_id, plan_id, created_at"
                " FROM rename_transactions WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                return None
            action_rows = conn.execute(
                "SELECT original_path, new_path, status, rollback_from, rollback_to"
                " FROM rename_transaction_actions"
                " WHERE transaction_id=? ORDER BY id ASC",
                (transaction_id,),
            ).fetchall()

        return RenameTransaction(
            transaction_id=row["transaction_id"],
            plan_id=row["plan_id"],
            created_at=row["created_at"],
            actions=[
                RenameTransactionAction(
                    original_path=a["original_path"],
                    new_path=a["new_path"],
                    status=a["status"],
                    rollback_from=a["rollback_from"],
                    rollback_to=a["rollback_to"],
                )
                for a in action_rows
            ],
        )

    def list_transactions(self) -> list[RenameTransaction]:
        """Return all stored transactions ordered by created_at ASC."""
        with _connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT transaction_id FROM rename_transactions"
                " ORDER BY created_at ASC, transaction_id ASC"
            ).fetchall()
        result = []
        for row in rows:
            tx = self.load_transaction(row["transaction_id"])
            if tx is not None:
                result.append(tx)
        return result

    def update_transaction(self, transaction: RenameTransaction) -> None:
        """Replace existing transaction by id, or insert if not found."""
        self.save_transaction(transaction)

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> RenameTransaction | None:
        """Update action statuses matched by original_path or new_path.

        action_updates: {path_key: new_status}
          path_key may be the action's original_path OR new_path.
        Returns the updated transaction, or None if transaction_id not found.
        """
        from app.filename.schemas import RenameTransactionAction

        tx = self.load_transaction(transaction_id)
        if tx is None:
            return None

        new_actions = []
        for action in tx.actions:
            new_status = action_updates.get(action.original_path)
            if new_status is None:
                new_status = action_updates.get(action.new_path)
            if new_status is not None:
                new_actions.append(RenameTransactionAction(
                    original_path=action.original_path,
                    new_path=action.new_path,
                    status=new_status,
                    rollback_from=action.rollback_from,
                    rollback_to=action.rollback_to,
                ))
            else:
                new_actions.append(action)

        tx.actions = new_actions
        self.save_transaction(tx)
        return tx

    def prune_transactions(
        self,
        max_transactions: int | None = None,
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> TransactionLogPruneResult:
        """Prune old rename transactions from SQLite (Phase 19L).

        Mirrors RenameTransactionLog.prune_transactions() (Phase 14F):
          - max_age_days: prune transactions older than N days.
          - max_transactions: keep at most N most-recent; prune the rest.
          - No criteria → no-op (returns counts, no DELETE executed).
          - Transactions with any action status='success' are never pruned
            (counted in kept_rollbackable_count).
          - ON DELETE CASCADE removes child actions automatically.
          - corrupted_count: not applicable; SQLite schema enforces validity.
          - No runtime lock needed: SQLite WAL + busy_timeout handle concurrency.
        """
        from app.filename.schemas import TransactionLogPruneResult

        if now is None:
            now = datetime.now(timezone.utc)

        def _aware(dt: datetime) -> datetime:
            if dt.tzinfo is not None:
                return dt
            return datetime(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second, dt.microsecond,
                tzinfo=timezone.utc,
            )

        with _connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT transaction_id, created_at FROM rename_transactions"
                " ORDER BY created_at ASC, transaction_id ASC"
            ).fetchall()
            total_before = len(rows)

            if not rows or (max_transactions is None and max_age_days is None):
                return TransactionLogPruneResult(
                    total_before=total_before,
                    total_after=total_before,
                )

            rollbackable_ids = {
                row["transaction_id"]
                for row in conn.execute(
                    "SELECT DISTINCT transaction_id FROM rename_transaction_actions"
                    " WHERE status='success'"
                ).fetchall()
            }

            candidate_ids: set[str] = set()

            if max_age_days is not None:
                cutoff = now - timedelta(days=max_age_days)
                for row in rows:
                    if _aware(datetime.fromisoformat(row["created_at"])) < cutoff:
                        candidate_ids.add(row["transaction_id"])

            if max_transactions is not None and total_before > max_transactions:
                excess = total_before - max_transactions
                for row in rows[:excess]:
                    candidate_ids.add(row["transaction_id"])

            prune_ids: list[str] = []
            kept_rollbackable = 0
            for row in rows:
                tx_id = row["transaction_id"]
                if tx_id not in candidate_ids:
                    continue
                if tx_id in rollbackable_ids:
                    kept_rollbackable += 1
                else:
                    prune_ids.append(tx_id)

            if prune_ids:
                conn.execute(
                    "DELETE FROM rename_transactions WHERE transaction_id IN"
                    f" ({','.join('?' * len(prune_ids))})",
                    prune_ids,
                )

        return TransactionLogPruneResult(
            total_before=total_before,
            total_after=total_before - len(prune_ids),
            pruned_count=len(prune_ids),
            kept_rollbackable_count=kept_rollbackable,
            pruned_transaction_ids=prune_ids,
        )


class SqliteMoveTransactionLog:
    """Experimental SQLite-backed move transaction log.

    Satisfies MoveTransactionLogProtocol (Phase 18E) via structural
    subtyping (PEP 544). Not connected to the default runtime path.

    Experimental: not for production use. The JSON backend
    (MoveTransactionLog) remains the default and only production backend.

    prune_transactions() is implemented (Phase 19L); signature mirrors the
    JSON MoveTransactionLog backend.
    All DB file operations require an explicit db_path passed to __init__.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        initialize_sqlite_schema(self._db_path)

    def save_transaction(self, transaction: MoveTransaction) -> None:
        """Upsert the transaction row and replace all its action rows atomically."""
        with _connection(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO move_transactions"
                "(transaction_id, plan_id, created_at) VALUES(?,?,?)",
                (
                    transaction.transaction_id,
                    transaction.plan_id,
                    transaction.created_at.isoformat(),
                ),
            )
            conn.execute(
                "DELETE FROM move_transaction_actions WHERE transaction_id=?",
                (transaction.transaction_id,),
            )
            for action in transaction.actions:
                conn.execute(
                    "INSERT INTO move_transaction_actions"
                    "(transaction_id, original_path, new_path, status,"
                    " rollback_from, rollback_to)"
                    " VALUES(?,?,?,?,?,?)",
                    (
                        transaction.transaction_id,
                        action.original_path,
                        action.new_path,
                        action.status,
                        action.rollback_from,
                        action.rollback_to,
                    ),
                )

    def load_transaction(self, transaction_id: str) -> MoveTransaction | None:
        """Return transaction by id, or None if not found."""
        from app.folder_intelligence.schemas import MoveTransaction, MoveTransactionAction

        with _connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT transaction_id, plan_id, created_at"
                " FROM move_transactions WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                return None
            action_rows = conn.execute(
                "SELECT original_path, new_path, status, rollback_from, rollback_to"
                " FROM move_transaction_actions"
                " WHERE transaction_id=? ORDER BY id ASC",
                (transaction_id,),
            ).fetchall()

        return MoveTransaction(
            transaction_id=row["transaction_id"],
            plan_id=row["plan_id"],
            created_at=row["created_at"],
            actions=[
                MoveTransactionAction(
                    original_path=a["original_path"],
                    new_path=a["new_path"],
                    status=a["status"],
                    rollback_from=a["rollback_from"],
                    rollback_to=a["rollback_to"],
                )
                for a in action_rows
            ],
        )

    def list_transactions(self) -> list[MoveTransaction]:
        """Return all stored transactions ordered by created_at ASC."""
        with _connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT transaction_id FROM move_transactions"
                " ORDER BY created_at ASC, transaction_id ASC"
            ).fetchall()
        result = []
        for row in rows:
            tx = self.load_transaction(row["transaction_id"])
            if tx is not None:
                result.append(tx)
        return result

    def update_transaction(self, transaction: MoveTransaction) -> None:
        """Replace existing transaction by id, or insert if not found."""
        self.save_transaction(transaction)

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> MoveTransaction | None:
        """Update action statuses matched by original_path or new_path.

        action_updates: {path_key: new_status}
          path_key may be the action's original_path OR new_path.
        Returns the updated transaction, or None if transaction_id not found.
        """
        from app.folder_intelligence.schemas import MoveTransactionAction

        tx = self.load_transaction(transaction_id)
        if tx is None:
            return None

        new_actions = []
        for action in tx.actions:
            new_status = action_updates.get(action.original_path)
            if new_status is None:
                new_status = action_updates.get(action.new_path)
            if new_status is not None:
                new_actions.append(MoveTransactionAction(
                    original_path=action.original_path,
                    new_path=action.new_path,
                    status=new_status,
                    rollback_from=action.rollback_from,
                    rollback_to=action.rollback_to,
                ))
            else:
                new_actions.append(action)

        tx.actions = new_actions
        self.save_transaction(tx)
        return tx

    def prune_transactions(
        self,
        older_than_days: int = 30,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> MoveTransactionLogPruneResult:
        """Prune old move transactions from SQLite (Phase 19L).

        Mirrors MoveTransactionLog.prune_transactions() (Phase 15J):
          - older_than_days: age threshold (default 30 days).
          - dry_run=True: compute and return result without deleting.
          - protected: any action status='success' → never pruned, even if old.
          - retained: no success action, not yet expired → kept, listed.
          - pruned: no success action, expired → deleted (unless dry_run).
          - corrupted_count / corrupted_entries: always 0; SQLite schema
            enforces row validity, eliminating the JSON corrupted-entry concept.
          - ON DELETE CASCADE removes child actions automatically.
          - No runtime lock needed: SQLite WAL + busy_timeout handle concurrency.
        """
        from app.folder_intelligence.schemas import MoveTransactionLogPruneResult

        if now is None:
            now = datetime.now(timezone.utc)

        def _aware(dt: datetime) -> datetime:
            if dt.tzinfo is not None:
                return dt
            return datetime(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second, dt.microsecond,
                tzinfo=timezone.utc,
            )

        cutoff = now - timedelta(days=older_than_days)

        with _connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT transaction_id, created_at FROM move_transactions"
                " ORDER BY created_at ASC, transaction_id ASC"
            ).fetchall()
            before_count = len(rows)

            protected_set = {
                row["transaction_id"]
                for row in conn.execute(
                    "SELECT DISTINCT transaction_id FROM move_transaction_actions"
                    " WHERE status='success'"
                ).fetchall()
            }

            prune_ids: list[str] = []
            retained_ids: list[str] = []
            protected_ids: list[str] = []

            for row in rows:
                tx_id = row["transaction_id"]
                if tx_id in protected_set:
                    protected_ids.append(tx_id)
                    continue
                if _aware(datetime.fromisoformat(row["created_at"])) < cutoff:
                    prune_ids.append(tx_id)
                else:
                    retained_ids.append(tx_id)

            if prune_ids and not dry_run:
                conn.execute(
                    "DELETE FROM move_transactions WHERE transaction_id IN"
                    f" ({','.join('?' * len(prune_ids))})",
                    prune_ids,
                )

        return MoveTransactionLogPruneResult(
            before_count=before_count,
            after_count=before_count - len(prune_ids),
            pruned_count=len(prune_ids),
            retained_count=len(retained_ids),
            protected_count=len(protected_ids),
            corrupted_count=0,
            corrupted_entries=0,
            dry_run=dry_run,
            pruned_transaction_ids=prune_ids,
            retained_transaction_ids=retained_ids,
            protected_transaction_ids=protected_ids,
        )
