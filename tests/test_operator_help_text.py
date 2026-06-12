"""Phase 16C 測試：Operator help text（「說明」「指令說明」「help」「/help」）。

Help 指令為純文字回覆：不建立 approval、不讀寫 transaction log、
不改名 / 搬移任何檔案。所有測試使用 tmp_path / monkeypatch，不污染 runtime/。
"""

from pathlib import Path

import pytest

from scripts.mock_line import command_help_text, mock_line_payload
from app.approvals.manager import approval_manager
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog


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


def _snapshot(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# ---------------------------------------------------------------------------
# 測試 1–3：help 指令觸發（full match）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["說明", "指令說明", "help", "/help"])
def test_help_commands_return_command_help(text, isolated_approvals):
    output = mock_line_payload(text)
    assert output == command_help_text()
    assert "指令說明" in output


def test_help_commands_require_full_match(isolated_approvals):
    """模糊文字不觸發 help（也不可觸發任何 destructive action）。"""
    for text in ("請給我指令說明", "說明一下", "help me 回滾"):
        output = mock_line_payload(text)
        assert "一、Planning / Dry-run" not in output
    assert isolated_approvals._store == {}


# ---------------------------------------------------------------------------
# 測試 4–9：help text 涵蓋所有指令分類
# ---------------------------------------------------------------------------


def test_help_text_includes_planning_commands():
    output = command_help_text()
    for cmd in (
        "整理檔名",
        "分析 PDF 詳細",
        "整理資料夾",
        "產生搬移計畫",
        "分析 PDF 並產生搬移計畫",
        "產生資料夾歸檔計畫",
    ):
        assert cmd in output, f"help text 應列出 planning 指令：{cmd}"


def test_help_text_includes_approval_command():
    output = command_help_text()
    assert "確認 {approval_id}" in output
    assert "只核准" in output
    assert "dry-run 報告" in output
    assert "不會真實改名或搬移" in output


def test_help_text_includes_rename_execution_command():
    output = command_help_text()
    assert "確認改名 {approval_id}" in output
    assert "會真的改名檔案" in output


def test_help_text_includes_rename_rollback_commands():
    output = command_help_text()
    assert "預覽回滾改名 {transaction_id}" in output
    assert "回滾改名 {transaction_id}" in output
    assert "會真的回滾改名" in output


def test_help_text_includes_move_execution_command():
    output = command_help_text()
    assert "確認搬移 {approval_id}" in output
    assert "會真的搬移檔案" in output


def test_help_text_includes_move_rollback_commands():
    output = command_help_text()
    assert "預覽回滾搬移 {transaction_id}" in output
    assert "回滾搬移 {transaction_id}" in output
    assert "會真的回滾搬移" in output


# ---------------------------------------------------------------------------
# 測試 10–11：destructive / non-destructive 標示
# ---------------------------------------------------------------------------


def test_help_text_says_planning_and_preview_are_non_destructive():
    output = command_help_text()
    assert "不會動任何檔案" in output
    assert "只預覽，不改檔案、不改 log" in output
    assert "只預覽，不搬檔案、不改 log" in output


def test_help_text_says_execution_and_rollback_mutate_files():
    output = command_help_text()
    assert "會真的改名檔案" in output
    assert "會真的搬移檔案" in output
    assert "會真的回滾改名" in output
    assert "會真的回滾搬移" in output
    # 安全提醒：full match + 模糊文字不觸發 + 建議先 preview
    assert "完整輸入" in output
    assert "模糊文字" in output
    assert "destructive action" in output
    assert "建議先輸入預覽指令" in output


# ---------------------------------------------------------------------------
# 測試 12–14：help 指令零副作用
# ---------------------------------------------------------------------------


def test_help_command_does_not_create_approval(isolated_approvals):
    for text in ("說明", "指令說明", "help", "/help"):
        mock_line_payload(text)
    assert isolated_approvals._store == {}, "help 指令不可建立任何 approval"


def test_help_command_does_not_touch_transaction_logs(
    tmp_path, isolated_approvals, rename_log, move_log
):
    for text in ("說明", "指令說明", "help", "/help"):
        mock_line_payload(
            text, transaction_log=rename_log, move_transaction_log=move_log
        )
    assert not rename_log._log_path.exists(), "help 指令不可建立 rename transaction log"
    assert not move_log._log_path.exists(), "help 指令不可建立 move transaction log"


def test_help_command_does_not_move_or_rename_files(
    tmp_path, monkeypatch, isolated_approvals, rename_log, move_log
):
    from app.core.config import settings

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()
    (pdf_root / "bill.pdf").write_text("content")
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    before = _snapshot(pdf_root)
    for text in ("說明", "指令說明", "help", "/help"):
        mock_line_payload(
            text, transaction_log=rename_log, move_transaction_log=move_log
        )
    assert _snapshot(pdf_root) == before, "help 指令不可改名或搬移任何檔案"
    assert (pdf_root / "bill.pdf").read_text() == "content"
