"""Phase 14B 測試：Safe Rename Executor。

所有涉及真實檔案系統操作的測試，一律使用 pytest tmp_path，
不修改任何真實專案檔案。
"""

import re
from pathlib import Path

import pytest

from app.filename.executor import (
    build_rename_transaction,
    execute_rename_plan,
    rollback_rename_transaction,
)
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenameTransaction,
    RenameTransactionAction,
    RenamePlan,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助函式
# ---------------------------------------------------------------------------


def _make_plan(
    candidates: list[RenameCandidate],
    risk_levels: list[str],
    status: str = "approved",
) -> RenamePlan:
    """建立帶有完整 ValidationReport 的 RenamePlan。"""
    plan = RenamePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)

    cv_list = [
        CandidateValidation(
            original_filename=c.original_filename,
            proposed_filename=c.proposed_filename,
            risk_level=rl,
        )
        for c, rl in zip(candidates, risk_levels)
    ]
    plan.validation_report = ValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
        candidates=cv_list,
    )
    return plan


def _write_file(path: Path, content: str = "dummy") -> Path:
    """建立測試用虛擬檔案並回傳路徑。"""
    path.write_text(content)
    return path


def _low(tmp_path: Path, orig: str = "source.pdf", proposed: str = "renamed.pdf") -> RenameCandidate:
    return RenameCandidate(
        original_filename=str(tmp_path / orig),
        proposed_filename=str(tmp_path / proposed),
        confidence=1.0,
        document_type="taipower_bill",
    )


def _medium(tmp_path: Path, orig: str = "medium.pdf", proposed: str = "medium_renamed.pdf") -> RenameCandidate:
    return RenameCandidate(
        original_filename=str(tmp_path / orig),
        proposed_filename=str(tmp_path / proposed),
        confidence=0.8,
        document_type="taipower_bill",
    )


# ---------------------------------------------------------------------------
# 測試 1：非 approved 狀態，拒絕執行，不更名
# ---------------------------------------------------------------------------


def test_execute_rejects_non_approved_plan(tmp_path):
    c = _low(tmp_path)
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"], status="pending_approval")

    result = execute_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert Path(c.original_filename).exists(), "原始檔案不應被更名"
    assert not Path(c.proposed_filename).exists(), "目標檔案不應被建立"
    assert all(r.reason == "plan_not_approved" for r in result.results)


# ---------------------------------------------------------------------------
# 測試 2：缺少 validation_report，拒絕執行，不更名
# ---------------------------------------------------------------------------


def test_execute_rejects_missing_validation_report(tmp_path):
    c = _low(tmp_path)
    _write_file(Path(c.original_filename))
    plan = RenamePlan(total_files=1, status="approved")
    plan.candidates = [c]
    # 刻意不設定 validation_report

    result = execute_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert Path(c.original_filename).exists()
    assert all(r.reason == "missing_validation_report" for r in result.results)


# ---------------------------------------------------------------------------
# 測試 3：validation_report.blocked_count > 0，拒絕執行，不更名
# ---------------------------------------------------------------------------


def test_execute_rejects_plan_with_blocked_candidates(tmp_path):
    good = _low(tmp_path, "good.pdf", "good_renamed.pdf")
    bad = RenameCandidate(
        original_filename=str(tmp_path / "bad.pdf"),
        proposed_filename=None,
        confidence=0.1,
        document_type="unknown",
    )
    _write_file(Path(good.original_filename))
    plan = _make_plan([good, bad], ["low", "blocked"])

    result = execute_rename_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert Path(good.original_filename).exists(), "good 檔案不應被更名"
    assert all(r.reason == "validation_has_blocked_candidates" for r in result.results)


# ---------------------------------------------------------------------------
# 測試 4：高風險候選項，跳過，不更名
# ---------------------------------------------------------------------------


def test_execute_skips_high_risk_candidate(tmp_path):
    c = _low(tmp_path, "risky.pdf", "risky_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["high"])

    result = execute_rename_plan(plan)

    assert result.skipped_count == 1
    assert result.success_count == 0
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "high_risk_requires_manual_review"
    assert Path(c.original_filename).exists(), "高風險檔案不應被更名"


# ---------------------------------------------------------------------------
# 測試 5：proposed == original，跳過，不更名
# ---------------------------------------------------------------------------


def test_execute_skips_same_filename(tmp_path):
    same = str(tmp_path / "same.pdf")
    c = RenameCandidate(
        original_filename=same,
        proposed_filename=same,
        confidence=1.0,
        document_type="taipower_bill",
    )
    _write_file(Path(same))
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)

    assert result.skipped_count == 1
    assert result.success_count == 0
    assert result.results[0].reason == "same_filename"


# ---------------------------------------------------------------------------
# 測試 6：原始檔案不存在，狀態 failed
# ---------------------------------------------------------------------------


def test_execute_fails_when_original_file_not_found(tmp_path):
    c = _low(tmp_path, "ghost.pdf", "ghost_renamed.pdf")
    # 刻意不建立 ghost.pdf
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)

    assert result.executed is True
    assert result.failed_count == 1
    assert result.success_count == 0
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "original_file_not_found"


# ---------------------------------------------------------------------------
# 測試 7：目標檔案已存在，狀態 failed
# ---------------------------------------------------------------------------


def test_execute_fails_when_target_already_exists(tmp_path):
    c = _low(tmp_path, "orig.pdf", "target.pdf")
    _write_file(Path(c.original_filename))
    _write_file(Path(c.proposed_filename))  # 目標已存在
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)

    assert result.executed is True
    assert result.failed_count == 1
    assert result.success_count == 0
    assert result.results[0].reason == "target_file_already_exists"
    assert Path(c.original_filename).exists(), "原始檔案不應被刪除"


# ---------------------------------------------------------------------------
# 測試 8：低風險候選項，成功更名
# ---------------------------------------------------------------------------


def test_execute_renames_low_risk_candidate(tmp_path):
    c = _low(tmp_path, "bill.pdf", "台電電費單_2026-05.pdf")
    _write_file(Path(c.original_filename), "pdf content")
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)

    assert result.executed is True
    assert result.success_count == 1
    assert result.failed_count == 0
    assert result.results[0].status == "success"
    assert not Path(c.original_filename).exists(), "原始路徑應已消失"
    assert Path(c.proposed_filename).exists(), "目標路徑應已存在"


# ---------------------------------------------------------------------------
# 測試 9：中風險候選項，成功更名
# ---------------------------------------------------------------------------


def test_execute_renames_medium_risk_candidate(tmp_path):
    c = _medium(tmp_path, "medium.pdf", "medium_renamed.pdf")
    _write_file(Path(c.original_filename), "pdf content")
    plan = _make_plan([c], ["medium"])

    result = execute_rename_plan(plan)

    assert result.executed is True
    assert result.success_count == 1
    assert result.results[0].status == "success"
    assert Path(c.proposed_filename).exists()


# ---------------------------------------------------------------------------
# 測試 10：成功更名後，rollback_from / rollback_to 正確填入
# ---------------------------------------------------------------------------


def test_execute_success_includes_rollback_info(tmp_path):
    c = _low(tmp_path, "source.pdf", "dest.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)

    r = result.results[0]
    assert r.status == "success"
    assert r.rollback_from == c.proposed_filename, "rollback_from 應指向新路徑"
    assert r.rollback_to == c.original_filename, "rollback_to 應指向原始路徑"


# ---------------------------------------------------------------------------
# 測試 11：結果計數正確（混合候選項）
# ---------------------------------------------------------------------------


def test_execute_result_counts_are_correct(tmp_path):
    c_low = _low(tmp_path, "low.pdf", "low_r.pdf")
    c_medium = _medium(tmp_path, "med.pdf", "med_r.pdf")
    c_high = RenameCandidate(
        original_filename=str(tmp_path / "high.pdf"),
        proposed_filename=str(tmp_path / "high_r.pdf"),
        confidence=0.6,
        document_type="taipower_bill",
    )
    c_no_file = _low(tmp_path, "ghost.pdf", "ghost_r.pdf")

    _write_file(Path(c_low.original_filename))
    _write_file(Path(c_medium.original_filename))
    _write_file(Path(c_high.original_filename))
    # c_no_file 的原始檔故意不建立

    plan = _make_plan(
        [c_low, c_medium, c_high, c_no_file],
        ["low", "medium", "high", "low"],
    )

    result = execute_rename_plan(plan)

    assert result.total == 4
    assert result.success_count == 2      # low + medium
    assert result.skipped_count == 1      # high
    assert result.failed_count == 1       # ghost (not found)
    assert result.blocked_count == 0
    assert result.executed is True
    assert result.dry_run is False
    assert result.rollback_available is True


# ---------------------------------------------------------------------------
# 測試 12：build_rename_transaction 只包含 low/medium 候選項
# ---------------------------------------------------------------------------


def test_build_rename_transaction_includes_only_low_medium(tmp_path):
    c_low = _low(tmp_path, "a.pdf", "a_renamed.pdf")
    c_medium = _medium(tmp_path, "b.pdf", "b_renamed.pdf")
    c_high = RenameCandidate(
        original_filename=str(tmp_path / "c.pdf"),
        proposed_filename=str(tmp_path / "c_renamed.pdf"),
        confidence=0.6,
        document_type="taipower_bill",
    )
    plan = _make_plan([c_low, c_medium, c_high], ["low", "medium", "high"])

    tx = build_rename_transaction(plan)

    assert tx.plan_id == plan.plan_id
    assert tx.transaction_id != ""
    assert len(tx.actions) == 2  # low + medium only

    included_originals = {a.original_path for a in tx.actions}
    assert c_low.original_filename in included_originals
    assert c_medium.original_filename in included_originals
    assert c_high.original_filename not in included_originals

    for action in tx.actions:
        assert action.status == "pending"
        assert action.rollback_from == action.new_path
        assert action.rollback_to == action.original_path


# ---------------------------------------------------------------------------
# 測試 13：rollback 成功復原已更名的檔案
# ---------------------------------------------------------------------------


def test_rollback_successfully_reverses_rename(tmp_path):
    original = tmp_path / "original.pdf"
    renamed = tmp_path / "renamed.pdf"
    _write_file(original, "content")

    # 先執行更名
    original.rename(renamed)
    assert renamed.exists()
    assert not original.exists()

    # 建立帶有 success 狀態的 transaction
    action = RenameTransactionAction(
        original_path=str(original),
        new_path=str(renamed),
        status="success",
        rollback_from=str(renamed),
        rollback_to=str(original),
    )
    tx = RenameTransaction(plan_id="test-plan", actions=[action])

    result = rollback_rename_transaction(tx)

    assert result.executed is True
    assert result.success_count == 1
    assert result.failed_count == 0
    assert result.rollback_available is False
    assert original.exists(), "rollback 後原始檔案應恢復"
    assert not renamed.exists(), "rollback 後更名後的檔案應消失"


# ---------------------------------------------------------------------------
# 測試 14：rollback 來源不存在時回報 failed
# ---------------------------------------------------------------------------


def test_rollback_fails_when_source_not_found(tmp_path):
    action = RenameTransactionAction(
        original_path=str(tmp_path / "orig.pdf"),
        new_path=str(tmp_path / "gone.pdf"),
        status="success",
        rollback_from=str(tmp_path / "gone.pdf"),  # 不存在
        rollback_to=str(tmp_path / "orig.pdf"),
    )
    tx = RenameTransaction(plan_id="test-plan", actions=[action])

    result = rollback_rename_transaction(tx)

    assert result.executed is True
    assert result.failed_count == 1
    assert result.success_count == 0
    assert result.results[0].reason == "rollback_source_not_found"


# ---------------------------------------------------------------------------
# 測試 15：rollback 目標已存在時回報 failed
# ---------------------------------------------------------------------------


def test_rollback_fails_when_target_already_exists(tmp_path):
    existing_src = tmp_path / "renamed.pdf"
    existing_dst = tmp_path / "original.pdf"
    _write_file(existing_src)
    _write_file(existing_dst)  # 目標已存在

    action = RenameTransactionAction(
        original_path=str(existing_dst),
        new_path=str(existing_src),
        status="success",
        rollback_from=str(existing_src),
        rollback_to=str(existing_dst),
    )
    tx = RenameTransaction(plan_id="test-plan", actions=[action])

    result = rollback_rename_transaction(tx)

    assert result.executed is True
    assert result.failed_count == 1
    assert result.success_count == 0
    assert result.results[0].reason == "rollback_target_already_exists"


# ---------------------------------------------------------------------------
# 測試 16 + 17：執行完整測試套件確認既有測試不受影響
# （透過 pytest 執行即可驗證，此處額外做 import 健全性確認）
# ---------------------------------------------------------------------------


def test_preflight_module_still_importable():
    from app.filename.preflight import preflight_rename_plan
    from app.filename.schemas import RenamePlan
    plan = RenamePlan(total_files=0, status="pending_approval")
    result = preflight_rename_plan(plan)
    assert result.executed is False
    assert result.dry_run is True


# ---------------------------------------------------------------------------
# 測試 18：Mock LINE 通用改名計畫指令，不觸發真實更名
# ---------------------------------------------------------------------------


def test_mock_line_rename_keywords_do_not_trigger_actual_rename(tmp_path, monkeypatch):
    """「產生改名計畫」、「整理檔名」等指令，輸出必須包含 dry-run，且不實際更名。"""
    from app.core.config import settings
    from scripts.mock_line import mock_line_payload

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()

    # 建立一個假的 PDF 讓計畫不為空
    import fitz
    pdf_path = pdf_root / "bill.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Taiwan Power Company electric bill amount due 1000")
    doc.save(str(pdf_path))
    doc.close()

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    for keyword in ["產生改名計畫", "整理檔名", "分析 PDF 並產生改名計畫"]:
        output = mock_line_payload(keyword)
        assert "dry-run" in output or "dry_run" in output, (
            f"關鍵字「{keyword}」的輸出應包含 dry-run 標示，實際輸出：\n{output}"
        )
        # 原始 PDF 不應被更名或刪除
        assert pdf_path.exists(), (
            f"關鍵字「{keyword}」不應刪除或更名原始 PDF"
        )
        # pdf_root 內不應出現新的更名後 PDF
        files_after = set(pdf_root.glob("*.pdf"))
        assert pdf_path in files_after, "原始 PDF 應仍存在於 inbox"
        # 確認沒有其他 PDF 被建立（若有就是真的更名了）
        assert len(files_after) == 1, (
            f"關鍵字「{keyword}」不應建立新 PDF，目前有 {files_after}"
        )


# ---------------------------------------------------------------------------
# 額外：rollback 只作用於 status == "success" 的 action
# ---------------------------------------------------------------------------


def test_rollback_ignores_non_success_actions(tmp_path):
    pending_action = RenameTransactionAction(
        original_path=str(tmp_path / "a.pdf"),
        new_path=str(tmp_path / "b.pdf"),
        status="pending",
        rollback_from=str(tmp_path / "b.pdf"),
        rollback_to=str(tmp_path / "a.pdf"),
    )
    failed_action = RenameTransactionAction(
        original_path=str(tmp_path / "c.pdf"),
        new_path=str(tmp_path / "d.pdf"),
        status="failed",
        rollback_from=str(tmp_path / "d.pdf"),
        rollback_to=str(tmp_path / "c.pdf"),
    )
    tx = RenameTransaction(plan_id="test", actions=[pending_action, failed_action])

    result = rollback_rename_transaction(tx)

    assert result.executed is False
    assert result.total == 0
    assert result.success_count == 0
    assert result.failed_count == 0


# ---------------------------------------------------------------------------
# 額外：execute_rename_plan 對空計畫回傳正確結構
# ---------------------------------------------------------------------------


def test_execute_empty_approved_plan():
    plan = RenamePlan(total_files=0, status="approved")
    plan.validation_report = ValidationReport(
        total_files=0,
        blocked_count=0,
    )

    result = execute_rename_plan(plan)

    assert result.executed is False
    assert result.dry_run is False
    assert result.total == 0
    assert result.success_count == 0
    assert result.rollback_available is False
