"""Phase 14A — Preflight validation for rename plans.

Checks whether a RenamePlan is safe to execute without mutating the filesystem.
Returns a RenameExecutionResult that always has:
  executed=False, dry_run=True, rollback_available=False, success_count=0.
"""

from app.filename.schemas import (
    RenamePlan,
    RenameExecutionResult,
    RenameFileResult,
)


def _risk_from_report(plan: RenamePlan, original_filename: str) -> str | None:
    """Return the risk_level for *original_filename* from the validation report."""
    report = plan.validation_report
    if report is None:
        return None
    for cv in report.candidates:
        if cv.original_filename == original_filename:
            return cv.risk_level
    return None


def preflight_rename_plan(plan: RenamePlan) -> RenameExecutionResult:
    """Validate whether *plan* is safe to execute.

    Never renames files.  Always returns executed=False, dry_run=True,
    rollback_available=False, success_count=0.
    """
    results: list[RenameFileResult] = []

    def _block_all(reason: str) -> RenameExecutionResult:
        blocked: list[RenameFileResult] = []
        for candidate in plan.candidates:
            blocked.append(
                RenameFileResult(
                    original_path=candidate.original_filename or "",
                    proposed_path=candidate.proposed_filename or "",
                    status="blocked",
                    reason=reason,
                    risk_level="blocked",
                )
            )
        return RenameExecutionResult(
            plan_id=plan.plan_id,
            executed=False,
            dry_run=True,
            total=len(plan.candidates),
            success_count=0,
            failed_count=0,
            skipped_count=0,
            blocked_count=len(blocked),
            results=blocked,
            rollback_available=False,
        )

    # Plan-level gate: must be approved
    if plan.status != "approved":
        return _block_all("plan_not_approved")

    # Plan-level gate: validation report required
    if plan.validation_report is None:
        return _block_all("missing_validation_report")

    # Plan-level gate: no pre-blocked candidates
    if plan.validation_report.blocked_count > 0:
        return _block_all("validation_has_blocked_candidates")

    # Candidate-level checks
    failed = skipped = blocked = 0

    for candidate in plan.candidates:
        original = candidate.original_filename or ""
        proposed = candidate.proposed_filename or ""
        risk = _risk_from_report(plan, original)

        # Missing original path
        if not original:
            results.append(
                RenameFileResult(
                    original_path=original,
                    proposed_path=proposed,
                    status="failed",
                    reason="missing_original_path",
                    risk_level=risk,
                )
            )
            failed += 1
            continue

        # Missing proposed path
        if not proposed:
            results.append(
                RenameFileResult(
                    original_path=original,
                    proposed_path=proposed,
                    status="failed",
                    reason="missing_proposed_path",
                    risk_level=risk,
                )
            )
            failed += 1
            continue

        # Blocked candidate from validation report
        if risk == "blocked":
            results.append(
                RenameFileResult(
                    original_path=original,
                    proposed_path=proposed,
                    status="blocked",
                    reason="blocked_by_validation",
                    risk_level=risk,
                )
            )
            blocked += 1
            continue

        # Same filename — skip
        if proposed == original:
            results.append(
                RenameFileResult(
                    original_path=original,
                    proposed_path=proposed,
                    status="skipped",
                    reason="same_filename",
                    risk_level=risk,
                )
            )
            skipped += 1
            continue

        # High risk — requires manual review
        if risk == "high":
            results.append(
                RenameFileResult(
                    original_path=original,
                    proposed_path=proposed,
                    status="skipped",
                    reason="high_risk_requires_manual_review",
                    risk_level=risk,
                )
            )
            skipped += 1
            continue

        # Low / medium — preflight passed; Phase 14A does not execute
        results.append(
            RenameFileResult(
                original_path=original,
                proposed_path=proposed,
                status="skipped",
                reason="preflight_passed_no_execution_in_phase_14a",
                risk_level=risk,
            )
        )
        skipped += 1

    return RenameExecutionResult(
        plan_id=plan.plan_id,
        executed=False,
        dry_run=True,
        total=len(plan.candidates),
        success_count=0,
        failed_count=failed,
        skipped_count=skipped,
        blocked_count=blocked,
        results=results,
        rollback_available=False,
    )
