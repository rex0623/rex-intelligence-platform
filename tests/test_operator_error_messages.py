"""Phase 16C 測試：錯誤 reason 中文說明（humanize_reason）與下一步提示。

只驗證輸出文字：底層 result reason、執行流程、once-only guard 行為均不變。
所有測試使用 tmp_path / monkeypatch，不污染 runtime/。
"""

from pathlib import Path

import pytest

from scripts.mock_line import humanize_reason, mock_line_payload
from app.approvals.manager import approval_manager
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    ValidationReport,
)
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    """將全域 approval_manager 隔離到 tmp_path，避免污染 runtime/approvals.json。"""
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


@pytest.fixture
def rename_log(tmp_path):
    return RenameTransactionLog(tmp_path / "logs" / "rename_tx.json")


@pytest.fixture
def move_log(tmp_path):
    return MoveTransactionLog(tmp_path / "logs" / "move_tx.json")


def _make_rename_plan(tmp_path: Path, name: str = "bill.pdf") -> RenamePlan:
    """手工 rename plan（絕對路徑，low risk，pending_approval）。"""
    src = tmp_path / "files" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("content-" + name)
    candidate = RenameCandidate(
        original_filename=str(src),
        proposed_filename=str(src.parent / ("renamed-" + name)),
        confidence=1.0,
        document_type="taipower_bill",
    )
    plan = RenamePlan(total_files=1)
    plan.candidates = [candidate]
    plan.validation_report = ValidationReport(
        total_files=1,
        low_count=1,
        candidates=[CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="low",
        )],
    )
    return plan


def _make_move_payload(tmp_path: Path, name: str = "bill.pdf") -> dict:
    """手工 move plan payload（絕對路徑，low risk，flattened 15B 格式）。"""
    src = tmp_path / "minbox" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("content-" + name)
    target = tmp_path / "電費單" / "24581234" / name
    candidate = MoveCandidate(
        original_path=str(src),
        original_filename=name,
        proposed_folder=str(target.parent) + "/",
        proposed_path=str(target),
        document_type="taipower_bill",
        confidence=1.0,
    )
    plan = MovePlan(total_files=1)
    plan.candidates = [candidate]
    plan.validation_report = MoveValidationReport(
        total_files=1,
        low_count=1,
        candidates=[MoveCandidateValidation(
            original_filename=name,
            proposed_folder=candidate.proposed_folder,
            proposed_path=candidate.proposed_path,
            risk_level="low",
        )],
    )
    payload = plan.model_dump(mode="json")
    payload["plan_type"] = "move_plan"
    return payload


# ---------------------------------------------------------------------------
# 測試 1–6：humanize_reason 中文說明（保留原始 reason code）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason, keyword",
    [
        ("approval_not_found", "找不到這筆核准資料"),
        ("already_executed", "不會重複執行"),
        ("transaction_not_found", "找不到這筆交易紀錄"),
        ("target_file_already_exists", "目標檔案已存在"),
        ("path_escapes_safe_root", "SAFE_PDF_ROOT"),
    ],
)
def test_humanize_reason_has_chinese_explanation(reason, keyword):
    output = humanize_reason(reason)
    assert output.startswith(f"{reason}："), "必須保留原始 reason code 方便 debug"
    assert keyword in output


def test_humanize_reason_unknown_code_displayed_safely():
    output = humanize_reason("totally_unknown_reason_xyz")
    assert output.startswith("totally_unknown_reason_xyz：")
    assert "未知" in output


def test_humanize_reason_covers_all_documented_reasons():
    for reason in (
        "approval_not_found",
        "approval_not_approved",
        "not_move_plan",
        "not_rename_plan",
        "already_executed",
        "transaction_not_found",
        "no_rollbackable_actions",
        "already_fully_rolled_back",
        "target_file_already_exists",
        "original_file_not_found",
        "rollback_source_not_found",
        "rollback_target_already_exists",
        "validation_has_blocked_candidates",
        "path_escapes_safe_root",
    ):
        output = humanize_reason(reason)
        assert output.startswith(f"{reason}：")
        assert "未知" not in output, f"{reason} 應有專屬中文說明"


# ---------------------------------------------------------------------------
# 測試 7–9：錯誤回覆同時帶 reason code 與中文說明（整合）
# ---------------------------------------------------------------------------


def test_confirm_rename_unknown_approval_has_reason_and_chinese(
    isolated_approvals, rename_log
):
    output = mock_line_payload("確認改名 no-such-id", transaction_log=rename_log)
    assert "找不到 approval" in output
    assert "approval_not_found" in output
    assert "找不到這筆核准資料" in output


def test_preview_rollback_unknown_transaction_has_reason_and_chinese(
    rename_log, move_log
):
    rename_out = mock_line_payload("預覽回滾改名 no-such-tx", transaction_log=rename_log)
    move_out = mock_line_payload(
        "預覽回滾搬移 no-such-tx", move_transaction_log=move_log
    )
    for output in (rename_out, move_out):
        assert "找不到 transaction" in output
        assert "transaction_not_found" in output
        assert "找不到這筆交易紀錄" in output


def test_confirm_rename_target_exists_failure_has_chinese(tmp_path, isolated_approvals):
    plan = _make_rename_plan(tmp_path)
    # 預先建立目標檔案 → target_file_already_exists
    Path(plan.candidates[0].proposed_filename).write_text("existing")
    approval = isolated_approvals.create_approval(plan.model_dump())
    isolated_approvals.approve(approval.approval_id)

    log = RenameTransactionLog(tmp_path / "tx.json")
    output = mock_line_payload(
        f"確認改名 {approval.approval_id}", transaction_log=log
    )

    assert "target_file_already_exists" in output
    assert "目標檔案已存在" in output
    assert Path(plan.candidates[0].proposed_filename).read_text() == "existing", (
        "既有目標檔案不可被覆寫"
    )


# ---------------------------------------------------------------------------
# 測試 10–13：execution 成功回覆的下一步提示
# ---------------------------------------------------------------------------


def _execute_rename(tmp_path, isolated_approvals, rename_log) -> tuple[str, str]:
    """執行一次成功的「確認改名」，回傳 (output, transaction_id)。"""
    plan = _make_rename_plan(tmp_path)
    approval = isolated_approvals.create_approval(plan.model_dump())
    isolated_approvals.approve(approval.approval_id)
    output = mock_line_payload(
        f"確認改名 {approval.approval_id}", transaction_log=rename_log
    )
    transactions = rename_log.list_transactions()
    assert len(transactions) == 1
    return output, transactions[0].transaction_id


def _execute_move(tmp_path, isolated_approvals, move_log) -> tuple[str, str]:
    """執行一次成功的「確認搬移」，回傳 (output, transaction_id)。"""
    payload = _make_move_payload(tmp_path)
    approval = isolated_approvals.create_approval(payload)
    isolated_approvals.approve(approval.approval_id)
    output = mock_line_payload(
        f"確認搬移 {approval.approval_id}", move_transaction_log=move_log
    )
    transactions = move_log.list_transactions()
    assert len(transactions) == 1
    return output, transactions[0].transaction_id


def test_confirm_rename_response_includes_preview_rollback_hint(
    tmp_path, isolated_approvals, rename_log
):
    output, tx_id = _execute_rename(tmp_path, isolated_approvals, rename_log)
    assert "已執行改名" in output
    assert f"預覽回滾改名 {tx_id}" in output
    assert "只預覽，不會動檔案" in output


def test_confirm_rename_response_includes_rollback_command_hint(
    tmp_path, isolated_approvals, rename_log
):
    output, tx_id = _execute_rename(tmp_path, isolated_approvals, rename_log)
    assert f"回滾改名 {tx_id}" in output
    assert "會真的把檔名復原" in output


def test_confirm_move_response_includes_preview_rollback_hint(
    tmp_path, isolated_approvals, move_log
):
    output, tx_id = _execute_move(tmp_path, isolated_approvals, move_log)
    assert "搬移執行結果" in output
    assert f"預覽回滾搬移 {tx_id}" in output
    assert "只預覽，不會動檔案" in output


def test_confirm_move_response_includes_rollback_command_hint(
    tmp_path, isolated_approvals, move_log
):
    output, tx_id = _execute_move(tmp_path, isolated_approvals, move_log)
    assert f"回滾搬移 {tx_id}" in output
    assert "會真的把檔案搬回原位" in output


# ---------------------------------------------------------------------------
# 測試 14–16：rollback preview / execution 回覆文字
# ---------------------------------------------------------------------------


def test_rollback_preview_responses_clearly_say_read_only(
    tmp_path, isolated_approvals, rename_log, move_log
):
    _, rename_tx = _execute_rename(tmp_path, isolated_approvals, rename_log)
    _, move_tx = _execute_move(tmp_path, isolated_approvals, move_log)

    rename_preview = mock_line_payload(
        f"預覽回滾改名 {rename_tx}", transaction_log=rename_log
    )
    assert "目前僅預覽，尚未執行回滾" in rename_preview
    assert "預覽不會修改任何檔案或 transaction log" in rename_preview
    assert f"回滾改名 {rename_tx}" in rename_preview

    move_preview = mock_line_payload(
        f"預覽回滾搬移 {move_tx}", move_transaction_log=move_log
    )
    assert "這只是預覽，尚未實際回滾任何檔案" in move_preview
    assert "預覽不會修改任何檔案或 transaction log" in move_preview
    assert f"回滾搬移 {move_tx}" in move_preview


def test_rollback_rename_success_mentions_once_only(
    tmp_path, isolated_approvals, rename_log
):
    _, tx_id = _execute_rename(tmp_path, isolated_approvals, rename_log)
    output = mock_line_payload(f"回滾改名 {tx_id}", transaction_log=rename_log)
    assert "已完成回滾改名" in output
    assert "不會重複回滾" in output

    second = mock_line_payload(f"回滾改名 {tx_id}", transaction_log=rename_log)
    assert "已完成回滾改名" not in second
    assert "already_fully_rolled_back" in second


def test_rollback_move_success_mentions_once_only(
    tmp_path, isolated_approvals, move_log
):
    _, tx_id = _execute_move(tmp_path, isolated_approvals, move_log)
    output = mock_line_payload(f"回滾搬移 {tx_id}", move_transaction_log=move_log)
    assert "已完成回滾搬移" in output
    assert "不會重複回滾" in output

    second = mock_line_payload(f"回滾搬移 {tx_id}", move_transaction_log=move_log)
    assert "已完成回滾搬移" not in second
    assert "already_fully_rolled_back" in second


# ---------------------------------------------------------------------------
# 測試 17–18：「確認 {approval_id}」回覆清楚說明不會動檔案
# ---------------------------------------------------------------------------


def test_generic_approval_for_move_plan_says_it_does_not_move_files(
    tmp_path, isolated_approvals
):
    payload = _make_move_payload(tmp_path)
    approval = isolated_approvals.create_approval(payload)

    output = mock_line_payload(f"確認 {approval.approval_id}")

    assert "搬移計畫已確認（dry-run）" in output
    assert "本次沒有實際搬移任何檔案" in output
    assert "不會搬移任何檔案" in output
    assert f"確認搬移 {approval.approval_id}" in output, (
        "核准回覆應提示明確執行指令"
    )
    assert (tmp_path / "minbox" / "bill.pdf").exists(), "「確認」不可搬移檔案"


def test_generic_approval_for_rename_plan_says_it_does_not_rename_files(
    tmp_path, isolated_approvals
):
    plan = _make_rename_plan(tmp_path)
    approval = isolated_approvals.create_approval(plan.model_dump())

    output = mock_line_payload(f"確認 {approval.approval_id}")

    assert "改名計畫已確認（dry-run）" in output
    assert "本次沒有實際更名任何 PDF" in output
    assert "不會改名任何檔案" in output
    assert f"確認改名 {approval.approval_id}" in output, (
        "核准回覆應提示明確執行指令"
    )
    assert Path(plan.candidates[0].original_filename).exists(), "「確認」不可改名檔案"


# ---------------------------------------------------------------------------
# 測試 19：plan 產生回覆清楚區分「確認」與真實執行指令
# ---------------------------------------------------------------------------


def test_move_plan_response_distinguishes_approval_from_execution(
    tmp_path, monkeypatch, isolated_approvals
):
    from app.core.config import settings

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()

    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Taiwan Power Company electric bill")
    doc.save(str(pdf_root / "bill.pdf"))
    doc.close()
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("產生搬移計畫")

    assert "只會核准並顯示 dry-run 報告，不會搬移任何檔案" in output
    assert "指令說明" in output, "plan 回覆應提示 help 指令"
    # 15B 既有不變式：move plan 產生回覆不可直接提示「確認搬移」
    assert "確認搬移" not in output
