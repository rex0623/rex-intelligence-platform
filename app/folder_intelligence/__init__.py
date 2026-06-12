"""Folder Intelligence — move plan generation and safe execution.

Planning (Phase 15A–15C) never touches the real filesystem; MovePlan is
dry-run and requires approval.  Phase 15D adds execute_move_plan(), the
ONLY entry point that actually moves files — it is a low-level API that
must be called explicitly with an approved, validated MovePlan, and is
NOT wired to Mock LINE or any fuzzy command.
"""

from app.folder_intelligence.approval_bridge import (
    default_move_transaction_log,
    execute_approved_move_by_approval_id,
    execute_approved_move_plan,
)
from app.folder_intelligence.executor import (
    build_move_transaction,
    execute_move_plan,
    rollback_move_transaction,
    rollback_move_transaction_by_id,
)
from app.folder_intelligence.formatter import format_move_plan_for_cli
from app.folder_intelligence.planner import build_move_plan
from app.folder_intelligence.preflight import preflight_move_plan
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
    MoveRollbackPreview,
    MoveRollbackPreviewAction,
    MoveTransaction,
    MoveTransactionAction,
    MoveTransactionLogPruneResult,
    MoveValidationReport,
)
from app.folder_intelligence.transaction_log import (
    MoveTransactionLog,
    preview_move_rollback_transaction,
    preview_move_rollback_transaction_by_id,
    prune_move_transactions,
)
from app.folder_intelligence.validator import validate_move_plan

__all__ = [
    "MoveCandidate",
    "MoveCandidateValidation",
    "MoveExecutionResult",
    "MoveFileResult",
    "MovePlan",
    "MoveRollbackPreview",
    "MoveRollbackPreviewAction",
    "MoveTransaction",
    "MoveTransactionAction",
    "MoveTransactionLog",
    "MoveTransactionLogPruneResult",
    "MoveValidationReport",
    "build_move_plan",
    "build_move_transaction",
    "default_move_transaction_log",
    "execute_approved_move_by_approval_id",
    "execute_approved_move_plan",
    "execute_move_plan",
    "rollback_move_transaction",
    "rollback_move_transaction_by_id",
    "validate_move_plan",
    "format_move_plan_for_cli",
    "preflight_move_plan",
    "preview_move_rollback_transaction",
    "preview_move_rollback_transaction_by_id",
    "prune_move_transactions",
]
