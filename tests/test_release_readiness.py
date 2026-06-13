"""Phase 16E 測試：Release Candidate Stabilization 驗收。

確認 RIP v0.7.4-alpha release candidate 狀態的文件完整性：
README release candidate notes、command inventory snapshot、version strategy、
PROJECT_STATUS release readiness checklist、CHANGELOG、
runtime 零污染、destructive command 未增加且仍 full match。

所有測試使用 tmp_path / monkeypatch，不污染 runtime。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.mock_line import command_help_text, mock_line_payload
from app.approvals.manager import approval_manager

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME_JSON = (
    "runtime/approvals.json",
    "runtime/rename_transactions.json",
    "runtime/move_transactions.json",
)
_APPROVED_DESTRUCTIVE_COMMANDS = (
    "確認改名",
    "回滾改名",
    "確認搬移",
    "回滾搬移",
)


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _project_status() -> str:
    return (_REPO_ROOT / "docs" / "PROJECT_STATUS.md").read_text(encoding="utf-8")


def _changelog() -> str:
    return (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _mock_line_source() -> str:
    return (_REPO_ROOT / "scripts" / "mock_line.py").read_text(encoding="utf-8")


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


# ---------------------------------------------------------------------------
# Tests 1-4: README version & release candidate content
# ---------------------------------------------------------------------------


def test_readme_contains_current_rip_version():
    """README 應記載目前版本 v0.7.4-alpha。"""
    assert "v0.7.4-alpha" in _readme()


def test_readme_mentions_release_candidate_notes():
    """README 應包含 Release Candidate Notes 區塊。"""
    assert "Release Candidate Notes" in _readme()


def test_readme_mentions_local_cli_mock_line_interface():
    """README 應說明本機 CLI / Mock LINE operator interface 的使用方式。"""
    readme = _readme()
    assert "Mock LINE" in readme
    assert "本機" in readme
    assert "mock_line.py" in readme


def test_readme_documents_not_suitable_for_multi_user_production():
    """README 應明確記載不適用於多人同時操作、非 production daemon 的場景。"""
    readme = _readme()
    assert "多人" in readme
    assert "production" in readme


# ---------------------------------------------------------------------------
# Tests 5-8: PROJECT_STATUS release readiness checklist
# ---------------------------------------------------------------------------


def test_project_status_contains_release_readiness_checklist():
    """PROJECT_STATUS 應包含 Release Readiness Checklist。"""
    status = _project_status()
    assert "Release Readiness Checklist" in status


def test_project_status_checklist_contains_rename_workflow_completed():
    """Checklist 應標記 RenamePlan workflow completed。"""
    status = _project_status()
    assert "RenamePlan workflow completed" in status


def test_project_status_checklist_contains_move_workflow_completed():
    """Checklist 應標記 MovePlan workflow completed。"""
    status = _project_status()
    assert "MovePlan workflow completed" in status


def test_project_status_checklist_contains_runtime_settings_completed():
    """Checklist 應標記 Runtime settings consolidated。"""
    status = _project_status()
    assert "Runtime settings consolidated" in status


# ---------------------------------------------------------------------------
# Test 9: CHANGELOG contains latest version section
# ---------------------------------------------------------------------------


def test_changelog_contains_latest_version_section():
    """CHANGELOG 最上方應有 v0.7.4-alpha Phase 16E 段落。"""
    changelog = _changelog()
    assert "v0.7.4-alpha" in changelog
    assert "16E" in changelog


# ---------------------------------------------------------------------------
# Test 10: pyproject.toml version strategy documented
# ---------------------------------------------------------------------------


def test_pyproject_version_strategy_is_documented():
    """README 或 PROJECT_STATUS 應記載 pyproject.toml 版本策略（方案 A）。"""
    combined = _readme() + _project_status()
    assert "pyproject.toml" in combined
    assert "source of truth" in combined or "版本策略" in combined or "packaging metadata" in combined


# ---------------------------------------------------------------------------
# Test 11: no runtime JSON tracked by git
# ---------------------------------------------------------------------------


def test_no_runtime_json_tracked_by_git():
    """runtime/ 下不可有任何被 git 追蹤的 JSON 檔案。"""
    result = subprocess.run(
        ["git", "ls-files", "runtime/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", "runtime/ 下不可有任何被 git 追蹤的檔案"


# ---------------------------------------------------------------------------
# Tests 12-13: destructive command audit
# ---------------------------------------------------------------------------


def test_no_new_mock_line_destructive_command_beyond_approved_list():
    """Mock LINE 不可新增 approved list 以外的危險操作指令。"""
    source = _mock_line_source()
    unapproved_dangerous_verbs = ("刪除", "清除", "覆蓋", "格式化", "抹除", "清空")
    for verb in unapproved_dangerous_verbs:
        # 找有無以該詞為主體的 full-match regex pattern
        match = re.search(r'["\'](\^[^"\']*' + verb + r'[^"\']*\$)["\']', source)
        assert match is None, (
            f"mock_line.py 不可新增含「{verb}」的 full-match destructive regex：{match}"
        )


def test_approved_destructive_commands_remain_full_match():
    """四個 approved destructive 指令的 regex 必須保持 ^ 開頭 $ 結尾（full match）。"""
    source = _mock_line_source()
    for cmd in _APPROVED_DESTRUCTIVE_COMMANDS:
        patterns = re.findall(
            r'["\'](\^[^"\']*' + re.escape(cmd) + r'[^"\']*\$)["\']',
            source,
        )
        assert patterns, f"Approved destructive 指令「{cmd}」應有 full match regex（^…$）"
        for p in patterns:
            assert p.startswith("^"), f"「{cmd}」regex 必須以 ^ 開頭，實際：{p}"
            assert p.endswith("$"), f"「{cmd}」regex 必須以 $ 結尾，實際：{p}"


# ---------------------------------------------------------------------------
# Test 14: help command still works
# ---------------------------------------------------------------------------


def test_help_command_still_works(isolated_approvals):
    """說明 / help / /help / 指令說明 應仍正常回傳 help text（不 crash、不變）。"""
    for cmd in ("說明", "help", "/help", "指令說明"):
        output = mock_line_payload(cmd)
        assert output == command_help_text(), f"「{cmd}」應回傳 command_help_text()，實際：{output[:80]}"


# ---------------------------------------------------------------------------
# Tests 15-16: key test files still exist
# ---------------------------------------------------------------------------


def test_cli_smoke_test_file_exists():
    """test_cli_smoke.py 應存在（16D packaging smoke tests）。"""
    assert (_REPO_ROOT / "tests" / "test_cli_smoke.py").is_file()


def test_e2e_audit_test_file_exists():
    """test_end_to_end_workflow_audit.py 應存在（16A E2E audit tests）。"""
    assert (_REPO_ROOT / "tests" / "test_end_to_end_workflow_audit.py").is_file()


# ---------------------------------------------------------------------------
# Tests 17-19: command inventory documented in README
# ---------------------------------------------------------------------------


def test_readme_contains_command_inventory():
    """README 應包含 Command Inventory 完整指令一覽區塊。"""
    readme = _readme()
    assert "Command Inventory" in readme or "完整指令一覽" in readme


def test_readme_command_inventory_separates_destructive_from_non_destructive():
    """Command Inventory 應明確區分 Non-destructive 與 Destructive 兩類。"""
    readme = _readme()
    assert "Non-destructive" in readme or "不會改動任何檔案" in readme
    assert "Destructive" in readme


def test_readme_command_inventory_lists_all_approved_destructive_commands():
    """Command Inventory 應列出全部四個 approved destructive 指令。"""
    readme = _readme()
    for cmd in _APPROVED_DESTRUCTIVE_COMMANDS:
        assert cmd in readme, f"README command inventory 應包含 destructive 指令：{cmd}"


def test_readme_command_inventory_lists_non_destructive_commands():
    """Command Inventory 應列出 non-destructive 指令（說明 / 整理檔名 / 整理資料夾 / 預覽系列）。"""
    readme = _readme()
    non_destructive = ("說明", "整理檔名", "整理資料夾", "預覽回滾改名", "預覽回滾搬移")
    for cmd in non_destructive:
        assert cmd in readme, f"README command inventory 應包含 non-destructive 指令：{cmd}"
