"""Workflow engine implementation."""

from typing import Optional

from app.workflows.base import WorkflowPlan
from app.workflows.registry import get as registry_get
from app.core.logger import get_logger

logger = get_logger(__name__)


class WorkflowEngine:
    """Simple workflow engine for creating plans (dry-run)."""

    def create_workflow(self, workflow_type: str, title: str, summary: Optional[str] = "", dry_run: bool = True) -> WorkflowPlan:
        factory = registry_get(workflow_type)
        if factory is None:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        plan = factory(title=title, summary=summary)
        plan.dry_run = dry_run
        plan.status = "waiting_approval" if dry_run else "draft"

        logger.info("Created workflow plan", extra={"workflow_id": plan.workflow_id, "type": workflow_type})

        return plan
