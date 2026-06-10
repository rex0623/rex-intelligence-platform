"""Rename plan quality gate — validates candidates and assigns risk levels."""

from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    ValidationReport,
)

# Confidence thresholds (inclusive lower bound)
_LOW = 0.9
_MEDIUM = 0.7
_HIGH = 0.5  # below this → blocked


def _validate_candidate(
    candidate: RenameCandidate,
    seen_proposed: set,
) -> CandidateValidation:
    """Return a CandidateValidation for a single RenameCandidate."""
    issues: list[str] = []

    # ── Blocked: missing filename ──────────────────────────────────────────
    if not candidate.original_filename:
        return CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="blocked",
            issues=["缺少原始檔名"],
        )

    # ── Blocked: unknown document type ─────────────────────────────────────
    if candidate.document_type == "unknown":
        return CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="blocked",
            issues=["文件類型未知，無法產生改名建議"],
        )

    # ── Blocked: no proposed filename ──────────────────────────────────────
    if candidate.proposed_filename is None:
        issues = ["無法產生建議檔名"] + [
            w for w in candidate.warnings if w != "無法產生建議檔名"
        ]
        return CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=None,
            risk_level="blocked",
            issues=issues,
        )

    # ── Blocked: confidence too low ────────────────────────────────────────
    if candidate.confidence < _HIGH:
        issues = [f"信心度不足（{candidate.confidence:.2f}）"] + list(candidate.warnings)
        return CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="blocked",
            issues=issues,
        )

    # ── Non-critical checks ────────────────────────────────────────────────
    for w in candidate.warnings:
        issues.append(w)

    if candidate.proposed_filename == candidate.original_filename:
        issues.append("建議檔名與原始檔名相同")

    if candidate.proposed_filename in seen_proposed:
        issues.append(f"建議檔名重複：{candidate.proposed_filename}")
        return CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="high",
            issues=issues,
        )

    # ── Confidence-based risk ──────────────────────────────────────────────
    if candidate.confidence >= _LOW:
        risk = "low"
    elif candidate.confidence >= _MEDIUM:
        risk = "medium"
        issues.append(f"信心度偏低（{candidate.confidence:.2f}）")
    else:
        risk = "high"
        issues.append(f"信心度過低（{candidate.confidence:.2f}）")

    # Upgrade low → medium when proposed name equals original
    if candidate.proposed_filename == candidate.original_filename and risk == "low":
        risk = "medium"

    return CandidateValidation(
        original_filename=candidate.original_filename,
        proposed_filename=candidate.proposed_filename,
        risk_level=risk,
        issues=issues,
    )


def validate_rename_plan(plan: RenamePlan) -> ValidationReport:
    """Validate every candidate in *plan* and return a ValidationReport."""
    plan_issues: list[str] = []

    if not plan.candidates:
        plan_issues.append("改名計畫為空，沒有任何待處理檔案")
        return ValidationReport(
            total_files=plan.total_files,
            plan_issues=plan_issues,
            approval_required=True,
        )

    seen_proposed: set[str] = set()
    validated: list[CandidateValidation] = []
    low = medium = high = blocked = 0

    for candidate in plan.candidates:
        cv = _validate_candidate(candidate, seen_proposed)

        # Track proposed names for collision detection (only once per name)
        if candidate.proposed_filename and candidate.proposed_filename not in seen_proposed:
            seen_proposed.add(candidate.proposed_filename)

        validated.append(cv)

        if cv.risk_level == "low":
            low += 1
        elif cv.risk_level == "medium":
            medium += 1
        elif cv.risk_level == "high":
            high += 1
        else:
            blocked += 1

    return ValidationReport(
        total_files=plan.total_files,
        low_count=low,
        medium_count=medium,
        high_count=high,
        blocked_count=blocked,
        approval_required=True,
        plan_issues=plan_issues,
        candidates=validated,
    )
