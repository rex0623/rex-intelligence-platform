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
from app.filename.schemas import RenamePlan
from app.filename.transaction_log import (
    RenameTransactionLog,
    preview_rollback_transaction,
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

# ---------------------------------------------------------------------------
# Phase 14D-2 — Explicit confirm rename command
# ---------------------------------------------------------------------------

# 唯一可觸發真實更名的指令格式：「確認改名 {approval_id}」（完全符合才生效）。
# 「確認」「確認改名」「好」「OK」「執行」等都不會匹配。
_CONFIRM_RENAME_PATTERN = re.compile(r"^確認改名\s+(\S+)$")

# Rollback 預覽指令格式（Phase 14D-3A）：「預覽回滾改名 {transaction_id}」。
# 純讀取，不會 rollback、不會修改任何檔案或 transaction log。
# 「回滾」「回滾改名」「預覽回滾」等都不會匹配，本階段也沒有任何
# 真實 rollback 指令。
_PREVIEW_ROLLBACK_PATTERN = re.compile(r"^預覽回滾改名\s+(\S+)$")

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


def format_mock_response(worker_response: object) -> str:
    """Format the router worker response for mock LINE CLI output."""
    if isinstance(worker_response, dict):
        if worker_response.get("action") == "generate_rename_plan":
            return _format_rename_plan(worker_response)

        if worker_response.get("status") == "dry_run_completed":
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
    lines.append("目前僅預覽，尚未執行回滾。")
    return "\n".join(lines)


def mock_line_payload(
    text: str,
    transaction_log: RenameTransactionLog | None = None,
) -> str:
    """Run the AI Router against a text input and return the mock LINE reply."""
    # Rollback preview (Phase 14D-3A): exact「預覽回滾改名 {transaction_id}」only
    preview_rollback_match = _PREVIEW_ROLLBACK_PATTERN.match(text.strip())
    if preview_rollback_match:
        return preview_rollback(
            preview_rollback_match.group(1),
            transaction_log=transaction_log,
        )

    # Explicit confirm rename (Phase 14D-2): exact「確認改名 {approval_id}」only
    confirm_rename_match = _CONFIRM_RENAME_PATTERN.match(text.strip())
    if confirm_rename_match:
        return confirm_rename(
            confirm_rename_match.group(1),
            transaction_log=transaction_log,
        )

    # Rename planning: must be checked before 分析 PDF to handle 分析 PDF 並產生改名計畫
    if any(kw in text for kw in _RENAME_PLAN_KEYWORDS):
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
