"""Move plan quality gate — validates candidates and assigns risk levels.

Pure data validation: never touches the real filesystem.
"""

from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)
from app.folder_intelligence.template import UNKNOWN_BUSINESS, UNKNOWN_PERIOD

# Confidence thresholds (inclusive lower bound)
_LOW = 0.9
_MEDIUM = 0.7


def _validate_candidate(
    candidate: MoveCandidate,
    seen_proposed_paths: set,
) -> MoveCandidateValidation:
    """Return a MoveCandidateValidation for a single MoveCandidate."""
    issues: list[str] = []

    def _result(risk: str, extra_issues: list[str]) -> MoveCandidateValidation:
        return MoveCandidateValidation(
            original_filename=candidate.original_filename,
            proposed_folder=candidate.proposed_folder,
            proposed_path=candidate.proposed_path,
            risk_level=risk,
            issues=extra_issues,
        )

    # ── Blocked ──────────────────────────────────────────────────────────────
    if not candidate.original_path:
        return _result("blocked", ["缺少原始路徑"])

    if candidate.document_type == "unknown":
        return _result("blocked", ["文件類型未知，無法產生歸檔建議"])

    if not candidate.proposed_folder:
        return _result("blocked", ["缺少建議資料夾"])

    if not candidate.proposed_path:
        return _result("blocked", ["缺少建議目標路徑"])

    # ── High ─────────────────────────────────────────────────────────────────
    issues.extend(candidate.warnings)

    fallback_segments = [
        seg for seg in (UNKNOWN_BUSINESS, UNKNOWN_PERIOD)
        if seg in candidate.proposed_folder
    ]
    if fallback_segments:
        issues.append(f"建議資料夾含 fallback segment：{'、'.join(fallback_segments)}")
        return _result("high", issues)

    if candidate.proposed_path in seen_proposed_paths:
        issues.append(f"建議目標路徑重複：{candidate.proposed_path}")
        return _result("high", issues)

    if candidate.confidence < _MEDIUM:
        issues.append(f"信心度不足（{candidate.confidence:.2f}）")
        return _result("high", issues)

    # ── Medium ───────────────────────────────────────────────────────────────
    if candidate.proposed_path == candidate.original_path:
        issues.append("建議目標路徑與原始路徑相同")
        return _result("medium", issues)

    if candidate.confidence < _LOW:
        issues.append(f"信心度偏低（{candidate.confidence:.2f}）")
        return _result("medium", issues)

    # ── Low ──────────────────────────────────────────────────────────────────
    return _result("low", issues)


def validate_move_plan(plan: MovePlan) -> MoveValidationReport:
    """Validate every candidate in *plan* and return a MoveValidationReport."""
    plan_issues: list[str] = []

    if not plan.candidates:
        plan_issues.append("搬移計畫為空，沒有任何待處理檔案")
        return MoveValidationReport(
            total_files=plan.total_files,
            blocked_count=0,
            approval_required=True,
            plan_issues=plan_issues,
        )

    seen_proposed_paths: set[str] = set()
    validated: list[MoveCandidateValidation] = []
    low = medium = high = blocked = 0

    for candidate in plan.candidates:
        cv = _validate_candidate(candidate, seen_proposed_paths)

        if candidate.proposed_path and candidate.proposed_path not in seen_proposed_paths:
            seen_proposed_paths.add(candidate.proposed_path)

        validated.append(cv)

        if cv.risk_level == "low":
            low += 1
        elif cv.risk_level == "medium":
            medium += 1
        elif cv.risk_level == "high":
            high += 1
        else:
            blocked += 1

    return MoveValidationReport(
        total_files=plan.total_files,
        low_count=low,
        medium_count=medium,
        high_count=high,
        blocked_count=blocked,
        approval_required=True,
        plan_issues=plan_issues,
        candidates=validated,
    )
