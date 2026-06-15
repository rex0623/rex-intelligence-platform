"""Phase 20A — Approval store Protocol definition.

Provides a @runtime_checkable structural Protocol for approval store backends.
Any object that implements load() and save() with compatible signatures satisfies
this Protocol (PEP 544 structural subtyping).

Design notes:
- Instance method design (not staticmethod) so that JsonApprovalStore() and
  SqliteApprovalStore() can both be injected as ApprovalStoreProtocol.
- store_path is retained as a parameter on both methods to remain compatible
  with ApprovalManager's existing call sites (JsonApprovalStore.load/save).
  SQLite backend accepts the argument but derives the actual DB path from
  get_sqlite_db_path() instead.
- JSON backend remains the default; this Protocol enables future DI without
  changing ApprovalManager callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.approvals.schemas import Approval


@runtime_checkable
class ApprovalStoreProtocol(Protocol):
    """Structural Protocol for approval store backends.

    Any object that implements load() and save() with compatible signatures
    satisfies this Protocol (PEP 544 structural subtyping).
    """

    def load(self, store_path: Path) -> dict[str, Approval]: ...

    def save(self, store_path: Path, data: dict[str, Approval]) -> None: ...
