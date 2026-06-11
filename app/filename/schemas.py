"""Data models for filename intelligence / rename plan."""

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RenameCandidate(BaseModel):
    original_filename: str
    proposed_filename: Optional[str] = None
    confidence: float = 0.0
    document_type: str = "unknown"
    warnings: List[str] = Field(default_factory=list)


class CandidateValidation(BaseModel):
    original_filename: str
    proposed_filename: Optional[str] = None
    risk_level: str = "low"  # low | medium | high | blocked
    issues: List[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    total_files: int = 0
    low_count: int = 0
    medium_count: int = 0
    high_count: int = 0
    blocked_count: int = 0
    approval_required: bool = True
    plan_issues: List[str] = Field(default_factory=list)
    candidates: List[CandidateValidation] = Field(default_factory=list)
    validated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RenamePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = True
    status: str = "pending_approval"
    requires_approval: bool = True
    candidates: List[RenameCandidate] = Field(default_factory=list)
    total_files: int = 0
    renamed_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    validation_report: Optional[ValidationReport] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Phase 14A — Execution schemas
# ---------------------------------------------------------------------------


class RenameFileResult(BaseModel):
    original_path: str
    proposed_path: str
    status: Literal["success", "failed", "skipped", "blocked"]
    reason: Optional[str] = None
    risk_level: Optional[str] = None
    rollback_from: Optional[str] = None
    rollback_to: Optional[str] = None


class RenameExecutionResult(BaseModel):
    plan_id: str
    executed: bool
    dry_run: bool
    total: int
    success_count: int
    failed_count: int
    skipped_count: int
    blocked_count: int
    results: List[RenameFileResult]
    rollback_available: bool = False


class RenameTransactionAction(BaseModel):
    original_path: str
    new_path: str
    status: Literal["pending", "success", "failed", "rolled_back"]
    rollback_from: Optional[str] = None
    rollback_to: Optional[str] = None


class RenameTransaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actions: List[RenameTransactionAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 14D-3A — Rollback preview schemas (read-only, no execution)
# ---------------------------------------------------------------------------


class RollbackPreviewAction(BaseModel):
    original_path: str
    new_path: str
    status: str
    rollbackable: bool


class RollbackPreview(BaseModel):
    transaction_id: str
    plan_id: str
    total_actions: int = 0
    success_count: int = 0
    rolled_back_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    rollbackable_count: int = 0
    actions: List[RollbackPreviewAction] = Field(default_factory=list)

    @property
    def has_rollbackable_actions(self) -> bool:
        return self.rollbackable_count > 0

    @property
    def is_fully_rolled_back(self) -> bool:
        return self.total_actions > 0 and self.rolled_back_count == self.total_actions


# ---------------------------------------------------------------------------
# Phase 14F — Transaction log rotation / cleanup schemas
# ---------------------------------------------------------------------------


class TransactionLogPruneResult(BaseModel):
    total_before: int = 0
    total_after: int = 0
    pruned_count: int = 0
    kept_rollbackable_count: int = 0
    pruned_transaction_ids: List[str] = Field(default_factory=list)
