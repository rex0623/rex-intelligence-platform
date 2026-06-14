"""Phase 18E — Transaction log Protocol definitions.

Provides @runtime_checkable structural Protocols for rename and move
transaction log backends.  Executors and approval bridges type-annotate
their transaction_log parameters with these Protocols so that any
structurally-compatible backend (e.g. a future SQLite backend) can be
injected without changing the callers.

Design notes:
  - prune_transactions() is excluded: RenameTransactionLog and
    MoveTransactionLog diverge in parameter names (max_transactions /
    max_age_days vs older_than_days / dry_run) and return types
    (TransactionLogPruneResult vs MoveTransactionLogPruneResult).
    No unified Protocol method is defined for prune.
  - No Generic base class: two separate, concrete-typed Protocols are
    cleaner than Generic[T] with TypeVar.
  - No SQLite backend: out of scope for Phase 18E.
  - JSON backend remains the default and only backend; runtime behaviour
    is unchanged from Phase 18C.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.filename.schemas import RenameTransaction
    from app.folder_intelligence.schemas import MoveTransaction


@runtime_checkable
class RenameTransactionLogProtocol(Protocol):
    """Structural Protocol for rename transaction log backends.

    Any object that implements these five methods with compatible signatures
    satisfies this Protocol (PEP 544 structural subtyping).

    Excluded: prune_transactions() — signature diverges from MoveTransactionLog.
    """

    def save_transaction(self, transaction: RenameTransaction) -> None: ...

    def load_transaction(self, transaction_id: str) -> RenameTransaction | None: ...

    def list_transactions(self) -> list[RenameTransaction]: ...

    def update_transaction(self, transaction: RenameTransaction) -> None: ...

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> RenameTransaction | None: ...


@runtime_checkable
class MoveTransactionLogProtocol(Protocol):
    """Structural Protocol for move transaction log backends.

    Any object that implements these five methods with compatible signatures
    satisfies this Protocol (PEP 544 structural subtyping).

    Excluded: prune_transactions() — signature diverges from RenameTransactionLog.
    """

    def save_transaction(self, transaction: MoveTransaction) -> None: ...

    def load_transaction(self, transaction_id: str) -> MoveTransaction | None: ...

    def list_transactions(self) -> list[MoveTransaction]: ...

    def update_transaction(self, transaction: MoveTransaction) -> None: ...

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> MoveTransaction | None: ...
