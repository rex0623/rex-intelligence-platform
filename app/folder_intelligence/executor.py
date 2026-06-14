"""Phase 15D/15E — Safe move executor.

Provides:
  execute_move_plan(plan, transaction_log=None)
      — actually moves files, only after all plan-level gates pass.
      — if transaction_log provided, persists & updates the transaction.
  build_move_transaction(plan)
      — builds an in-memory transaction for low/medium candidates.
  rollback_move_transaction(tx)
      — reverses successful actions in a transaction.
  rollback_move_transaction_by_id(transaction_id, transaction_log)
      — loads from log and rolls back, updating log action statuses.

這是底層 API（low-level executor）：
  - 不應由模糊指令觸發；Mock LINE 目前「沒有」任何指令會呼叫本模組
    （包含 rollback —— 沒有「確認搬移」也沒有 move rollback 指令）。
  - 呼叫端必須提供 approved 且帶有 validation_report 的 MovePlan。

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
  - Rollback only reverses actions whose status is "success".
  - This is the ONLY module that may move files for move plans.
"""

from pathlib import Path

from app.core.config import resolve_under_safe_root
from app.folder_intelligence.preflight import preflight_move_plan
from app.folder_intelligence.schemas import (
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
    MoveTransaction,
    MoveTransactionAction,
)
from app.core.transaction_log_protocol import MoveTransactionLogProtocol


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


def execute_move_plan(
    plan: MovePlan,
    transaction_log: MoveTransactionLogProtocol | None = None,
) -> MoveExecutionResult:
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

    If transaction_log is provided (Phase 15E):
      - Builds a MoveTransaction and saves it before execution.
      - Updates action statuses (success/failed) in the log after execution.
      - Execution without transaction_log behaves identically to Phase 15D.
    """
    # ── Plan-level gate (mirrors preflight) ─────────────────────────────────
    preflight = preflight_move_plan(plan)
    if plan.status != "approved":
        return preflight  # executed=False already set by preflight
    if plan.validation_report is None:
        return preflight
    if plan.validation_report.blocked_count > 0:
        return preflight

    # ── Persist transaction before execution ────────────────────────────────
    tx: MoveTransaction | None = None
    if transaction_log is not None:
        tx = build_move_transaction(plan)
        transaction_log.save_transaction(tx)

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
        # 相對路徑錨定 SAFE_PDF_ROOT（16B）；path traversal → fail-safe failed
        any_attempted = True
        try:
            original_path = resolve_under_safe_root(original)
            proposed_path = resolve_under_safe_root(proposed)
        except ValueError:
            results.append(_result("failed", "path_escapes_safe_root"))
            failed_count += 1
            continue

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

    execution_result = MoveExecutionResult(
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

    # ── Update persisted transaction statuses ────────────────────────────────
    if transaction_log is not None and tx is not None:
        result_by_orig: dict[str, str] = {r.original_path: r.status for r in results}
        updates: dict[str, str] = {}
        for action in tx.actions:
            file_status = result_by_orig.get(action.original_path)
            if file_status in ("success", "failed"):
                updates[action.original_path] = file_status
        if updates:
            transaction_log.mark_transaction_actions(tx.transaction_id, updates)

    return execution_result


def build_move_transaction(plan: MovePlan) -> MoveTransaction:
    """Build an in-memory MoveTransaction for low/medium-risk candidates.

    High-risk and blocked candidates are excluded.
    Does not execute or touch the filesystem.
    """
    actions: list[MoveTransactionAction] = []

    for candidate in plan.candidates:
        original = candidate.original_path or ""
        proposed = candidate.proposed_path or ""

        if not original or not proposed or original == proposed:
            continue

        risk = _risk_for(plan, candidate.original_filename)
        if risk not in ("low", "medium"):
            continue

        actions.append(MoveTransactionAction(
            original_path=original,
            new_path=proposed,
            status="pending",
            rollback_from=proposed,
            rollback_to=original,
        ))

    return MoveTransaction(
        plan_id=plan.plan_id,
        actions=actions,
    )


def rollback_move_transaction(transaction: MoveTransaction) -> MoveExecutionResult:
    """Reverse all actions whose status is "success".

    Only reverses confirmed successes.  Never touches pending/failed actions.
    Creates the rollback_to parent folder if needed (the source folder may
    have been empty and removed by external cleanup).
    """
    results: list[MoveFileResult] = []
    success_count = failed_count = 0
    any_attempted = False

    for action in transaction.actions:
        if action.status != "success":
            continue

        any_attempted = True
        rollback_from = action.rollback_from or ""
        rollback_to = action.rollback_to or ""
        # 相對路徑錨定 SAFE_PDF_ROOT（16B）；path traversal → fail-safe failed
        try:
            from_path = resolve_under_safe_root(rollback_from)
            to_path = resolve_under_safe_root(rollback_to)
        except ValueError:
            results.append(MoveFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason="path_escapes_safe_root",
            ))
            failed_count += 1
            continue

        if not from_path.exists():
            results.append(MoveFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason="rollback_source_not_found",
            ))
            failed_count += 1
            continue

        if to_path.exists():
            results.append(MoveFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason="rollback_target_already_exists",
            ))
            failed_count += 1
            continue

        try:
            to_path.parent.mkdir(parents=True, exist_ok=True)
            from_path.rename(to_path)
            results.append(MoveFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="success",
                reason="rolled_back",
                rollback_from=rollback_from,
                rollback_to=rollback_to,
            ))
            success_count += 1
        except OSError as exc:
            results.append(MoveFileResult(
                original_path=rollback_from,
                proposed_path=rollback_to,
                status="failed",
                reason=f"rollback_error: {exc}",
            ))
            failed_count += 1

    return MoveExecutionResult(
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


def rollback_move_transaction_by_id(
    transaction_id: str,
    transaction_log: MoveTransactionLogProtocol,
) -> MoveExecutionResult:
    """Load a persisted transaction and rollback all successful actions.

    - If the transaction_id is not found in the log, returns a result with
      executed=False and reason "transaction_not_found".
    - On success, updates the action status to "rolled_back" in the log.
    - If rollback of an individual action fails, the action status is NOT
      changed (it remains "success", indicating the file is still moved).
    """
    tx = transaction_log.load_transaction(transaction_id)

    if tx is None:
        return MoveExecutionResult(
            plan_id="",
            executed=False,
            dry_run=False,
            total=0,
            success_count=0,
            failed_count=1,
            skipped_count=0,
            blocked_count=0,
            results=[MoveFileResult(
                original_path="",
                proposed_path="",
                status="failed",
                reason="transaction_not_found",
            )],
            rollback_available=False,
        )

    rollback_result = rollback_move_transaction(tx)

    # ── Sync log: mark rolled-back actions ───────────────────────────────────
    if rollback_result.executed:
        # result.original_path == action.rollback_from == action.new_path
        rollback_by_new_path: dict[str, str] = {
            r.original_path: r.status for r in rollback_result.results
        }
        updates: dict[str, str] = {}
        for action in tx.actions:
            if action.status == "success":
                rb_status = rollback_by_new_path.get(action.new_path)
                if rb_status == "success":
                    # Rollback succeeded → mark action as rolled_back
                    updates[action.original_path] = "rolled_back"
                # If rb_status == "failed", keep action.status as "success"
                # (file is still in the moved location)
        if updates:
            transaction_log.mark_transaction_actions(transaction_id, updates)

    return rollback_result
