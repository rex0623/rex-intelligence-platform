"""Folder Intelligence — move plan generation (Phase 15A).

Planning only: this package never touches the real filesystem.
There is no move executor; MovePlan is dry-run and requires approval.
"""

from app.folder_intelligence.formatter import format_move_plan_for_cli
from app.folder_intelligence.planner import build_move_plan
from app.folder_intelligence.preflight import preflight_move_plan
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MoveExecutionResult,
    MoveFileResult,
    MovePlan,
    MoveValidationReport,
)
from app.folder_intelligence.validator import validate_move_plan

__all__ = [
    "MoveCandidate",
    "MoveCandidateValidation",
    "MoveExecutionResult",
    "MoveFileResult",
    "MovePlan",
    "MoveValidationReport",
    "build_move_plan",
    "validate_move_plan",
    "format_move_plan_for_cli",
    "preflight_move_plan",
]
