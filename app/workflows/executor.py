"""Workflow execution logic."""

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.workflows.base import WorkflowPlan


class WorkflowExecutor:
    """Executor for workflow dry-run simulation."""

    def execute_dry_run(self, workflow_plan: dict[str, Any] | WorkflowPlan) -> dict[str, Any]:
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

    def _dry_run_result_for_step(self, step_name: str) -> str:
        if step_name == "掃描 PDF":
            summary = self._scan_pdf_summary()
            classification_result = (
                ", ".join(
                    [f"{k} {v}" for k, v in summary["classification_counts"].items()]
                )
                or "none"
            )
            return (
                f"dry-run completed：PDF數量 {summary['total_pdfs']}，可讀數量 {summary['readable_pdfs']}，"
                f"分類結果 {classification_result}"
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

        def classify(text: str) -> str:
            normalized = text.lower()
            if "台灣電力公司" in normalized or "電費通知單" in normalized:
                return "taipower_bill"
            if "發票" in normalized:
                return "invoice"
            if "契約" in normalized:
                return "contract"
            return "unknown"

        for path in pdf_files:
            try:
                doc = fitz.open(path)
                if not doc.is_encrypted and doc.page_count > 0:
                    text = doc.load_page(0).get_text()
                    if text:
                        readable += 1
                        pdf_type = classify(text)
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
        }
