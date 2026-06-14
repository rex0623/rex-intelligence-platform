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
- prune_transactions() is not implemented (not in Protocol; Rename/Move
  signatures diverge). Raises NotImplementedError if called directly.
- WAL mode note: PRAGMA journal_mode=WAL may not function correctly on
  Windows filesystem paths (e.g. /mnt/c/ in WSL2 DrvFs/NTFS). Use Linux
  filesystem paths (e.g. inside the repo or /tmp) for reliable WAL support.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from app.filename.schemas import RenameTransaction, RenameTransactionAction
    from app.folder_intelligence.schemas import MoveTransaction, MoveTransactionAction

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

    prune_transactions() is not implemented and raises NotImplementedError.
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

    def prune_transactions(self, *args, **kwargs) -> None:  # type: ignore[return]
        raise NotImplementedError(
            "prune_transactions not implemented for SQLite backend"
        )


class SqliteMoveTransactionLog:
    """Experimental SQLite-backed move transaction log.

    Satisfies MoveTransactionLogProtocol (Phase 18E) via structural
    subtyping (PEP 544). Not connected to the default runtime path.

    Experimental: not for production use. The JSON backend
    (MoveTransactionLog) remains the default and only production backend.

    prune_transactions() is not implemented and raises NotImplementedError.
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

    def prune_transactions(self, *args, **kwargs) -> None:  # type: ignore[return]
        raise NotImplementedError(
            "prune_transactions not implemented for SQLite backend"
        )
