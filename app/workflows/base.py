"""Workflow base schemas."""

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = ""
    worker: Optional[str] = None
    status: str = "pending"  # pending / skipped / completed / failed
    requires_approval: bool = False


class WorkflowPlan(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str
    title: str
    summary: Optional[str] = ""
    steps: List[WorkflowStep] = Field(default_factory=list)
    status: str = "draft"  # draft / waiting_approval / approved / completed / failed
    dry_run: bool = True
