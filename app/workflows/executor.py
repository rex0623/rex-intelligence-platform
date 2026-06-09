"""Workflow execution logic."""

from typing import Any

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
            return "dry-run completed"

        if step_name in {"批次更名", "加入浮水印"}:
            return "dry-run blocked，需要正式 approval，Phase 9 不執行"

        return "dry-run skipped，目前尚未實作"
