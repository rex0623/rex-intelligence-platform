"""Tests for Phase 14A: Safe Rename Executor Schemas & Preflight."""

import os

import pytest

from app.filename.preflight import preflight_rename_plan
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenameExecutionResult,
    RenameFileResult,
    RenameTransaction,
    RenameTransactionAction,
    RenamePlan,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approved_plan(candidates: list[RenameCandidate], risk_levels: list[str] | None = None) -> RenamePlan:
    """Build an approved RenamePlan with a matching ValidationReport."""
    plan = RenamePlan(total_files=len(candidates), status="approved")
    plan.candidates = list(candidates)

    if risk_levels is None:
        risk_levels = ["low"] * len(candidates)

    cv_list = [
        CandidateValidation(
            original_filename=c.original_filename,
            proposed_filename=c.proposed_filename,
            risk_level=rl,
        )
        for c, rl in zip(candidates, risk_levels)
    ]
    low = sum(1 for r in risk_levels if r == "low")
    medium = sum(1 for r in risk_levels if r == "medium")
    high = sum(1 for r in risk_levels if r == "high")
    blocked = sum(1 for r in risk_levels if r == "blocked")

    plan.validation_report = ValidationReport(
        total_files=len(candidates),
        low_count=low,
        medium_count=medium,
        high_count=high,
        blocked_count=blocked,
        candidates=cv_list,
    )
    return plan


def _low_candidate(orig: str = "bill.pdf", proposed: str = "renamed.pdf") -> RenameCandidate:
    return RenameCandidate(
        original_filename=orig,
        proposed_filename=proposed,
        confidence=1.0,
        document_type="taipower_bill",
    )


# ---------------------------------------------------------------------------
# Schema smoke tests
# ---------------------------------------------------------------------------


def test_rename_file_result_schema():
    r = RenameFileResult(
        original_path="a.pdf",
        proposed_path="b.pdf",
        status="skipped",
        reason="preflight_passed_no_execution_in_phase_14a",
        risk_level="low",
    )
    assert r.status == "skipped"
    assert r.rollback_from is None
    assert r.rollback_to is None


def test_rename_execution_result_schema():
    result = RenameExecutionResult(
        plan_id="test-plan",
        executed=False,
        dry_run=True,
        total=1,
        success_count=0,
        failed_count=0,
        skipped_count=1,
        blocked_count=0,
        results=[],
        rollback_available=False,
    )
    assert result.rollback_available is False
    assert result.executed is False


def test_rename_transaction_action_schema():
    action = RenameTransactionAction(
        original_path="old.pdf",
        new_path="new.pdf",
        status="pending",
    )
    assert action.status == "pending"
    assert action.rollback_from is None


def test_rename_transaction_schema():
    tx = RenameTransaction(plan_id="p1")
    assert tx.plan_id == "p1"
    assert tx.actions == []
    assert tx.transaction_id != ""


# ---------------------------------------------------------------------------
# 1. Preflight rejects non-approved plan
# ---------------------------------------------------------------------------


def test_preflight_rejects_non_approved_plan():
    plan = RenamePlan(total_files=1, status="pending_approval")
    plan.candidates = [_low_candidate()]
    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is True
    assert result.rollback_available is False
    assert result.success_count == 0
    assert all(r.reason == "plan_not_approved" for r in result.results)
    assert result.blocked_count == 1


# ---------------------------------------------------------------------------
# 2. Preflight rejects missing validation_report
# ---------------------------------------------------------------------------


def test_preflight_rejects_missing_validation_report():
    plan = RenamePlan(total_files=1, status="approved")
    plan.candidates = [_low_candidate()]
    # Intentionally leave validation_report as None

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert all(r.reason == "missing_validation_report" for r in result.results)
    assert result.blocked_count == 1


# ---------------------------------------------------------------------------
# 3. Preflight rejects plan with blocked_count > 0
# ---------------------------------------------------------------------------


def test_preflight_rejects_plan_with_blocked_candidates():
    candidates = [
        _low_candidate("good.pdf", "good_renamed.pdf"),
        RenameCandidate(
            original_filename="bad.pdf",
            proposed_filename=None,
            confidence=0.1,
            document_type="unknown",
        ),
    ]
    plan = _approved_plan(candidates, risk_levels=["low", "blocked"])
    # Force blocked_count to reflect reality
    plan.validation_report.blocked_count = 1

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert all(r.reason == "validation_has_blocked_candidates" for r in result.results)


# ---------------------------------------------------------------------------
# 4. Preflight skips high-risk candidates
# ---------------------------------------------------------------------------


def test_preflight_skips_high_risk_candidate():
    c = RenameCandidate(
        original_filename="risky.pdf",
        proposed_filename="renamed_risky.pdf",
        confidence=0.6,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["high"])

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "high_risk_requires_manual_review"


# ---------------------------------------------------------------------------
# 5. Preflight passes low-risk candidate without executing
# ---------------------------------------------------------------------------


def test_preflight_passes_low_risk_candidate_without_executing():
    c = _low_candidate("invoice.pdf", "台電電費單_2026-05.pdf")
    plan = _approved_plan([c], risk_levels=["low"])

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is True
    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "preflight_passed_no_execution_in_phase_14a"
    assert result.results[0].risk_level == "low"


# ---------------------------------------------------------------------------
# 6. Preflight handles same filename
# ---------------------------------------------------------------------------


def test_preflight_handles_same_filename():
    c = RenameCandidate(
        original_filename="same.pdf",
        proposed_filename="same.pdf",
        confidence=1.0,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["medium"])

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    file_result = result.results[0]
    assert file_result.status == "skipped"
    assert file_result.reason == "same_filename"


# ---------------------------------------------------------------------------
# 7. Preflight handles missing original path
# ---------------------------------------------------------------------------


def test_preflight_handles_missing_original_path():
    c = RenameCandidate(
        original_filename="",
        proposed_filename="proposed.pdf",
        confidence=0.9,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["low"])

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "missing_original_path"


# ---------------------------------------------------------------------------
# 8. Preflight handles missing proposed filename
# ---------------------------------------------------------------------------


def test_preflight_handles_missing_proposed_filename():
    c = RenameCandidate(
        original_filename="unknown.pdf",
        proposed_filename=None,
        confidence=0.9,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["medium"])

    result = preflight_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "missing_proposed_path"


# ---------------------------------------------------------------------------
# 9. Execution result counts are correct (mixed candidates)
# ---------------------------------------------------------------------------


def test_execution_result_counts_are_correct():
    candidates = [
        _low_candidate("low.pdf", "low_renamed.pdf"),
        RenameCandidate(
            original_filename="medium.pdf",
            proposed_filename="medium_renamed.pdf",
            confidence=0.8,
            document_type="taipower_bill",
        ),
        RenameCandidate(
            original_filename="high.pdf",
            proposed_filename="high_renamed.pdf",
            confidence=0.6,
            document_type="taipower_bill",
        ),
        RenameCandidate(
            original_filename="same.pdf",
            proposed_filename="same.pdf",
            confidence=1.0,
            document_type="taipower_bill",
        ),
        RenameCandidate(
            original_filename="",
            proposed_filename="something.pdf",
            confidence=0.9,
            document_type="taipower_bill",
        ),
    ]
    plan = _approved_plan(candidates, risk_levels=["low", "medium", "high", "low", "low"])

    result = preflight_rename_plan(plan)

    assert result.total == 5
    assert result.success_count == 0
    assert result.executed is False
    assert result.dry_run is True
    assert result.rollback_available is False

    statuses = [r.status for r in result.results]
    assert statuses.count("failed") == 1   # missing original_path
    assert statuses.count("skipped") == 4  # low, medium, high, same


# ---------------------------------------------------------------------------
# 10. No real filesystem mutation
# ---------------------------------------------------------------------------


def test_no_real_filesystem_mutation(tmp_path):
    """preflight_rename_plan must never create, rename, or delete files."""
    orig_file = tmp_path / "bill.pdf"
    orig_file.write_text("dummy pdf content")
    proposed = tmp_path / "台電電費單_2026-05.pdf"

    c = RenameCandidate(
        original_filename=str(orig_file),
        proposed_filename=str(proposed),
        confidence=1.0,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["low"])

    before_files = set(os.listdir(tmp_path))
    preflight_rename_plan(plan)
    after_files = set(os.listdir(tmp_path))

    assert before_files == after_files, "preflight must not mutate the filesystem"
    assert orig_file.exists(), "original file must still exist after preflight"
    assert not proposed.exists(), "proposed file must not be created by preflight"


# ---------------------------------------------------------------------------
# 11. Medium-risk candidate is skipped (preflight passed, not executed)
# ---------------------------------------------------------------------------


def test_preflight_medium_risk_skipped():
    c = RenameCandidate(
        original_filename="medium.pdf",
        proposed_filename="medium_renamed.pdf",
        confidence=0.75,
        document_type="taipower_bill",
    )
    plan = _approved_plan([c], risk_levels=["medium"])

    result = preflight_rename_plan(plan)

    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "preflight_passed_no_execution_in_phase_14a"
    assert result.results[0].risk_level == "medium"
    assert result.success_count == 0


# ---------------------------------------------------------------------------
# 12. Always-False guarantees across multiple plan types
# ---------------------------------------------------------------------------


def test_always_executed_false_and_dry_run_true():
    for status in ("pending_approval", "approved", "rejected", "cancelled"):
        plan = RenamePlan(total_files=0, status=status)
        result = preflight_rename_plan(plan)
        assert result.executed is False
        assert result.dry_run is True
        assert result.rollback_available is False
        assert result.success_count == 0
