"""Phase 14D-1 — Approval-to-Execution Bridge.

Provides:
  execute_approved_rename_plan(plan, transaction_log=None)
      — application-layer entry point that accepts an approved, validated
        RenamePlan and executes it through the Safe Rename Executor.
  execute_approved_rename_by_plan_id(plan_id, plan_loader, transaction_log=None)
      — lookup adapter: loads a plan via an injected loader, then delegates
        to execute_approved_rename_plan().

Safety rules:
  - The bridge requires plan.status == "approved".
  - The bridge requires plan.validation_report to be present.
  - The bridge requires validation_report.blocked_count == 0.
  - All execution goes through execute_rename_plan(); this module never
    touches the filesystem itself (no Path/os/shutil rename calls).
  - This module is NOT wired to any Mock LINE command; it is the foundation
    for a future explicit confirm command (Phase 14D-2).
"""

from typing import Callable, Optional

from app.filename.executor import execute_rename_plan
from app.filename.schemas import (
    RenamePlan,
    RenameExecutionResult,
    RenameFileResult,
)
from app.core.transaction_log_protocol import RenameTransactionLogProtocol


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _reject(plan: RenamePlan, reason: str) -> RenameExecutionResult:
    """Build a non-executed rejection result with *reason* on every candidate.

    Unlike preflight (dry_run=True), the bridge reports dry_run=False because
    the caller requested a real execution that was refused.
    """
    results = [
        RenameFileResult(
            original_path=candidate.original_filename or "",
            proposed_path=candidate.proposed_filename or "",
            status="blocked",
            reason=reason,
            risk_level="blocked",
        )
        for candidate in plan.candidates
    ]
    return RenameExecutionResult(
        plan_id=plan.plan_id,
        executed=False,
        dry_run=False,
        total=len(plan.candidates),
        success_count=0,
        failed_count=0,
        skipped_count=0,
        blocked_count=len(results),
        results=results,
        rollback_available=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_approved_rename_plan(
    plan: RenamePlan,
    transaction_log: Optional[RenameTransactionLogProtocol] = None,
) -> RenameExecutionResult:
    """Execute an approved, validated RenamePlan via the Safe Rename Executor.

    Gate order (each failure returns executed=False, dry_run=False without
    calling execute_rename_plan):

      1. plan.status != "approved"                → "plan_not_approved"
      2. plan.validation_report is None           → "missing_validation_report"
      3. validation_report.blocked_count > 0      → "validation_has_blocked_candidates"

    On success, delegates to execute_rename_plan(plan, transaction_log=...),
    which re-runs preflight and enforces all per-candidate safety rules
    (blocked never renamed, high risk skipped, collision/missing-file checks).
    """
    if plan.status != "approved":
        return _reject(plan, "plan_not_approved")

    if plan.validation_report is None:
        return _reject(plan, "missing_validation_report")

    if plan.validation_report.blocked_count > 0:
        return _reject(plan, "validation_has_blocked_candidates")

    return execute_rename_plan(plan, transaction_log=transaction_log)


def execute_approved_rename_by_plan_id(
    plan_id: str,
    plan_loader: Callable[[str], Optional[RenamePlan]],
    transaction_log: Optional[RenameTransactionLogProtocol] = None,
) -> RenameExecutionResult:
    """Load a RenamePlan by id via *plan_loader*, then execute it through
    execute_approved_rename_plan().

    The loader is injected so this module stays decoupled from any plan
    storage (there is no RenamePlan persistence yet).  If the loader returns
    None, no execution is attempted and the result carries reason
    "plan_not_found" (same pattern as rollback_transaction_by_id).
    """
    plan = plan_loader(plan_id)

    if plan is None:
        return RenameExecutionResult(
            plan_id=plan_id,
            executed=False,
            dry_run=False,
            total=0,
            success_count=0,
            failed_count=1,
            skipped_count=0,
            blocked_count=0,
            results=[
                RenameFileResult(
                    original_path="",
                    proposed_path="",
                    status="failed",
                    reason="plan_not_found",
                )
            ],
            rollback_available=False,
        )

    return execute_approved_rename_plan(plan, transaction_log=transaction_log)
