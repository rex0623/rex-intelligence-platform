"""Phase 15F — Move Approval-to-Execution Bridge.

Provides:
  execute_approved_move_plan(approval_payload, transaction_log=None)
      — application-layer entry point that restores a MovePlan from an
        approval payload, syncs status to "approved", and executes it
        through the Safe Move Executor.
  execute_approved_move_by_approval_id(approval_id, approval_manager, ...)
      — lookup adapter: loads the approval, enforces approval-level gates
        (exists / is move plan / approved / not already executed), then
        delegates to execute_approved_move_plan() and writes execution
        state back via approval_manager.mark_executed().
  default_move_transaction_log()
      — MoveTransactionLog at runtime/move_transactions.json（已列入
        .gitignore）；測試請改用 tmp_path。

這是底層 bridge（仿照 rename 的 Phase 14D-1）：
  - 未接任何 Mock LINE 指令；沒有「確認搬移」、沒有 move rollback 指令。
  - 只能在測試或程式中明確呼叫。

Safety rules:
  - Payload must be tagged plan_type == "move_plan"（或 type == "move_plan"）。
  - All execution goes through execute_move_plan(); this module never
    touches the filesystem itself (no Path/os/shutil move calls).
  - Approval-level once-only guard: payload 已有 execution_status ==
    "executed" 時直接拒絕（"already_executed"），不重複搬移。
  - 至少一筆搬移成功才標記 executed（沿用 14E mark_executed() 機制）；
    全數失敗（檔案未動）時不標記，允許重試。
"""

from typing import Optional

from pydantic import ValidationError

from app.core.config import get_move_transaction_log_path
from app.folder_intelligence.executor import execute_move_plan
from app.folder_intelligence.schemas import (
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
)
from app.folder_intelligence.transaction_log import MoveTransactionLog


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reject(plan_id: str, reason: str) -> MoveExecutionResult:
    """Build a non-executed rejection result carrying *reason*.

    dry_run=False because the caller requested a real execution that was
    refused (same convention as the rename approval bridge).
    """
    return MoveExecutionResult(
        plan_id=plan_id,
        executed=False,
        dry_run=False,
        total=0,
        success_count=0,
        failed_count=1,
        skipped_count=0,
        blocked_count=0,
        results=[
            MoveFileResult(
                original_path="",
                proposed_path="",
                status="failed",
                reason=reason,
            )
        ],
        rollback_available=False,
    )


def _is_move_plan_payload(payload: dict) -> bool:
    return (
        payload.get("plan_type") == "move_plan"
        or payload.get("type") == "move_plan"
    )


def _restore_move_plan(payload: dict) -> Optional[MovePlan]:
    """Restore a MovePlan from an approval payload, or None if impossible.

    Supports both payload shapes:
      - nested: payload["plan"]（或 payload["move_plan"]）為 plan dict
      - flattened（Phase 15B router 格式）: payload 本身就是
        plan.model_dump() + plan_type 標記（plan_id / candidates /
        validation_report 直接攤平在 payload 上）
    """
    plan_data: Optional[dict] = None

    for key in ("plan", "move_plan"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            plan_data = nested
            break

    if plan_data is None:
        if "plan_id" in payload and "candidates" in payload:
            plan_data = payload
        else:
            return None

    try:
        return MovePlan.model_validate(plan_data)
    except ValidationError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_approved_move_plan(
    approval_payload: dict,
    transaction_log: Optional[MoveTransactionLog] = None,
) -> MoveExecutionResult:
    """Restore a MovePlan from *approval_payload* and execute it.

    Gate order (each failure returns executed=False without calling
    execute_move_plan):

      1. payload is not a move plan        → "not_move_plan"
      2. MovePlan cannot be restored       → "invalid_move_plan_payload"

    On success, the restored plan's status is synced to "approved"
    (the Approval Engine holds the approval state; the serialized plan
    still carries "pending_approval") and execution is delegated to
    execute_move_plan(), which re-runs preflight and enforces all
    plan-level and per-candidate safety rules (missing validation_report,
    blocked candidates, high risk skipped, collision/missing-file checks).
    """
    if not isinstance(approval_payload, dict) or not _is_move_plan_payload(
        approval_payload
    ):
        plan_id = ""
        if isinstance(approval_payload, dict):
            plan_id = str(approval_payload.get("plan_id") or "")
        return _reject(plan_id, "not_move_plan")

    plan = _restore_move_plan(approval_payload)
    if plan is None:
        plan_id = str(approval_payload.get("plan_id") or "")
        return _reject(plan_id, "invalid_move_plan_payload")

    # Approval Engine 已核准；將核准狀態同步到 plan 物件，candidates 與
    # validation_report 由 model_validate 原樣還原，不在此處改動。
    plan.status = "approved"

    return execute_move_plan(plan, transaction_log=transaction_log)


def execute_approved_move_by_approval_id(
    approval_id: str,
    approval_manager,
    transaction_log: Optional[MoveTransactionLog] = None,
) -> MoveExecutionResult:
    """Load an approval by id and execute its MovePlan through the bridge.

    Approval-level gate order (each failure returns executed=False):

      1. approval not found                          → "approval_not_found"
      2. payload is not a move plan                  → "not_move_plan"
      3. approval.status != "approved"               → "approval_not_approved"
      4. payload execution_status == "executed"      → "already_executed"

    On execution with at least one successful move, writes execution state
    back through approval_manager.mark_executed() (Phase 14E mechanism):
    execution_status="executed", executed_at, and execution_transaction_id
    when a transaction was persisted.  All-failed executions (no file
    moved) are NOT marked, so the approval can be retried.
    """
    approval = approval_manager.get(approval_id)
    if approval is None:
        return _reject("", "approval_not_found")

    payload = approval.payload or {}

    if not _is_move_plan_payload(payload):
        return _reject(str(payload.get("plan_id") or ""), "not_move_plan")

    if approval.status != "approved":
        return _reject(str(payload.get("plan_id") or ""), "approval_not_approved")

    # Once-only guard：同一 approval 成功執行過即不可重複搬移。
    # 舊 payload 沒有 execution_status 時視為尚未執行（backward compatible）。
    if payload.get("execution_status") == "executed":
        return _reject(str(payload.get("plan_id") or ""), "already_executed")

    result = execute_approved_move_plan(payload, transaction_log=transaction_log)

    if result.success_count > 0:
        # 從 log 取回本次 plan 對應的 transaction_id（executor 內部建立）
        transaction_id = None
        if transaction_log is not None:
            for tx in transaction_log.list_transactions():
                if tx.plan_id == result.plan_id:
                    transaction_id = tx.transaction_id
        approval_manager.mark_executed(approval_id, transaction_id)

    return result


def default_move_transaction_log() -> MoveTransactionLog:
    """Return a MoveTransactionLog at the default runtime path.

    預設路徑由 settings 取得（16B）：runtime/move_transactions.json
    （已列入 .gitignore）。測試以 monkeypatch settings.RUNTIME_DIR
    或注入 tmp_path log，不可污染 runtime/。
    """
    return MoveTransactionLog(get_move_transaction_log_path())
