"""Phase 15C — Preflight validation for move plans.

Checks whether a MovePlan would be safe to execute in a future phase,
without touching the filesystem at all:
  - never moves files
  - never creates folders
  - never checks real file existence (read-only data validation only)

Always returns a MoveExecutionResult with:
  executed=False, dry_run=True, success_count=0, rollback_available=False.
"""

from app.folder_intelligence.schemas import (
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
)


def _risk_from_report(plan: MovePlan, original_filename: str) -> str | None:
    """Return the risk_level for *original_filename* from the validation report."""
    report = plan.validation_report
    if report is None:
        return None
    for cv in report.candidates:
        if cv.original_filename == original_filename:
            return cv.risk_level
    return None


def preflight_move_plan(plan: MovePlan) -> MoveExecutionResult:
    """Validate whether *plan* would be safe to execute.

    Never moves files or creates folders.  Always returns executed=False,
    dry_run=True, success_count=0, rollback_available=False.
    """
    def _block_all(reason: str) -> MoveExecutionResult:
        blocked: list[MoveFileResult] = []
        for candidate in plan.candidates:
            blocked.append(
                MoveFileResult(
                    original_path=candidate.original_path or "",
                    proposed_path=candidate.proposed_path or "",
                    proposed_folder=candidate.proposed_folder or "",
                    status="blocked",
                    reason=reason,
                    risk_level="blocked",
                )
            )
        return MoveExecutionResult(
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

    # ── Plan-level gates ─────────────────────────────────────────────────────
    if plan.status != "approved":
        return _block_all("plan_not_approved")

    if plan.validation_report is None:
        return _block_all("missing_validation_report")

    if plan.validation_report.blocked_count > 0:
        return _block_all("validation_has_blocked_candidates")

    # ── Candidate-level checks ───────────────────────────────────────────────
    results: list[MoveFileResult] = []
    failed = skipped = blocked = 0

    for candidate in plan.candidates:
        original_path = candidate.original_path or ""
        proposed_folder = candidate.proposed_folder or ""
        proposed_path = candidate.proposed_path or ""
        risk = _risk_from_report(plan, candidate.original_filename)

        def _add(status: str, reason: str) -> MoveFileResult:
            return MoveFileResult(
                original_path=original_path,
                proposed_path=proposed_path,
                proposed_folder=proposed_folder,
                status=status,
                reason=reason,
                risk_level=risk,
            )

        # Missing original path
        if not original_path:
            results.append(_add("failed", "missing_original_path"))
            failed += 1
            continue

        # Missing proposed folder
        if not proposed_folder:
            results.append(_add("failed", "missing_proposed_folder"))
            failed += 1
            continue

        # Missing proposed path
        if not proposed_path:
            results.append(_add("failed", "missing_proposed_path"))
            failed += 1
            continue

        # Blocked candidate from validation report
        if risk == "blocked":
            results.append(_add("blocked", "blocked_by_validation"))
            blocked += 1
            continue

        # Same path — nothing to move
        if proposed_path == original_path:
            results.append(_add("skipped", "same_path"))
            skipped += 1
            continue

        # High risk — requires manual review
        if risk == "high":
            results.append(_add("skipped", "high_risk_requires_manual_review"))
            skipped += 1
            continue

        # Low / medium — preflight passed; Phase 15C does not execute
        results.append(_add("skipped", "preflight_passed_no_execution_in_phase_15c"))
        skipped += 1

    return MoveExecutionResult(
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
