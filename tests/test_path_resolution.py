"""Phase 16B 測試：SAFE_PDF_ROOT path anchoring（resolve_under_safe_root）。

- 絕對路徑原樣回傳（既有語意不變）
- 相對路徑錨定 SAFE_PDF_ROOT（純字串正規化，不碰 filesystem）
- path traversal（逃出 safe root）→ ValueError；executor 層 fail-safe
  以 failed reason "path_escapes_safe_root" 處理，不操作任何檔案
- rename / move 的 execute 與 rollback 均可在相對路徑下運作，無需 chdir
"""

from pathlib import Path

import pytest

from app.core.config import resolve_under_safe_root, settings
from app.filename.executor import execute_rename_plan, rollback_rename_transaction
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    RenameTransaction,
    RenameTransactionAction,
    ValidationReport,
)
from app.folder_intelligence.executor import (
    execute_move_plan,
    rollback_move_transaction,
)
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveTransaction,
    MoveTransactionAction,
    MoveValidationReport,
)


@pytest.fixture
def safe_root(tmp_path, monkeypatch):
    root = tmp_path / "safe_root"
    root.mkdir()
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(root))
    return root


def _rename_plan(original: str, proposed: str, risk: str = "low") -> RenamePlan:
    plan = RenamePlan(total_files=1, status="approved")
    plan.candidates = [RenameCandidate(
        original_filename=original,
        proposed_filename=proposed,
        confidence=1.0,
        document_type="taipower_bill",
    )]
    plan.validation_report = ValidationReport(
        total_files=1,
        low_count=1,
        candidates=[CandidateValidation(
            original_filename=original, proposed_filename=proposed, risk_level=risk,
        )],
    )
    return plan


def _move_plan(original: str, proposed: str) -> MovePlan:
    plan = MovePlan(total_files=1, status="approved")
    plan.candidates = [MoveCandidate(
        original_path=original,
        original_filename=Path(original).name,
        proposed_folder=str(Path(proposed).parent) + "/",
        proposed_path=proposed,
        document_type="taipower_bill",
        confidence=1.0,
    )]
    plan.validation_report = MoveValidationReport(
        total_files=1,
        low_count=1,
        candidates=[MoveCandidateValidation(
            original_filename=Path(original).name,
            proposed_folder=str(Path(proposed).parent) + "/",
            proposed_path=proposed,
            risk_level="low",
        )],
    )
    return plan


# ---------------------------------------------------------------------------
# 測試 11–12 + 17：resolve_under_safe_root 基本語意
# ---------------------------------------------------------------------------


def test_absolute_path_returned_unchanged(tmp_path, safe_root):
    p = tmp_path / "elsewhere" / "f.pdf"

    assert resolve_under_safe_root(str(p)) == p
    assert resolve_under_safe_root(p).is_absolute()


def test_relative_path_anchored_to_safe_root(safe_root):
    assert resolve_under_safe_root("bill.pdf") == safe_root / "bill.pdf"
    assert (
        resolve_under_safe_root("電費單/2025-03/bill.pdf")
        == safe_root / "電費單" / "2025-03" / "bill.pdf"
    )


def test_relative_resolution_does_not_touch_filesystem(safe_root):
    """不存在的檔案不會 throw，也不會建立任何東西。"""
    resolved = resolve_under_safe_root("no/such/file.pdf")

    assert resolved == safe_root / "no" / "such" / "file.pdf"
    assert not (safe_root / "no").exists()


def test_explicit_root_overrides_settings(tmp_path, safe_root):
    other = tmp_path / "other_root"

    assert resolve_under_safe_root("f.pdf", root=other) == other / "f.pdf"


def test_path_traversal_is_blocked(safe_root):
    """相對路徑逃出 safe root → ValueError（documented behavior）。"""
    for evil in ("../escape.pdf", "a/../../escape.pdf", "../../etc/passwd"):
        with pytest.raises(ValueError, match="path_escapes_safe_root"):
            resolve_under_safe_root(evil)


def test_internal_dotdot_within_root_is_allowed(safe_root):
    """未逃出 root 的 .. 正規化後允許。"""
    assert resolve_under_safe_root("a/b/../c.pdf") == safe_root / "a" / "c.pdf"


# ---------------------------------------------------------------------------
# 測試 13–14：executor 以相對路徑運作（無需 chdir）
# ---------------------------------------------------------------------------


def test_rename_executor_anchors_relative_paths_without_chdir(safe_root):
    (safe_root / "bill.pdf").write_text("content")
    plan = _rename_plan("bill.pdf", "renamed.pdf")

    result = execute_rename_plan(plan)

    assert result.success_count == 1
    assert (safe_root / "renamed.pdf").exists()
    assert not (safe_root / "bill.pdf").exists()


def test_move_executor_anchors_relative_paths_without_chdir(safe_root):
    (safe_root / "bill.pdf").write_text("content")
    plan = _move_plan("bill.pdf", "電費單/2025-03/bill.pdf")

    result = execute_move_plan(plan)

    assert result.success_count == 1
    assert (safe_root / "電費單" / "2025-03" / "bill.pdf").exists()
    assert not (safe_root / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 15–16：rollback 以相對路徑運作（無需 chdir）
# ---------------------------------------------------------------------------


def test_rename_rollback_anchors_relative_paths_without_chdir(safe_root):
    (safe_root / "renamed.pdf").write_text("content")
    tx = RenameTransaction(plan_id="p", actions=[RenameTransactionAction(
        original_path="bill.pdf", new_path="renamed.pdf",
        status="success", rollback_from="renamed.pdf", rollback_to="bill.pdf",
    )])

    result = rollback_rename_transaction(tx)

    assert result.success_count == 1
    assert (safe_root / "bill.pdf").exists()
    assert not (safe_root / "renamed.pdf").exists()


def test_move_rollback_anchors_relative_paths_without_chdir(safe_root):
    moved = safe_root / "電費單" / "bill.pdf"
    moved.parent.mkdir(parents=True)
    moved.write_text("content")
    tx = MoveTransaction(plan_id="p", actions=[MoveTransactionAction(
        original_path="inbox/bill.pdf", new_path="電費單/bill.pdf",
        status="success",
        rollback_from="電費單/bill.pdf", rollback_to="inbox/bill.pdf",
    )])

    result = rollback_move_transaction(tx)

    assert result.success_count == 1
    assert (safe_root / "inbox" / "bill.pdf").exists()
    assert not moved.exists()


# ---------------------------------------------------------------------------
# 測試 17（executor 層）：traversal fail-safe，不動任何檔案
# ---------------------------------------------------------------------------


def test_rename_executor_fails_safe_on_traversal(tmp_path, safe_root):
    outside = tmp_path / "outside.pdf"
    outside.write_text("outside")
    plan = _rename_plan("../outside.pdf", "../stolen.pdf")

    result = execute_rename_plan(plan)

    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].reason == "path_escapes_safe_root"
    assert outside.exists() and not (tmp_path / "stolen.pdf").exists()


def test_move_executor_fails_safe_on_traversal(tmp_path, safe_root):
    outside = tmp_path / "outside.pdf"
    outside.write_text("outside")
    plan = _move_plan("../outside.pdf", "../moved/outside.pdf")

    result = execute_move_plan(plan)

    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].reason == "path_escapes_safe_root"
    assert outside.exists() and not (tmp_path / "moved").exists()


def test_move_rollback_fails_safe_on_traversal(safe_root):
    tx = MoveTransaction(plan_id="p", actions=[MoveTransactionAction(
        original_path="../x.pdf", new_path="../y.pdf",
        status="success", rollback_from="../y.pdf", rollback_to="../x.pdf",
    )])

    result = rollback_move_transaction(tx)

    assert result.success_count == 0
    assert result.failed_count == 1
    assert result.results[0].reason == "path_escapes_safe_root"


def test_absolute_paths_still_work_as_before(tmp_path, safe_root):
    """絕對路徑（既有測試 / 呼叫端的主要用法）行為完全不變。"""
    src = tmp_path / "abs" / "bill.pdf"
    src.parent.mkdir()
    src.write_text("content")
    target = tmp_path / "abs" / "renamed.pdf"
    plan = _rename_plan(str(src), str(target))

    result = execute_rename_plan(plan)

    assert result.success_count == 1
    assert target.exists()
