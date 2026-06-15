"""Phase 19D — Transaction log backend factory.

Returns a RenameTransactionLogProtocol or MoveTransactionLogProtocol
instance selected by settings.TRANSACTION_LOG_BACKEND.

Supported backends:
  "json"   (default) — JSON flat-file backend; production-safe; all existing
                       behaviour preserved; runtime/rip.db never created.
  "sqlite" (experimental) — SQLite backend; prune_transactions() implemented
                       (Phase 19L); creates runtime/rip.db on first use.

Design notes:
- All imports are local (inside functions) to avoid circular imports and to
  ensure the SQLite module is never imported when backend="json".
- settings.TRANSACTION_LOG_BACKEND is read at call time, not at import time,
  so monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", ...) works in tests.
- get_sqlite_db_path() is only called when backend="sqlite".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.transaction_log_protocol import (
        MoveTransactionLogProtocol,
        RenameTransactionLogProtocol,
    )


def make_rename_transaction_log() -> RenameTransactionLogProtocol:
    """Return a rename transaction log backend selected by TRANSACTION_LOG_BACKEND.

    backend="json" (default):
        Returns RenameTransactionLog(get_rename_transaction_log_path()).
        runtime/rip.db is never created.

    backend="sqlite" (experimental):
        Returns SqliteRenameTransactionLog(get_sqlite_db_path()).
        Creates runtime/rip.db on first call.
        prune_transactions() implemented (Phase 19L).
        No migration from JSON backend. Existing JSON history is not visible.

    Raises ValueError for unknown backend values.
    """
    from app.core.config import settings

    backend = settings.TRANSACTION_LOG_BACKEND
    if backend == "json":
        from app.core.config import get_rename_transaction_log_path
        from app.filename.transaction_log import RenameTransactionLog
        return RenameTransactionLog(get_rename_transaction_log_path())
    if backend == "sqlite":
        from app.core.config import get_sqlite_db_path
        from app.core.sqlite_transaction_log import SqliteRenameTransactionLog
        return SqliteRenameTransactionLog(get_sqlite_db_path())
    raise ValueError(
        f"Unknown TRANSACTION_LOG_BACKEND: {backend!r}. "
        "Allowed values: 'json', 'sqlite'."
    )


def make_move_transaction_log() -> MoveTransactionLogProtocol:
    """Return a move transaction log backend selected by TRANSACTION_LOG_BACKEND.

    backend="json" (default):
        Returns MoveTransactionLog(get_move_transaction_log_path()).
        runtime/rip.db is never created.

    backend="sqlite" (experimental):
        Returns SqliteMoveTransactionLog(get_sqlite_db_path()).
        Creates runtime/rip.db on first call.
        prune_transactions() implemented (Phase 19L).
        No migration from JSON backend. Existing JSON history is not visible.

    Raises ValueError for unknown backend values.
    """
    from app.core.config import settings

    backend = settings.TRANSACTION_LOG_BACKEND
    if backend == "json":
        from app.core.config import get_move_transaction_log_path
        from app.folder_intelligence.transaction_log import MoveTransactionLog
        return MoveTransactionLog(get_move_transaction_log_path())
    if backend == "sqlite":
        from app.core.config import get_sqlite_db_path
        from app.core.sqlite_transaction_log import SqliteMoveTransactionLog
        return SqliteMoveTransactionLog(get_sqlite_db_path())
    raise ValueError(
        f"Unknown TRANSACTION_LOG_BACKEND: {backend!r}. "
        "Allowed values: 'json', 'sqlite'."
    )
