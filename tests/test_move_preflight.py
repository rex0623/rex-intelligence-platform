"""Phase 15C 測試：MovePlan Quality Gate / Preflight。

preflight_move_plan() 是純資料驗證：
- 不搬移檔案、不建立資料夾、不檢查真實 filesystem
- executed 永遠 False、dry_run 永遠 True
- success_count 永遠 0、rollback_available 永遠 False
"""

import inspect
from pathlib import Path

import pytest

from app.folder_intelligence import preflight_move_plan
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _candidate(
    name: str = "bill.pdf",
    original_path: str = "/inbox/bill.pdf",
    proposed_folder: str = "電費單/24581234/2026-05/",
    proposed_path: str | None = None,
    confidence: float = 1.0,
) -> MoveCandidate:
    if proposed_path is None:
        proposed_path = proposed_folder + name
    return MoveCandidate(
        original_path=original_path,
        original_filename=name,
        proposed_folder=proposed_folder,
        proposed_path=proposed_path,
        document_type="taipower_bill",
        confidence=confidence,
    )


def _make_plan(
    candidates: list[MoveCandidate],
    risk_levels: list[str],
    status: str = "approved",
) -> MovePlan:
    """建立帶有完整 MoveValidationReport 的 MovePlan。"""
    plan = MovePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)
    plan.validation_report = MoveValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
        candidates=[
            MoveCandidateValidation(
                original_filename=c.original_filename,
                proposed_folder=c.proposed_folder,
                proposed_path=c.proposed_path,
                risk_level=rl,
            )
            for c, rl in zip(candidates, risk_levels)
        ],
    )
    return plan


def _assert_invariants(result):
    """Phase 15C 不變式：永不執行。"""
    assert result.executed is False
    assert result.dry_run is True
    assert result.success_count == 0
    assert result.rollback_available is False


# ---------------------------------------------------------------------------
# 測試 1–3：plan-level gates
# ---------------------------------------------------------------------------


def test_preflight_rejects_non_approved_plan():
    plan = _make_plan([_candidate()], ["low"], status="pending_approval")

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.blocked_count == 1
    assert all(r.reason == "plan_not_approved" for r in result.results)


def test_preflight_rejects_missing_validation_report():
    plan = MovePlan(total_files=1, status="approved")
    plan.candidates = [_candidate()]
    # 刻意不設定 validation_report

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert all(r.reason == "missing_validation_report" for r in result.results)


def test_preflight_rejects_blocked_count_in_report():
    good = _candidate("good.pdf", "/inbox/good.pdf")
    bad = _candidate("bad.pdf", "/inbox/bad.pdf")
    plan = _make_plan([good, bad], ["low", "blocked"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.blocked_count == 2
    assert all(r.reason == "validation_has_blocked_candidates" for r in result.results)


# ---------------------------------------------------------------------------
# 測試 4：blocked candidate（plan gate 未觸發時的 candidate-level 檢查）
# ---------------------------------------------------------------------------


def test_preflight_blocks_blocked_candidate_at_candidate_level():
    c = _candidate()
    plan = _make_plan([c], ["blocked"])
    # 刻意讓 report 的 blocked_count 為 0，以測試 candidate-level 檢查
    plan.validation_report.blocked_count = 0

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "blocked_by_validation"


# ---------------------------------------------------------------------------
# 測試 5：high-risk candidate 跳過
# ---------------------------------------------------------------------------


def test_preflight_skips_high_risk_candidate():
    plan = _make_plan([_candidate(confidence=0.6)], ["high"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "high_risk_requires_manual_review"
    assert result.results[0].risk_level == "high"


# ---------------------------------------------------------------------------
# 測試 6 + 7：low / medium 通過 preflight 但不執行
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("risk", ["low", "medium"])
def test_preflight_passes_low_medium_without_execution(risk):
    plan = _make_plan([_candidate()], [risk])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "preflight_passed_no_execution_in_phase_15c"
    assert result.results[0].risk_level == risk


# ---------------------------------------------------------------------------
# 測試 8–10：missing original_path / proposed_folder / proposed_path
# ---------------------------------------------------------------------------


def test_preflight_fails_missing_original_path():
    c = _candidate(original_path="")
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.failed_count == 1
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "missing_original_path"


def test_preflight_fails_missing_proposed_folder():
    c = _candidate(proposed_folder="", proposed_path="電費單/x/bill.pdf")
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.failed_count == 1
    assert result.results[0].reason == "missing_proposed_folder"


def test_preflight_fails_missing_proposed_path():
    c = _candidate(proposed_path="")
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.failed_count == 1
    assert result.results[0].reason == "missing_proposed_path"


# ---------------------------------------------------------------------------
# 測試 11：proposed_path == original_path → skipped same_path
# ---------------------------------------------------------------------------


def test_preflight_skips_same_path():
    same = "電費單/24581234/2026-05/bill.pdf"
    c = _candidate(original_path=same, proposed_path=same)
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.skipped_count == 1
    assert result.results[0].reason == "same_path"


# ---------------------------------------------------------------------------
# 測試 12–16：混合候選的計數正確與不變式
# ---------------------------------------------------------------------------


def test_preflight_result_counts_are_correct():
    c_low = _candidate("low.pdf", "/inbox/low.pdf")
    c_medium = _candidate("med.pdf", "/inbox/med.pdf", confidence=0.8)
    c_high = _candidate("high.pdf", "/inbox/high.pdf", confidence=0.6)
    c_missing = _candidate("nopath.pdf", original_path="")
    plan = _make_plan(
        [c_low, c_medium, c_high, c_missing],
        ["low", "medium", "high", "low"],
    )

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.total == 4
    assert result.skipped_count == 3   # low + medium + high
    assert result.failed_count == 1    # missing path
    assert result.blocked_count == 0
    assert result.success_count == 0


def test_preflight_empty_approved_plan():
    plan = MovePlan(total_files=0, status="approved")
    plan.validation_report = MoveValidationReport(total_files=0, blocked_count=0)

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert result.total == 0
    assert result.results == []


# ---------------------------------------------------------------------------
# 測試 17 + 18：preflight 不建立資料夾、不搬移檔案
# ---------------------------------------------------------------------------


def test_preflight_does_not_create_folders_or_move_files(tmp_path):
    src = tmp_path / "bill.pdf"
    src.write_text("content")
    target_folder = str(tmp_path / "電費單" / "24581234" / "2026-05") + "/"

    c = MoveCandidate(
        original_path=str(src),
        original_filename="bill.pdf",
        proposed_folder=target_folder,
        proposed_path=target_folder + "bill.pdf",
        document_type="taipower_bill",
        confidence=1.0,
    )
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    _assert_invariants(result)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bill.pdf"], (
        "preflight 不可建立資料夾或搬移檔案"
    )
    assert src.read_text() == "content"
    assert not (tmp_path / "電費單").exists()


# ---------------------------------------------------------------------------
# 測試 19：AST 驗證 preflight module 無任何 filesystem 異動呼叫
# ---------------------------------------------------------------------------


def test_preflight_module_has_no_filesystem_calls():
    import ast

    import app.folder_intelligence.preflight as preflight_module

    forbidden_imports = {"os", "shutil", "pathlib"}
    tree = ast.parse(inspect.getsource(preflight_module))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_imports, (
                    f"preflight 不可 import {alias.name}"
                )
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_imports, (
                f"preflight 不可 from {node.module} import"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in (
                "rename", "move", "replace", "mkdir", "makedirs",
            ), f"preflight 不可呼叫 .{node.func.attr}()"
