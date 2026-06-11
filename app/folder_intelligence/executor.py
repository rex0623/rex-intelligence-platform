"""Phase 15D — Safe move executor.

Provides:
  execute_move_plan(plan)
      — actually moves files, only after all plan-level gates pass.

這是底層 API（low-level executor）：
  - 不應由模糊指令觸發；Mock LINE 目前「沒有」任何指令會呼叫本模組。
  - 呼叫端必須提供 approved 且帶有 validation_report 的 MovePlan。
  - 目前尚未實作 Move Transaction Log 與 Move rollback（Phase 15E）。

Safety rules:
  - execute_move_plan requires plan.status == "approved".
  - execute_move_plan requires plan.validation_report to be present.
  - execute_move_plan requires validation_report.blocked_count == 0.
  - Blocked candidates are never moved.
  - High-risk candidates are skipped by default.
  - Filesystem collision (target exists) prevents move.
  - Missing source file prevents move.
  - Target parent folders are created before moving.
  - Every successful move records rollback_from / rollback_to.
  - This is the ONLY module that may move files for move plans.
"""

from pathlib import Path

from app.folder_intelligence.preflight import preflight_move_plan
from app.folder_intelligence.schemas import (
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _risk_for(plan: MovePlan, original_filename: str) -> str | None:
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


def execute_move_plan(plan: MovePlan) -> MoveExecutionResult:
    """Execute an approved, validated MovePlan by actually moving files.

    Calls preflight_move_plan() first.  Returns early (executed=False) if
    any plan-level gate fails:

      - plan.status != "approved"            → "plan_not_approved"
      - plan.validation_report is None       → "missing_validation_report"
      - validation_report.blocked_count > 0  → "validation_has_blocked_candidates"

    For each candidate the order of checks is:

      1. blocked risk          → blocked
      2. high risk             → skipped
      3. same path             → skipped
      4. missing paths         → failed
      5. original not found    → failed
      6. target already exists → failed
      7. mkdir + Path.rename() → success / failed
    """
    # ── Plan-level gate (mirrors preflight) ─────────────────────────────────
    preflight = preflight_move_plan(plan)
    if plan.status != "approved":
        return preflight  # executed=False already set by preflight
    if plan.validation_report is None:
        return preflight
    if plan.validation_report.blocked_count > 0:
        return preflight

    # ── Per-candidate execution ──────────────────────────────────────────────
    results: list[MoveFileResult] = []
    success_count = failed_count = skipped_count = blocked_count = 0
    any_attempted = False  # True once we hit a filesystem check

    for candidate in plan.candidates:
        original = candidate.original_path or ""
        proposed = candidate.proposed_path or ""
        folder = candidate.proposed_folder or ""
        risk = _risk_for(plan, candidate.original_filename)

        def _result(status: str, reason: str | None, **kwargs) -> MoveFileResult:
            return MoveFileResult(
                original_path=original,
                proposed_path=proposed,
                proposed_folder=folder,
                status=status,
                reason=reason,
                risk_level=risk,
                **kwargs,
            )

        # 1. Blocked by validation report
        if risk == "blocked":
            results.append(_result("blocked", "blocked_by_validation"))
            blocked_count += 1
            continue

        # 2. High risk — skip without touching filesystem
        if risk == "high":
            results.append(_result("skipped", "high_risk_requires_manual_review"))
            skipped_count += 1
            continue

        # 3. Same path — nothing to move
        if original and proposed == original:
            results.append(_result("skipped", "same_path"))
            skipped_count += 1
            continue

        # 4. Missing paths
        if not original:
            results.append(_result("failed", "missing_original_path"))
            failed_count += 1
            continue
        if not proposed:
            results.append(_result("failed", "missing_proposed_path"))
            failed_count += 1
            continue

        # ── From here onward we check the real filesystem ──────────────────
        any_attempted = True
        original_path = Path(original)
        proposed_path = Path(proposed)

        # 5. Original file must exist
        if not original_path.exists():
            results.append(_result("failed", "original_file_not_found"))
            failed_count += 1
            continue

        # 6. Target must not already exist
        if proposed_path.exists():
            results.append(_result("failed", "target_file_already_exists"))
            failed_count += 1
            continue

        # 7. Create target folder and perform move
        try:
            proposed_path.parent.mkdir(parents=True, exist_ok=True)
            original_path.rename(proposed_path)
            results.append(_result(
                "success",
                None,
                rollback_from=proposed,  # new location → where to roll back FROM
                rollback_to=original,    # original location → where to roll back TO
            ))
            success_count += 1
        except OSError as exc:
            results.append(_result("failed", f"move_error: {exc}"))
            failed_count += 1

    return MoveExecutionResult(
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
