#!/usr/bin/env python3
"""Local mock LINE CLI for testing AI Router routing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import asyncio
import re
import uuid

from app.approvals.manager import approval_manager
from app.filename.approval_bridge import execute_approved_rename_plan
from app.filename.executor import rollback_transaction_by_id
from app.filename.schemas import RenamePlan
from app.filename.transaction_log import (
    RenameTransactionLog,
    preview_rollback_transaction,
)
from app.folder_intelligence.approval_bridge import (
    default_move_transaction_log,
    execute_approved_move_by_approval_id,
)
from app.folder_intelligence.formatter import format_move_plan_for_cli
from app.folder_intelligence.schemas import MoveExecutionResult, MovePlan
from app.folder_intelligence.transaction_log import (
    preview_move_rollback_transaction_by_id,
)
from app.router.ai_router import AIRouter
from app.schemas.messages import WorkerRequest
from app.workers.pdf_worker import PDFWorker


def _format_document_summary(inner: dict) -> str:
    """Format an analyze_pdfs payload dict into Document Summary output."""
    lines = ["小雷收到：PDF 智慧分析完成"]
    if inner.get("mode") == "dry-run":
        lines.append("- 模式：dry-run，不會修改 PDF (dry-run 模式)")
    lines.append(f"- PDF 檔案總數：{inner.get('total_pdfs', 0)}")
    lines.append(f"- 可讀數量：{inner.get('readable_pdfs', 0)}")
    classification_counts = inner.get("classification_counts", {})
    if classification_counts:
        counts_text = "、".join([f"{k} {v}" for k, v in classification_counts.items()])
        lines.append(f"- 分類結果：{counts_text}")
    document_objects = inner.get("document_objects", [])
    if document_objects:
        lines.append("- Document Summary：")
        for doc in document_objects:
            doc_type = doc.get("document_type", "unknown")
            confidence = doc.get("confidence", 0.0)
            source = doc.get("source_file", "")
            lines.append(f"  * [{doc_type}] {source} (confidence: {confidence:.2f})")
            for field in doc.get("fields", []):
                lines.append(f"    - {field.get('name')}：{field.get('value')}")
    return "\n".join(lines)


def _run_analyze_pdfs() -> dict:
    """Call PDFWorker.analyze_pdfs and return the inner payload dict."""
    worker = PDFWorker()
    request = WorkerRequest(
        worker_id="pdf_worker",
        action="analyze_pdfs",
        payload={},
        user_id="cli",
        request_id=str(uuid.uuid4()),
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()
    return data.get("data", {}).get("data", {})


def _analyze_pdfs_direct() -> str:
    """Directly call PDFWorker.analyze_pdfs, bypassing the router."""
    return _format_document_summary(_run_analyze_pdfs())


def _format_document_detail(inner: dict) -> str:
    """Format analyze_pdfs payload into a verbose per-PDF detail view."""
    lines = ["小雷收到：PDF 詳細分析完成"]
    if inner.get("mode") == "dry-run":
        lines.append("- 模式：dry-run，不會修改 PDF (dry-run 模式)")
    total = inner.get("total_pdfs", 0)
    lines.append(f"- PDF 檔案總數：{total}")
    lines.append(f"- 可讀數量：{inner.get('readable_pdfs', 0)}")
    summaries = inner.get("pdf_summaries", [])
    for i, summary in enumerate(summaries, start=1):
        lines.append("")
        lines.append(f"[{i}/{total}] {summary.get('file_name', '')}")
        doc = summary.get("document_object") or {}
        doc_type_raw = doc.get("document_type", "unknown")
        doc_type = doc_type_raw.value if hasattr(doc_type_raw, "value") else str(doc_type_raw)
        lines.append(f"  - document_type：{doc_type}")
        confidence = doc.get("confidence", 0.0)
        lines.append(f"  - confidence：{confidence:.2f}")
        lines.append(f"  - text_length：{summary.get('text_length', 0)}")
        first_200 = summary.get("first_200_chars", "")
        lines.append(f"  - first_200_chars：{first_200}")
        fields = doc.get("fields", [])
        if fields:
            lines.append("  - extracted_fields：")
            for field in fields:
                lines.append(f"    * {field.get('name')}：{field.get('value')}")
        else:
            lines.append("  - extracted_fields：（無）")
    return "\n".join(lines)


def _analyze_pdfs_detail() -> str:
    """Directly call PDFWorker.analyze_pdfs and return the verbose detail view."""
    return _format_document_detail(_run_analyze_pdfs())


def _format_rename_plan(response: dict) -> str:
    """Format a generate_rename_plan response for mock LINE CLI output."""
    plan = response.get("rename_plan", {})
    approval_id = response.get("approval_id", "")
    validation = plan.get("validation_report") or {}
    val_by_file = {
        v["original_filename"]: v for v in validation.get("candidates", [])
    }
    plan_issues = validation.get("plan_issues", [])

    lines = ["小雷收到：已產生改名計畫（dry-run）"]
    lines.append("- 模式：dry-run，不會實際更名")
    lines.append(f"- 待處理檔案：{plan.get('total_files', 0)} 份")
    lines.append(f"- 可改名：{plan.get('renamed_count', 0)} 份")

    # Risk summary
    lines.append("")
    lines.append("風險摘要：")
    lines.append(
        f"  低風險 {validation.get('low_count', 0)} 份"
        f" | 中風險 {validation.get('medium_count', 0)} 份"
        f" | 高風險 {validation.get('high_count', 0)} 份"
        f" | 封鎖 {validation.get('blocked_count', 0)} 份"
    )
    if plan_issues:
        for issue in plan_issues:
            lines.append(f"  ⚠ {issue}")

    lines.append("")
    lines.append("改名計畫：")

    for i, c in enumerate(plan.get("candidates", []), 1):
        orig = c.get("original_filename", "?")
        proposed = c.get("proposed_filename")
        confidence = c.get("confidence", 0.0)
        val = val_by_file.get(orig, {})
        risk = val.get("risk_level", "unknown")
        issues = val.get("issues", [])

        lines.append(f"  [{i}] {orig}")
        if proposed:
            lines.append(f"      → {proposed}")
            lines.append(f"      信心度：{confidence:.2f} | 風險：{risk}")
        else:
            lines.append("      → （無法產生建議檔名）")
            lines.append(f"      風險：{risk}")
        if issues:
            lines.append(f"      問題：{'、'.join(issues)}")

    if approval_id:
        lines.append("")
        lines.append(f"若要確認，請輸入：確認 {approval_id}")
        lines.append(f"若要取消，請輸入：取消 {approval_id}")
        lines.append(f"核准後若要實際執行改名，請輸入：確認改名 {approval_id}")

    return "\n".join(lines)


_RENAME_PLAN_KEYWORDS = ["產生改名計畫", "整理檔名", "分析 PDF 並產生改名計畫"]

# Move planning 關鍵字（Phase 15B）：只產生 MovePlan + approval + dry-run 顯示，
# 不會搬移任何檔案；本階段沒有任何真實搬移指令。
_MOVE_PLAN_KEYWORDS = [
    "產生搬移計畫",
    "整理資料夾",
    "分析 PDF 並產生搬移計畫",
    "產生資料夾歸檔計畫",
]


def _format_move_plan_response(response: dict) -> str:
    """Format a generate_move_plan response for mock LINE CLI output."""
    plan = MovePlan.model_validate(response.get("move_plan", {}))
    lines = [format_move_plan_for_cli(plan)]

    approval_id = response.get("approval_id", "")
    if approval_id:
        lines.append("")
        lines.append(f"- approval_id：{approval_id}")
        lines.append(f"若要核准此搬移計畫（僅 dry-run 報告），請輸入：確認 {approval_id}")
        lines.append(f"若要取消，請輸入：取消 {approval_id}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Phase 14D-2 — Explicit confirm rename command
# ---------------------------------------------------------------------------

# 唯一可觸發真實更名的指令格式：「確認改名 {approval_id}」（完全符合才生效）。
# 「確認」「確認改名」「好」「OK」「執行」等都不會匹配。
_CONFIRM_RENAME_PATTERN = re.compile(r"^確認改名\s+(\S+)$")

# Rollback 預覽指令格式（Phase 14D-3A）：「預覽回滾改名 {transaction_id}」。
# 純讀取，不會 rollback、不會修改任何檔案或 transaction log。
_PREVIEW_ROLLBACK_PATTERN = re.compile(r"^預覽回滾改名\s+(\S+)$")

# Rollback 執行指令格式（Phase 14D-3B）：「回滾改名 {transaction_id}」。
# 唯一可觸發真實 rollback 的指令；完全比對才生效。
# 「回滾」「回滾改名」「確認」「好」「OK」「執行」或附加多餘文字均不匹配。
_ROLLBACK_RENAME_PATTERN = re.compile(r"^回滾改名\s+(\S+)$")

# 唯一可觸發真實搬移的指令格式（Phase 15G）：「確認搬移 {approval_id}」。
# full match 才生效；「確認」「搬移」「確認搬移」「確認搬移一下 …」
# 「請幫我確認搬移 …」「整理資料夾」「產生搬移計畫」均不匹配。
_CONFIRM_MOVE_PATTERN = re.compile(r"^確認搬移\s+([A-Za-z0-9_-]+)$")

# Move rollback 預覽指令格式（Phase 15H）：「預覽回滾搬移 {transaction_id}」。
# 純讀取，不 rollback、不搬移檔案、不寫 transaction log。
# full match 才生效；「回滾搬移 …」「預覽搬移回滾 …」「請幫我預覽回滾搬移 …」
# 「預覽回滾搬移」「預覽回滾搬移一下 …」均不匹配。
# 仍沒有任何真實 move rollback 指令。
_PREVIEW_MOVE_ROLLBACK_PATTERN = re.compile(r"^預覽回滾搬移\s+([A-Za-z0-9_-]+)$")

_DEFAULT_TRANSACTION_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "runtime" / "rename_transactions.json"
)

# Approval bridge 的 plan-level gate 拒絕理由 → 使用者訊息
_BRIDGE_REJECT_MESSAGES = {
    "plan_not_approved": "改名計畫尚未核准，無法執行",
    "missing_validation_report": "改名計畫缺少 validation_report，無法執行",
    "validation_has_blocked_candidates": "改名計畫包含 blocked candidate，無法執行",
}


def _payload_to_rename_plan(payload: object) -> RenamePlan | None:
    """Minimal adapter: convert an approval payload dict back to RenamePlan.

    Returns None if the payload is not a rename plan (e.g. a pdf_bill
    workflow plan or empty payload).
    """
    if not isinstance(payload, dict):
        return None
    # MovePlan payload 也有 plan_id / candidates，不可被當成 RenamePlan 執行
    if payload.get("plan_type") == "move_plan":
        return None
    if "plan_id" not in payload or "candidates" not in payload:
        return None
    try:
        return RenamePlan.model_validate(payload)
    except Exception:
        return None


def confirm_rename(
    approval_id: str,
    transaction_log: RenameTransactionLog | None = None,
) -> str:
    """Handle the explicit 「確認改名 {approval_id}」 command.

    The only Mock LINE path that can trigger a real rename.  All execution
    goes through execute_approved_rename_plan() (approval bridge), which
    delegates to the safe rename executor; this module never renames files.
    """
    approval = approval_manager.get(approval_id)
    if approval is None:
        return f"小雷收到：找不到 approval：{approval_id}"

    if approval.status != "approved":
        return (
            f"小雷收到：approval {approval_id} 尚未核准（狀態：{approval.status}），"
            f"請先輸入：確認 {approval_id}"
        )

    # Once-only guard (Phase 14E)：同一 approval 成功執行過即不可重複執行。
    # 舊 approval payload 沒有 execution_status 時視為尚未執行（backward compatible）。
    payload = approval.payload or {}
    if payload.get("execution_status") == "executed":
        executed_tx = payload.get("execution_transaction_id")
        lines = ["小雷收到：此改名計畫已執行過，不會重複執行"]
        lines.append(f"- approval_id：{approval_id}")
        if executed_tx:
            lines.append(f"- transaction_id：{executed_tx}")
            lines.append(f"如需復原，請輸入：預覽回滾改名 {executed_tx}")
            lines.append(f"或輸入：回滾改名 {executed_tx}")
        return "\n".join(lines)

    plan = _payload_to_rename_plan(approval.payload)
    if plan is None:
        return f"小雷收到：approval {approval_id} 的內容不是改名計畫，不支援「確認改名」"

    # Approval Engine 已核准此 approval，將核准狀態同步到 plan 物件，
    # 由 approval bridge 重新驗證所有 gate（validation_report、blocked_count）。
    plan.status = "approved"

    if transaction_log is None:
        transaction_log = RenameTransactionLog(_DEFAULT_TRANSACTION_LOG_PATH)

    result = execute_approved_rename_plan(plan, transaction_log=transaction_log)

    # Bridge plan-level gate 拒絕：回覆統一原因
    if not result.executed and result.results:
        reasons = {r.reason for r in result.results}
        if len(reasons) == 1:
            reason = next(iter(reasons))
            if reason in _BRIDGE_REJECT_MESSAGES:
                return f"小雷收到：{_BRIDGE_REJECT_MESSAGES[reason]}"

    # 從 log 取回本次 plan 對應的 transaction_id（executor 內部建立）
    transaction_id = None
    for tx in transaction_log.list_transactions():
        if tx.plan_id == plan.plan_id:
            transaction_id = tx.transaction_id

    # Once-only guard (Phase 14E)：至少一筆真實更名成功才標記已執行；
    # 全數失敗（檔案未動）時允許重試。
    if result.success_count > 0:
        approval_manager.mark_executed(approval_id, transaction_id)

    lines = ["小雷收到：已執行改名"]
    lines.append(f"- approval_id：{approval_id}")
    lines.append(
        f"- 成功：{result.success_count} 筆"
        f" | 失敗：{result.failed_count} 筆"
        f" | 跳過：{result.skipped_count} 筆"
        f" | blocked：{result.blocked_count} 筆"
    )
    if transaction_id:
        lines.append(f"- transaction_id：{transaction_id}")
    if result.results:
        lines.append("檔案結果：")
        for i, r in enumerate(result.results, 1):
            entry = f"  [{i}] {r.original_path} → {r.proposed_path}：{r.status}"
            if r.reason:
                entry += f"（{r.reason}）"
            lines.append(entry)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 15G — Explicit confirm move command
# ---------------------------------------------------------------------------

# Move bridge 的拒絕理由 → 使用者訊息（bridge-level 與 plan-level gates）
_MOVE_REJECT_MESSAGES = {
    "approval_not_found": "找不到 approval",
    "not_move_plan": "approval 的內容不是搬移計畫，不支援「確認搬移」",
    "approval_not_approved": "approval 尚未核准，請先輸入：確認 {approval_id}",
    "already_executed": "此搬移計畫已執行過，不會重複執行",
    "invalid_move_plan_payload": "approval payload 無法還原搬移計畫，無法執行",
    "plan_not_approved": "搬移計畫尚未核准，無法執行",
    "missing_validation_report": "搬移計畫缺少 validation_report，無法執行",
    "validation_has_blocked_candidates": "搬移計畫包含 blocked candidate，無法執行",
}


def _format_move_execution_response(
    result: MoveExecutionResult,
    approval_id: str,
    transaction_id: str | None = None,
) -> str:
    """Format a MoveExecutionResult into the mock LINE reply."""
    lines = ["小雷收到：搬移執行結果"]
    lines.append(f"- approval_id：{approval_id}")
    lines.append(f"- executed：{result.executed} | dry_run：{result.dry_run}")
    lines.append(
        f"- 總數：{result.total} 筆"
        f" | 成功：{result.success_count} 筆"
        f" | 失敗：{result.failed_count} 筆"
        f" | 跳過：{result.skipped_count} 筆"
        f" | blocked：{result.blocked_count} 筆"
    )
    if transaction_id:
        lines.append(f"- transaction_id：{transaction_id}")

    # 未執行且所有結果同一原因 → 顯示明確拒絕訊息
    if not result.executed and result.results:
        reasons = {r.reason for r in result.results}
        if len(reasons) == 1:
            reason = next(iter(reasons))
            if reason in _MOVE_REJECT_MESSAGES:
                message = _MOVE_REJECT_MESSAGES[reason].format(approval_id=approval_id)
                lines.append(f"- 原因：{reason}（{message}）")

    if result.results:
        lines.append("檔案結果：")
        for i, r in enumerate(result.results, 1):
            entry = f"  [{i}] {r.original_path} → {r.proposed_path}：{r.status}"
            if r.reason:
                entry += f"（{r.reason}）"
            lines.append(entry)
            if r.rollback_from and r.rollback_to:
                lines.append(f"      rollback_from：{r.rollback_from}")
                lines.append(f"      rollback_to：{r.rollback_to}")

    if result.rollback_available:
        lines.append("已建立 rollback 資訊，但目前尚未開放 Mock LINE 回滾搬移指令。")
    return "\n".join(lines)


def confirm_move(
    approval_id: str,
    move_transaction_log=None,
) -> str:
    """Handle the explicit 「確認搬移 {approval_id}」 command (Phase 15G).

    The only Mock LINE path that can trigger a real move.  All execution
    goes through execute_approved_move_by_approval_id() (move approval
    bridge), which enforces approval gates + once-only guard and delegates
    to the safe move executor; this module never moves files itself.
    """
    if move_transaction_log is None:
        move_transaction_log = default_move_transaction_log()

    result = execute_approved_move_by_approval_id(
        approval_id,
        approval_manager,
        transaction_log=move_transaction_log,
    )

    # 成功執行後 bridge 透過 mark_executed() 回寫 execution_transaction_id；
    # already_executed 時 payload 也已帶有先前的 transaction_id。
    transaction_id = None
    approval = approval_manager.get(approval_id)
    if approval is not None and approval.payload:
        transaction_id = approval.payload.get("execution_transaction_id")

    return _format_move_execution_response(result, approval_id, transaction_id)


# ---------------------------------------------------------------------------
# Phase 15H — Move rollback preview command (read-only)
# ---------------------------------------------------------------------------


def _format_move_rollback_preview_response(preview, transaction_id: str) -> str:
    """Format a MoveRollbackPreview (or None) into the mock LINE reply."""
    if preview is None:
        return (
            f"小雷收到：找不到 transaction：{transaction_id}"
            f"（transaction_not_found）"
        )

    lines = ["小雷收到：搬移回滾預覽"]
    lines.append(f"- transaction_id：{preview.transaction_id}")
    lines.append(
        f"- total：{preview.total} 筆"
        f" | rollbackable_count：{preview.rollbackable_count} 筆"
        f" | already_rolled_back_count：{preview.already_rolled_back_count} 筆"
        f" | failed_count：{preview.failed_count} 筆"
    )
    if preview.actions:
        lines.append("Action 摘要：")
        for i, action in enumerate(preview.actions, 1):
            lines.append(f"  [{i}] {action.original_path} → {action.new_path}")
            lines.append(
                f"      狀態：{action.status}"
                f" | 可回滾：{'是' if action.rollbackable else '否'}"
                + (f"（{action.reason}）" if action.reason else "")
            )
            if action.rollback_from:
                lines.append(f"      rollback_from：{action.rollback_from}")
            if action.rollback_to:
                lines.append(f"      rollback_to：{action.rollback_to}")
    if not preview.has_rollbackable_actions:
        if preview.is_fully_rolled_back:
            lines.append("此交易已全部回滾，目前沒有可回滾項目。")
        else:
            lines.append("目前沒有可回滾項目。")
    lines.append("這只是預覽，尚未實際回滾任何檔案。")
    lines.append("目前尚未開放 Mock LINE 的真實 move rollback 指令。")
    return "\n".join(lines)


def preview_move_rollback(
    transaction_id: str,
    move_transaction_log=None,
) -> str:
    """Handle the explicit 「預覽回滾搬移 {transaction_id}」 command (read-only).

    Only queries the move transaction log and formats a preview via
    preview_move_rollback_transaction_by_id().  Never rolls back, never
    moves files, never writes to the transaction log.
    """
    if move_transaction_log is None:
        move_transaction_log = default_move_transaction_log()

    preview = preview_move_rollback_transaction_by_id(
        transaction_id, move_transaction_log
    )
    return _format_move_rollback_preview_response(preview, transaction_id)


def format_mock_response(worker_response: object) -> str:
    """Format the router worker response for mock LINE CLI output."""
    if isinstance(worker_response, dict):
        if worker_response.get("action") == "generate_rename_plan":
            return _format_rename_plan(worker_response)

        if worker_response.get("action") == "generate_move_plan":
            return _format_move_plan_response(worker_response)

        if worker_response.get("status") == "dry_run_completed":
            if worker_response.get("action") == "move_plan":
                lines = ["小雷收到：搬移計畫已確認（dry-run）"]
                risk_summary = worker_response.get("risk_summary", {})
                if risk_summary:
                    lines.append(
                        f"風險摘要："
                        f"低風險 {risk_summary.get('low', 0)} 份"
                        f" | 中風險 {risk_summary.get('medium', 0)} 份"
                        f" | 高風險 {risk_summary.get('high', 0)} 份"
                        f" | 封鎖 {risk_summary.get('blocked', 0)} 份"
                    )
                for step in worker_response.get("steps", []):
                    lines.append(f"- {step.get('name')}：{step.get('result')}")
                lines.append(
                    f"注意：{worker_response.get('note', '本次沒有實際搬移任何檔案')}"
                )
                return "\n".join(lines)

            if worker_response.get("action") == "rename_plan":
                lines = ["小雷收到：改名計畫已確認（dry-run）"]
                risk_summary = worker_response.get("risk_summary", {})
                if risk_summary:
                    lines.append(
                        f"風險摘要："
                        f"低風險 {risk_summary.get('low', 0)} 份"
                        f" | 中風險 {risk_summary.get('medium', 0)} 份"
                        f" | 高風險 {risk_summary.get('high', 0)} 份"
                        f" | 封鎖 {risk_summary.get('blocked', 0)} 份"
                    )
                for step in worker_response.get("steps", []):
                    lines.append(f"- {step.get('name')}：{step.get('result')}")
                lines.append(f"注意：{worker_response.get('note', '本次沒有實際更名任何 PDF')}")
            else:
                lines = ["小雷收到：workflow 已確認，以下是 dry-run 執行報告"]
                for step in worker_response.get("steps", []):
                    lines.append(f"- {step.get('name')}：{step.get('result')}")
                lines.append("注意：本次沒有修改任何 PDF")
            return "\n".join(lines)

        data = worker_response.get("data", {})
        # handle workflow plan payloads
        if worker_response.get("workflow_type") == "pdf_bill":
            steps = worker_response.get("steps", [])
            lines = [f"小雷收到：已建立電費單處理流程（{'dry-run' if worker_response.get('dry_run') else 'live'}）"]
            lines.append(f"狀態：{worker_response.get('status')}")
            lines.append("步驟：")
            for i, s in enumerate(steps, start=1):
                lines.append(f"{i}. {s.get('name')}")
            lines.append("注意：目前不會更名、不會修改 PDF")
            approval_id = worker_response.get('approval_id')
            if approval_id:
                lines.append("")
                lines.append(f"若要確認，請輸入：確認 {approval_id}")
                lines.append(f"若要取消，請輸入：取消 {approval_id}")
            return "\n".join(lines)
        # handle PDF analysis response
        if isinstance(data, dict) and data.get("action") == "analyze_pdfs":
            inner = data.get("data", {})
            return _format_document_summary(inner)
        # handle nested worker response structure
        inner = {}
        if isinstance(data, dict) and data.get("action") == "analyze_folder":
            inner = data.get("data", {})
        elif isinstance(data, dict) and data.get("dry_run") is not None:
            inner = data

        if inner:
            lines = ["小雷收到：資料夾分析完成"]
            if inner.get("dry_run") is True:
                lines.append("- 模式：dry-run，不會搬移或刪除 (dry-run 模式)")
            total = inner.get("total_files", 0)
            # include both colon and space variants to ease test matching
            lines.append(f"- 檔案總數：{total} (檔案總數 {total})")
            counts = inner.get("extension_counts", {})
            if counts:
                stats = "、".join([f"{k} {v}" for k, v in counts.items()])
            else:
                stats = "無"
            lines.append(f"- 類型統計：{stats}")
            suggestions = inner.get("suggested_folders", [])
            if suggestions:
                lines.append(f"- 建議分類：{ '、'.join(suggestions) }")
            return "\n".join(lines)

        return f"小雷收到：{worker_response}"

    return f"小雷收到：{worker_response}"


def preview_rollback(
    transaction_id: str,
    transaction_log: RenameTransactionLog | None = None,
) -> str:
    """Handle the explicit 「預覽回滾改名 {transaction_id}」 command (read-only).

    Only queries the transaction log and formats a preview.  Never rolls
    back, never renames files, never writes to the transaction log.
    """
    if transaction_log is None:
        transaction_log = RenameTransactionLog(_DEFAULT_TRANSACTION_LOG_PATH)

    preview = preview_rollback_transaction(transaction_id, transaction_log)
    if preview is None:
        return f"小雷收到：找不到 transaction：{transaction_id}"

    lines = ["小雷收到：回滾預覽"]
    lines.append(f"- 交易 ID：{preview.transaction_id}")
    lines.append(f"- Plan ID：{preview.plan_id}")
    lines.append(
        f"- 可回滾：{preview.rollbackable_count} 筆"
        f" | 已回滾：{preview.rolled_back_count} 筆"
        f" | 失敗：{preview.failed_count} 筆"
        f" | pending：{preview.pending_count} 筆"
        f"（共 {preview.total_actions} 筆）"
    )
    if preview.actions:
        lines.append("Action 摘要：")
        for i, action in enumerate(preview.actions, 1):
            lines.append(f"  [{i}] {action.new_path} → {action.original_path}")
            lines.append(
                f"      狀態：{action.status}"
                f" | 可回滾：{'是' if action.rollbackable else '否'}"
            )
    if not preview.has_rollbackable_actions:
        if preview.is_fully_rolled_back:
            lines.append("此交易已全部回滾，目前沒有可回滾項目。")
        else:
            lines.append("目前沒有可回滾項目。")
    lines.append("目前僅預覽，尚未執行回滾。")
    return "\n".join(lines)


def rollback_rename(
    transaction_id: str,
    transaction_log: RenameTransactionLog | None = None,
) -> str:
    """Handle the explicit 「回滾改名 {transaction_id}」 command.

    The only Mock LINE path that can trigger a real rollback.  All execution
    goes through rollback_transaction_by_id(), which reverses successful
    actions via the safe executor and marks them "rolled_back" in the log;
    this module never renames files itself.
    """
    if transaction_log is None:
        transaction_log = RenameTransactionLog(_DEFAULT_TRANSACTION_LOG_PATH)

    # Once-only guard (Phase 14E)：先以 read-only preview 判斷狀態，
    # 沒有可回滾 action 時完全不進入 rollback 執行路徑（不動檔案、不寫 log）。
    preview = preview_rollback_transaction(transaction_id, transaction_log)
    if preview is None:
        return f"小雷收到：找不到 transaction：{transaction_id}"
    if not preview.has_rollbackable_actions:
        if preview.is_fully_rolled_back:
            return (
                f"小雷收到：此交易已回滾完成"
                f"（已回滾 {preview.rolled_back_count} 筆），沒有可回滾項目"
            )
        return f"小雷收到：transaction {transaction_id} 沒有可回滾項目"

    result = rollback_transaction_by_id(transaction_id, transaction_log)

    if not result.executed:
        # 理論上 preview guard 已擋掉；保留原行為作為防護
        reasons = {r.reason for r in result.results}
        if "transaction_not_found" in reasons:
            return f"小雷收到：找不到 transaction：{transaction_id}"
        return f"小雷收到：transaction {transaction_id} 沒有可回滾項目"

    lines = ["小雷收到：已執行回滾改名"]
    lines.append(f"- transaction_id：{transaction_id}")
    lines.append(
        f"- 成功：{result.success_count} 筆"
        f" | 失敗：{result.failed_count} 筆"
        f" | 跳過：{result.skipped_count} 筆"
        f" | blocked：{result.blocked_count} 筆"
    )
    if result.results:
        lines.append("檔案結果：")
        for i, r in enumerate(result.results, 1):
            entry = f"  [{i}] {r.original_path} → {r.proposed_path}：{r.status}"
            if r.reason:
                entry += f"（{r.reason}）"
            lines.append(entry)
    return "\n".join(lines)


def mock_line_payload(
    text: str,
    transaction_log: RenameTransactionLog | None = None,
    move_transaction_log=None,
) -> str:
    """Run the AI Router against a text input and return the mock LINE reply."""
    # Explicit confirm move (Phase 15G): exact「確認搬移 {approval_id}」only.
    # 唯一可觸發真實搬移的指令；其他文字（含「確認」「搬移」「整理資料夾」
    # 「產生搬移計畫」「確認改名」）一律不會進入 move 執行路徑。
    confirm_move_match = _CONFIRM_MOVE_PATTERN.match(text.strip())
    if confirm_move_match:
        return confirm_move(
            confirm_move_match.group(1),
            move_transaction_log=move_transaction_log,
        )

    # Move rollback preview (Phase 15H): exact「預覽回滾搬移 {transaction_id}」
    # only.  Read-only：不 rollback、不搬移、不寫 log；「回滾搬移 …」不是指令。
    preview_move_rollback_match = _PREVIEW_MOVE_ROLLBACK_PATTERN.match(text.strip())
    if preview_move_rollback_match:
        return preview_move_rollback(
            preview_move_rollback_match.group(1),
            move_transaction_log=move_transaction_log,
        )

    # Rollback preview (Phase 14D-3A): exact「預覽回滾改名 {transaction_id}」only
    preview_rollback_match = _PREVIEW_ROLLBACK_PATTERN.match(text.strip())
    if preview_rollback_match:
        return preview_rollback(
            preview_rollback_match.group(1),
            transaction_log=transaction_log,
        )

    # Rollback execution (Phase 14D-3B): exact「回滾改名 {transaction_id}」only
    rollback_rename_match = _ROLLBACK_RENAME_PATTERN.match(text.strip())
    if rollback_rename_match:
        return rollback_rename(
            rollback_rename_match.group(1),
            transaction_log=transaction_log,
        )

    # Explicit confirm rename (Phase 14D-2): exact「確認改名 {approval_id}」only
    confirm_rename_match = _CONFIRM_RENAME_PATTERN.match(text.strip())
    if confirm_rename_match:
        return confirm_rename(
            confirm_rename_match.group(1),
            transaction_log=transaction_log,
        )

    # Move/Rename planning: must be checked before 分析 PDF to handle
    # 分析 PDF 並產生搬移計畫 / 分析 PDF 並產生改名計畫
    if any(kw in text for kw in _MOVE_PLAN_KEYWORDS) or any(
        kw in text for kw in _RENAME_PLAN_KEYWORDS
    ):
        router = AIRouter()
        result = asyncio.run(router.route(message=text))
        worker_response = result.get("worker_response", "我還不確定你的需求，可以再說清楚一點嗎？")
        return format_mock_response(worker_response)

    if "分析 PDF 詳細" in text or "分析pdf詳細" in text.lower():
        return _analyze_pdfs_detail()
    if "分析 PDF" in text or "分析pdf" in text.lower():
        return _analyze_pdfs_direct()

    router = AIRouter()
    result = asyncio.run(router.route(message=text))
    worker_response = result.get("worker_response", "我還不確定你的需求，可以再說清楚一點嗎？")
    return format_mock_response(worker_response)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock LINE CLI for local AI Router testing."
    )
    parser.add_argument("text", help="Text message to send to AI Router.")
    args = parser.parse_args()

    reply = mock_line_payload(args.text)
    print(reply)


if __name__ == "__main__":
    main()
