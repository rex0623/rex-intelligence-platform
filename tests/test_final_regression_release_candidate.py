"""Phase 16F 最終回歸稽核：Release Candidate Tagging / Final Regression。

本測試檔案為 v0.7.4-alpha release candidate 的最後 gate check：
- Safety invariants（destructive full match、preview read-only、planning non-destructive）
- Rename / Move log 分離不變式
- Runtime / git 稽核
- 文件一致性（README / PROJECT_STATUS / CHANGELOG / RELEASE_NOTES 版本與內容）
- Tag readiness checklist 狀態
- Help 指令回歸
- Command inventory 最終比對

不重複既有測試細節，只做 invariant gate check。
所有測試使用 tmp_path / monkeypatch，不污染 runtime。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.mock_line import command_help_text, mock_line_payload
from app.approvals.manager import approval_manager
from app.core.config import settings
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME_JSON = (
    "runtime/approvals.json",
    "runtime/rename_transactions.json",
    "runtime/move_transactions.json",
)
_APPROVED_DESTRUCTIVE_COMMANDS = ("確認改名", "回滾改名", "確認搬移", "回滾搬移")
_PREVIEW_COMMANDS = ("預覽回滾改名", "預覽回滾搬移")


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _project_status() -> str:
    return (_REPO_ROOT / "docs" / "PROJECT_STATUS.md").read_text(encoding="utf-8")


def _changelog() -> str:
    return (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _release_notes() -> str:
    return (_REPO_ROOT / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")


def _mock_line_source() -> str:
    return (_REPO_ROOT / "scripts" / "mock_line.py").read_text(encoding="utf-8")


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


@pytest.fixture
def rename_log(tmp_path):
    return RenameTransactionLog(tmp_path / "rename_tx.json")


@pytest.fixture
def move_log(tmp_path):
    return MoveTransactionLog(tmp_path / "move_tx.json")


# ===========================================================================
# Task 1 — Destructive command invariants
# ===========================================================================


def test_destructive_commands_still_full_match():
    """四個 approved destructive 指令的 regex 必須保持 ^ 開頭 $ 結尾（full match 不變）。"""
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


def test_no_unknown_destructive_command_patterns():
    """mock_line.py 不可含 approved list 以外的危險操作 full-match regex。"""
    source = _mock_line_source()
    unapproved_verbs = ("刪除", "清除", "覆蓋", "格式化", "抹除", "清空")
    for verb in unapproved_verbs:
        match = re.search(r'["\'](\^[^"\']*' + verb + r'[^"\']*\$)["\']', source)
        assert match is None, (
            f"mock_line.py 不可有含「{verb}」的 full-match regex：{match}"
        )


# ===========================================================================
# Task 1 — Preview command invariants
# ===========================================================================


def test_preview_commands_have_full_match_regex():
    """兩個 preview 指令應有 ^…$ full match regex（確保不被模糊觸發）。"""
    source = _mock_line_source()
    for cmd in _PREVIEW_COMMANDS:
        patterns = re.findall(
            r'["\'](\^[^"\']*' + re.escape(cmd) + r'[^"\']*\$)["\']',
            source,
        )
        assert patterns, f"Preview 指令「{cmd}」應有 full match regex（^…$）"


# ===========================================================================
# Task 1 — Planning commands non-destructive smoke
# ===========================================================================


def test_planning_commands_non_destructive_smoke(
    tmp_path, monkeypatch, isolated_approvals, rename_log, move_log
):
    """三個 planning 指令對空 pdf_root 不可動任何檔案、不寫任何 log。"""
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    for cmd in ("整理檔名", "整理資料夾", "產生搬移計畫"):
        mock_line_payload(cmd, transaction_log=rename_log, move_transaction_log=move_log)

    assert list(pdf_root.rglob("*")) == [], "planning 指令不可建立或改動任何檔案"
    assert not rename_log._log_path.exists(), "planning 指令不可寫入 rename log"
    assert not move_log._log_path.exists(), "planning 指令不可寫入 move log"


# ===========================================================================
# Task 1 — Generic approval confirm is dry-run only
# ===========================================================================


def test_generic_approval_confirm_unknown_id_safe(
    isolated_approvals, rename_log, move_log
):
    """「確認 {fake_id}」應安全回覆 not-found，不 crash，不動任何 log。"""
    output = mock_line_payload(
        "確認 FAKE-APPROVAL-REGTEST-999",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert isinstance(output, str) and output
    assert not rename_log._log_path.exists(), "確認 fake_id 不可寫 rename log"
    assert not move_log._log_path.exists(), "確認 fake_id 不可寫 move log"


# ===========================================================================
# Task 1 — Rename / Move log separation
# ===========================================================================


def test_rename_rollback_does_not_touch_move_log(
    isolated_approvals, rename_log, move_log
):
    """「回滾改名 {fake_id}」只查詢 rename log，不觸碰 move log。"""
    output = mock_line_payload(
        "回滾改名 FAKE-TX-REGTEST-001",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert isinstance(output, str)
    assert not move_log._log_path.exists(), "回滾改名 不可建立或修改 move log"


def test_move_rollback_does_not_touch_rename_log(
    isolated_approvals, rename_log, move_log
):
    """「回滾搬移 {fake_id}」只查詢 move log，不觸碰 rename log。"""
    output = mock_line_payload(
        "回滾搬移 FAKE-TX-REGTEST-001",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert isinstance(output, str)
    assert not rename_log._log_path.exists(), "回滾搬移 不可建立或修改 rename log"


# ===========================================================================
# Task 1 — Runtime / git
# ===========================================================================


def test_runtime_json_not_git_tracked():
    """runtime/ 下不可有任何被 git 追蹤的 JSON 檔案（最終回歸確認）。"""
    result = subprocess.run(
        ["git", "ls-files", "runtime/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", "runtime/ 下不可有任何被 git 追蹤的檔案"


# ===========================================================================
# Task 1 — Document consistency
# ===========================================================================


def test_version_present_in_readme_project_status_changelog():
    """README / PROJECT_STATUS / CHANGELOG 三份文件均應包含目前 release version v0.7.4-alpha。"""
    version = "v0.7.4-alpha"
    assert version in _readme(), "README 應含 v0.7.4-alpha"
    assert version in _project_status(), "PROJECT_STATUS 應含 v0.7.4-alpha"
    assert version in _changelog(), "CHANGELOG 應含 v0.7.4-alpha"


def test_readme_has_command_inventory():
    """README 應含 Command Inventory（完整指令一覽）區塊。"""
    readme = _readme()
    assert "Command Inventory" in readme or "完整指令一覽" in readme


def test_project_status_has_release_readiness_checklist():
    """PROJECT_STATUS 應含 Release Readiness Checklist。"""
    assert "Release Readiness Checklist" in _project_status()


def test_changelog_has_16f_entry():
    """CHANGELOG 應含 Phase 16F 條目。"""
    changelog = _changelog()
    assert "16F" in changelog
    assert "Final Regression" in changelog or "Release Candidate Tagging" in changelog


def test_pyproject_version_strategy_documented():
    """pyproject.toml 版本策略應記載於 README 或 PROJECT_STATUS。"""
    combined = _readme() + _project_status()
    assert "pyproject.toml" in combined
    assert (
        "source of truth" in combined
        or "版本策略" in combined
        or "packaging metadata" in combined
    )


# ===========================================================================
# Task 1 — Help regression
# ===========================================================================


def test_help_command_works(isolated_approvals):
    """說明 / help / /help / 指令說明 應仍正常回傳 help text（最終回歸確認）。"""
    for cmd in ("說明", "help", "/help", "指令說明"):
        output = mock_line_payload(cmd)
        assert output == command_help_text(), (
            f"「{cmd}」應回傳 command_help_text()，實際：{output[:80]}"
        )


# ===========================================================================
# Task 6 — RELEASE_NOTES content audit
# ===========================================================================


def test_release_notes_file_exists():
    """docs/RELEASE_NOTES.md 應存在。"""
    assert (_REPO_ROOT / "docs" / "RELEASE_NOTES.md").is_file()


def test_release_notes_has_current_version():
    """RELEASE_NOTES 應包含 v0.7.4-alpha。"""
    assert "v0.7.4-alpha" in _release_notes()


def test_release_notes_has_safety_guarantees_section():
    """RELEASE_NOTES 應包含 Safety Guarantees 區塊。"""
    rn = _release_notes()
    assert "Safety Guarantees" in rn or "safety guarantees" in rn.lower()


def test_release_notes_has_operator_commands_section():
    """RELEASE_NOTES 應包含 Operator Commands 區塊，且列出 destructive 與 non-destructive 指令。"""
    rn = _release_notes()
    assert "Operator Commands" in rn
    for cmd in _APPROVED_DESTRUCTIVE_COMMANDS:
        assert cmd in rn, f"RELEASE_NOTES operator commands 應含 destructive 指令：{cmd}"


def test_release_notes_has_known_limitations_section():
    """RELEASE_NOTES 應包含 Known Limitations 區塊。"""
    rn = _release_notes()
    assert "Known Limitations" in rn


def test_release_notes_documents_no_auto_tag():
    """RELEASE_NOTES 應明確聲明本 phase 不自動建立 git tag。"""
    rn = _release_notes()
    assert "不自動" in rn or "not automatically" in rn.lower() or "⬜" in rn


# ===========================================================================
# Task 6 — Tag readiness
# ===========================================================================


def test_project_status_has_tag_readiness_checklist():
    """PROJECT_STATUS 應包含 Tag Readiness Checklist。"""
    assert "Tag Readiness Checklist" in _project_status()


def test_project_status_git_tag_not_yet_created():
    """PROJECT_STATUS Tag Readiness 中「Git tag created」應標記為未完成（[ ]）。"""
    status = _project_status()
    assert "[ ] Git tag created" in status, (
        "PROJECT_STATUS 中 git tag 項目應為 [ ]（尚未建立）"
    )


# ===========================================================================
# Task 6 — README links to RELEASE_NOTES
# ===========================================================================


def test_readme_links_to_release_notes():
    """README 應包含 RELEASE_NOTES.md 連結。"""
    readme = _readme()
    assert "RELEASE_NOTES.md" in readme or "RELEASE_NOTES" in readme


# ===========================================================================
# Task 6 — Command inventory final check
# ===========================================================================


def test_destructive_command_inventory_matches_approved_list():
    """mock_line.py 的 destructive full-match regex 數量應等於 approved list（4 個）。"""
    source = _mock_line_source()
    found = set()
    for cmd in _APPROVED_DESTRUCTIVE_COMMANDS:
        patterns = re.findall(
            r'["\'](\^[^"\']*' + re.escape(cmd) + r'[^"\']*\$)["\']',
            source,
        )
        if patterns:
            found.add(cmd)
    assert found == set(_APPROVED_DESTRUCTIVE_COMMANDS), (
        f"Destructive command inventory 不符合 approved list。"
        f"預期：{set(_APPROVED_DESTRUCTIVE_COMMANDS)}，實際發現：{found}"
    )


def test_no_new_mock_line_regex_added_beyond_approved():
    """mock_line.py 不可新增任何 approved inventory 以外的 full-match 中文 destructive regex。"""
    source = _mock_line_source()
    all_full_match = re.findall(r'["\'](\^[一-鿿][^"\']*\$)["\']', source)
    known_prefixes = (
        "^確認改名", "^回滾改名",
        "^確認搬移", "^回滾搬移",
        "^預覽回滾改名", "^預覽回滾搬移",
        "^確認\\s", "^取消\\s",
        "^說明$", "^指令說明$",
    )
    for pattern in all_full_match:
        is_known = any(
            pattern == prefix or pattern.startswith(prefix.replace("\\s", " ").replace("\\s+", " "))
            for prefix in known_prefixes
        )
        assert is_known, (
            f"發現未知 full-match 中文指令 regex：{pattern!r}（不在 approved inventory 中）"
        )


def test_release_notes_lists_all_operator_commands():
    """RELEASE_NOTES 應列出 non-destructive 指令（說明 / 整理檔名 / 整理資料夾 / 預覽系列）。"""
    rn = _release_notes()
    for cmd in ("說明", "整理檔名", "整理資料夾", "預覽回滾改名", "預覽回滾搬移"):
        assert cmd in rn, f"RELEASE_NOTES operator commands 應含 non-destructive 指令：{cmd}"
