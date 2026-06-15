"""Approval schemas."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Approval(BaseModel):
    approval_id: str = Field(...)
    workflow_id: str
    status: str = "pending"  # pending | approved | rejected | expired
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    payload: Optional[dict] = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class ApprovalPruneResult:
    """Result of ApprovalManager.prune_approvals() (Phase 21B)."""

    dry_run: bool
    total_before: int
    total_after: int
    pruned_count: int
    retained_count: int
    pruned_expired: int
    pruned_executed: int
    pruned_rejected: int
    pruned_old: int
    pruned_approval_ids: list = field(default_factory=list)
