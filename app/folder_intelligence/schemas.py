"""Data models for folder intelligence / move plan (Phase 15A).

Planning-only schemas: MovePlan is dry_run=True and requires approval by
default.  No executor consumes these models yet.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MoveCandidate(BaseModel):
    original_path: str
    original_filename: str
    proposed_folder: str
    proposed_path: str
    document_type: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    extracted_fields: dict = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    requires_approval: bool = True


class MoveCandidateValidation(BaseModel):
    original_filename: str
    proposed_folder: str
    proposed_path: str
    risk_level: Literal["low", "medium", "high", "blocked"] = "low"
    issues: List[str] = Field(default_factory=list)


class MoveValidationReport(BaseModel):
    total_files: int = 0
    low_count: int = 0
    medium_count: int = 0
    high_count: int = 0
    blocked_count: int = 0
    approval_required: bool = True
    plan_issues: List[str] = Field(default_factory=list)
    candidates: List[MoveCandidateValidation] = Field(default_factory=list)
    validated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Phase 15C — Move execution schemas（目前僅供 read-only preflight 使用；
# 本階段沒有 move executor，executed 永遠 False、success_count 永遠 0）
# ---------------------------------------------------------------------------


class MoveFileResult(BaseModel):
    original_path: str
    proposed_path: str
    proposed_folder: str = ""
    status: Literal["success", "failed", "skipped", "blocked"]
    reason: Optional[str] = None
    risk_level: Optional[str] = None
    rollback_from: Optional[str] = None
    rollback_to: Optional[str] = None


class MoveExecutionResult(BaseModel):
    plan_id: str
    executed: bool
    dry_run: bool
    total: int
    success_count: int
    failed_count: int
    skipped_count: int
    blocked_count: int
    results: List[MoveFileResult]
    rollback_available: bool = False


# ---------------------------------------------------------------------------
# Phase 15E — Move transaction schemas（持久化每次真實搬移的 rollback 資訊；
# rollback_from = 搬移後的新位置、rollback_to = 搬移前的原位置）
# ---------------------------------------------------------------------------


class MoveTransactionAction(BaseModel):
    original_path: str
    new_path: str
    status: Literal["pending", "success", "failed", "rolled_back"]
    rollback_from: Optional[str] = None
    rollback_to: Optional[str] = None


class MoveTransaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actions: List[MoveTransactionAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 15H — Move rollback preview schemas（read-only，無任何執行行為）
# ---------------------------------------------------------------------------


class MoveRollbackPreviewAction(BaseModel):
    original_path: str
    new_path: str
    rollback_from: Optional[str] = None
    rollback_to: Optional[str] = None
    status: str
    rollbackable: bool
    reason: Optional[str] = None


class MoveRollbackPreview(BaseModel):
    transaction_id: str
    total: int = 0
    rollbackable_count: int = 0
    already_rolled_back_count: int = 0
    failed_count: int = 0
    actions: List[MoveRollbackPreviewAction] = Field(default_factory=list)

    @property
    def has_rollbackable_actions(self) -> bool:
        return self.rollbackable_count > 0

    @property
    def is_fully_rolled_back(self) -> bool:
        return self.total > 0 and self.already_rolled_back_count == self.total


class MovePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = True
    status: str = "pending_approval"
    requires_approval: bool = True
    candidates: List[MoveCandidate] = Field(default_factory=list)
    total_files: int = 0
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    validation_report: Optional[MoveValidationReport] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
