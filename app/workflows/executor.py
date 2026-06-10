"""Workflow execution logic."""

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.document.classifier import classify_document_type
from app.document.extractor import extract_fields
from app.document.parser import parse_text
from app.document.schemas import Document
from app.workflows.base import WorkflowPlan


class WorkflowExecutor:
    """Executor for workflow dry-run simulation."""

    def execute_dry_run(self, workflow_plan: dict[str, Any] | WorkflowPlan) -> dict[str, Any]:
        # Detect RenamePlan payload (has plan_id, not workflow_id)
        if isinstance(workflow_plan, dict) and "plan_id" in workflow_plan:
            return self._execute_rename_dry_run(workflow_plan)

        if isinstance(workflow_plan, WorkflowPlan):
            plan = workflow_plan
        else:
            plan = WorkflowPlan.model_validate(workflow_plan)

        steps_report = []
        for step in plan.steps:
            result = self._dry_run_result_for_step(step.name)
            steps_report.append({"name": step.name, "result": result})

        return {
            "workflow_id": plan.workflow_id,
            "workflow_type": plan.workflow_type,
            "status": "dry_run_completed",
            "steps": steps_report,
            "note": "本次沒有修改任何 PDF",
        }

    def _execute_rename_dry_run(self, plan_dict: dict[str, Any]) -> dict[str, Any]:
        validation = plan_dict.get("validation_report") or {}
        val_by_file = {
            v["original_filename"]: v
            for v in validation.get("candidates", [])
        }

        steps_report = []
        for c in plan_dict.get("candidates", []):
            original = c.get("original_filename", "")
            proposed = c.get("proposed_filename")
            confidence = c.get("confidence", 0.0)
            warnings = c.get("warnings", [])
            val = val_by_file.get(original, {})
            risk = val.get("risk_level", "unknown")
            issues = val.get("issues", [])

            if proposed and risk not in ("blocked",):
                steps_report.append({
                    "name": original,
                    "result": (
                        f"dry-run：建議改名為 {proposed}"
                        f"（信心度 {confidence:.2f}，風險 {risk}）"
                    ),
                })
            else:
                reason = "；".join(issues) if issues else (
                    "；".join(warnings) if warnings else "無法產生建議檔名"
                )
                steps_report.append({
                    "name": original,
                    "result": f"dry-run blocked：{reason}",
                })

        risk_summary = {
            "low": validation.get("low_count", 0),
            "medium": validation.get("medium_count", 0),
            "high": validation.get("high_count", 0),
            "blocked": validation.get("blocked_count", 0),
        }

        return {
            "plan_id": plan_dict.get("plan_id", ""),
            "status": "dry_run_completed",
            "action": "rename_plan",
            "steps": steps_report,
            "risk_summary": risk_summary,
            "note": "本次沒有實際更名任何 PDF",
        }

    def _dry_run_result_for_step(self, step_name: str) -> str:
        if step_name == "掃描 PDF":
            summary = self._scan_pdf_summary()
            classification_result = (
                ", ".join(
                    [f"{k} {v}" for k, v in summary["classification_counts"].items()]
                )
                or "none"
            )
            doc_count = len(summary.get("document_objects", []))
            return (
                f"dry-run completed：PDF數量 {summary['total_pdfs']}，可讀數量 {summary['readable_pdfs']}，"
                f"分類結果 {classification_result}，Document物件 {doc_count}"
            )

        if step_name in {"批次更名", "加入浮水印"}:
            return "dry-run blocked，需要正式 approval，Phase 9 不執行"

        return "dry-run skipped，目前尚未實作"

    def _scan_pdf_summary(self) -> dict[str, Any]:
        target = Path(settings.SAFE_PDF_ROOT).expanduser().resolve()
        if not target.exists():
            return {"total_pdfs": 0, "readable_pdfs": 0, "classification_counts": {}}

        try:
            import fitz
        except ImportError:
            return {"total_pdfs": 0, "readable_pdfs": 0, "classification_counts": {}}

        pdf_files = [path for path in target.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"]
        readable = 0
        classification_counts: dict[str, int] = {}
        document_objects: list[dict[str, Any]] = []

        for path in pdf_files:
            try:
                doc = fitz.open(path)
                if not doc.is_encrypted and doc.page_count > 0:
                    raw_text = doc.load_page(0).get_text()
                    normalized = parse_text(raw_text)
                    if normalized:
                        classification = classify_document_type(normalized)
                        document = Document(
                            document_type=classification["document_type"],
                            confidence=float(classification["confidence"]),
                            fields=extract_fields(normalized),
                            text=normalized,
                            source_file=path.name,
                        )
                        readable += 1
                        pdf_type = classification["document_type"].value
                        document_objects.append(document.model_dump())
                    else:
                        pdf_type = "unknown"
                else:
                    pdf_type = "unknown"
                doc.close()
            except Exception:
                pdf_type = "unknown"

            classification_counts[pdf_type] = classification_counts.get(pdf_type, 0) + 1

        return {
            "total_pdfs": len(pdf_files),
            "readable_pdfs": readable,
            "classification_counts": classification_counts,
            "document_objects": document_objects,
        }
