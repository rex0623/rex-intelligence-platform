"""Approval schemas."""

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
