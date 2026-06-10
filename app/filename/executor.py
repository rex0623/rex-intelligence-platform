"""Phase 14B — Safe rename executor.

Provides:
  execute_rename_plan(plan)          — actually renames files, only after preflight passes.
  build_rename_transaction(plan)     — builds an in-memory transaction for low/medium candidates.
  rollback_rename_transaction(tx)    — reverses successful actions in a transaction.

Safety rules:
  - execute_rename_plan requires plan.status == "approved".
  - execute_rename_plan requires plan.validation_report to be present.
  - execute_rename_plan requires validation_report.blocked_count == 0.
  - Blocked candidates are never renamed.
  - High-risk candidates are skipped by default.
  - Filesystem collision (target exists) prevents rename.
  - Missing source file prevents rename.
  - Every successful rename records rollback_from / rollback_to.
  - This is the ONLY module that may call Path.rename().
"""

from pathlib import Path

from app.filename.preflight import preflight_rename_plan
from app.filename.schemas import (
    RenamePlan,
    RenameExecutionResult,
    RenameFileResult,
    RenameTransaction,
    RenameTransactionAction,
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _risk_for(plan: RenamePlan, original_filename: str) -> str | None:
    """Look up the risk_level for *original_filename* in the validation report."""
    if plan.validation_report is None:
        return None
    for cv in plan.validation_report.candidates:
        if cv.original_filename == original_filename:
            return cv.risk_level
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_rename_plan(plan: RenamePlan) -> RenameExecutionResult:
    """Execute an approved, validated RenamePlan by actually renaming files.

    Calls preflight_rename_plan() first.  Returns early (executed=False) if
    any plan-level gate fails.  For each candidate the order of checks is:

      1. missing paths         → failed
      2. blocked risk          → blocked
      3. same filename         → skipped
      4. high risk             → skipped
      5. original not found    → failed
      6. target already exists → failed
      7. Path.rename()         → success / failed
    """
    # ── Plan-level gate (mirrors preflight) ─────────────────────────────────
    preflight = preflight_rename_plan(plan)
    if plan.status != "approved":
        return preflight  # executed=False already set by preflight
    if plan.validation_report is None:
        return preflight
    if plan.validation_report.blocked_count > 0:
        return preflight

    # ── Per-candidate execution ──────────────────────────────────────────────
    results: list[RenameFileResult] = []
    success_count = failed_count = skipped_count = blocked_count = 0
    any_attempted = False  # True once we hit a filesystem check

    for candidate in plan.candidates:
        original = candidate.original_filename or ""
        proposed = candidate.proposed_filename or ""
        risk = _risk_for(plan, original)

        # 1. Missing original path
        if not original:
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="failed",
                reason="missing_original_path",
                risk_level=risk,
            ))
            failed_count += 1
            continue

        # 2. Missing proposed path
        if not proposed:
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="failed",
                reason="missing_proposed_path",
                risk_level=risk,
            ))
            failed_count += 1
            continue

        # 3. Blocked by validation report
        if risk == "blocked":
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="blocked",
                reason="blocked_by_validation",
                risk_level=risk,
            ))
            blocked_count += 1
            continue

        # 4. Same filename
        if proposed == original:
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="skipped",
                reason="same_filename",
                risk_level=risk,
            ))
            skipped_count += 1
            continue

        # 5. High risk — skip without touching filesystem
        if risk == "high":
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="skipped",
                reason="high_risk_requires_manual_review",
                risk_level=risk,
            ))
            skipped_count += 1
            continue

        # ── From here onward we check the real filesystem ──────────────────
        any_attempted = True
        original_path = Path(original)
        proposed_path = Path(proposed)

        # 6. Original file must exist
        if not original_path.exists():
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="failed",
                reason="original_file_not_found",
                risk_level=risk,
            ))
            failed_count += 1
            continue

        # 7. Target must not already exist
        if proposed_path.exists():
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="failed",
                reason="target_file_already_exists",
                risk_level=risk,
            ))
            failed_count += 1
            continue

        # 8. Perform rename
        try:
            original_path.rename(proposed_path)
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="success",
                reason=None,
                risk_level=risk,
                rollback_from=proposed,   # new location → where to roll back FROM
                rollback_to=original,     # original location → where to roll back TO
            ))
            success_count += 1
        except OSError as exc:
            results.append(RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="failed",
                reason=f"rename_error: {exc}",
                risk_level=risk,
            ))
            failed_count += 1

    return RenameExecutionResult(
        plan_id=plan.plan_id,
        executed=any_attempted,
        dry_run=False,
        total=len(plan.candidates),
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        blocked_count=blocked_count,
        results=results,
        rollback_available=(success_count > 0),
    )


def build_rename_transaction(plan: RenamePlan) -> RenameTransaction:
    """Build an in-memory RenameTransaction for low/medium-risk candidates.

    High-risk and blocked candidates are excluded.
    Does not execute or touch the filesystem.
    """
    actions: list[RenameTransactionAction] = []

    for candidate in plan.candidates:
        original = candidate.original_filename or ""
        proposed = candidate.proposed_filename or ""

        if not original or not proposed or original == proposed:
            continue

        risk = _risk_for(plan, original)
        if risk not in ("low", "medium"):
            continue

        actions.append(RenameTransactionAction(
            original_path=original,
            new_path=proposed,
            status="pending",
            rollback_from=proposed,
            rollback_to=original,
        ))

    return RenameTransaction(
        plan_id=plan.plan_id,
        actions=actions,
    )


def rollback_rename_transaction(transaction: RenameTransaction) -> RenameExecutionResult:
    """Reverse all actions whose status is "success".

    Only reverses confirmed successes.  Never touches pending/failed actions.
    """
    results: list[RenameFileResult] = []
    success_count = failed_count = 0
    any_attempted = False

    for action in transaction.actions:
        if action.status != "success":
            continue

        any_attempted = True
        rollback_from = action.rollback_from or ""
        rollback_to = action.rollback_to or ""
        from_path = Path(rollback_from)
        to_path = Path(rollback_to)

        if not from_path.exists():
            results.append(RenameFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason="rollback_source_not_found",
            ))
            failed_count += 1
            continue

        if to_path.exists():
            results.append(RenameFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason="rollback_target_already_exists",
            ))
            failed_count += 1
            continue

        try:
            from_path.rename(to_path)
            results.append(RenameFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="success",
                reason="rolled_back",
            ))
            success_count += 1
        except OSError as exc:
            results.append(RenameFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason=f"rollback_error: {exc}",
            ))
            failed_count += 1

    return RenameExecutionResult(
        plan_id=transaction.plan_id,
        executed=any_attempted,
        dry_run=False,
        total=len(results),
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=0,
        blocked_count=0,
        results=results,
        rollback_available=False,
    )
