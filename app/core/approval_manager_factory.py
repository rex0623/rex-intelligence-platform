"""Phase 20B — Approval manager backend factory.

Returns an ApprovalManager instance backed by the store selected by
settings.APPROVAL_STORE_BACKEND.

Supported backends:
  "json"   (default) — JSON flat-file backend; production-safe; approvals.json
                       never creates runtime/rip.db.
  "sqlite" (experimental) — SQLite backend; shares runtime/rip.db with the
                       transaction log SQLite backend. No migration from JSON.

Design notes:
- All imports are local (inside the function) to avoid circular imports and to
  ensure the SQLite module is never imported when backend="json".
- settings.APPROVAL_STORE_BACKEND is read at call time, not at import time,
  so monkeypatch.setattr(settings, "APPROVAL_STORE_BACKEND", ...) works in tests.
- get_sqlite_db_path() is only called when backend="sqlite".
- The module-level approval_manager singleton in app/approvals/manager.py uses
  its own _make_singleton() helper (to avoid circular import); this factory is
  for external callers and tests that need a fresh instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.approvals.manager import ApprovalManager


def make_approval_manager() -> ApprovalManager:
    """Return an ApprovalManager backed by settings.APPROVAL_STORE_BACKEND.

    backend="json" (default):
        Returns ApprovalManager() — JSON-backed, reads/writes approvals.json.
        runtime/rip.db is never created.

    backend="sqlite" (experimental):
        Returns ApprovalManager(_store_backend=SqliteApprovalStore()).
        Creates runtime/rip.db on first write. No migration from JSON backend.
        Existing JSON approval history is not visible.

    Raises ValueError for unknown backend values.
    """
    from app.core.config import settings

    backend = settings.APPROVAL_STORE_BACKEND
    if backend == "json":
        from app.approvals.manager import ApprovalManager
        return ApprovalManager()
    if backend == "sqlite":
        from app.approvals.manager import ApprovalManager
        from app.core.sqlite_approval_store import SqliteApprovalStore
        return ApprovalManager(_store_backend=SqliteApprovalStore())
    raise ValueError(
        f"Unknown APPROVAL_STORE_BACKEND: {backend!r}. "
        "Allowed values: 'json', 'sqlite'."
    )
