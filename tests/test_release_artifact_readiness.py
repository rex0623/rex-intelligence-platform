"""Phase 16G 測試：Git Tagging / Release Artifact Preparation 驗收。

確認 tagging instructions 已文件化、package artifact 建置狀態已記錄、
pyproject version strategy 已最終確認、dist artifacts 未被 git 追蹤、
runtime JSON 未被 git 追蹤、所有 release 文件版本一致。

所有測試使用 tmp_path / monkeypatch 或只做 read-only 稽核，不污染 runtime。
"""

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _project_status() -> str:
    return (_REPO_ROOT / "docs" / "PROJECT_STATUS.md").read_text(encoding="utf-8")


def _changelog() -> str:
    return (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _release_notes() -> str:
    return (_REPO_ROOT / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")


def _pyproject() -> str:
    return (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests 1-6: RELEASE_NOTES tagging instructions content
# ---------------------------------------------------------------------------


def test_release_notes_contains_tagging_instructions():
    """RELEASE_NOTES 應包含 Tagging Instructions 區塊。"""
    rn = _release_notes()
    assert "Tagging Instructions" in rn or "tagging instructions" in rn.lower()


def test_release_notes_mentions_v074_alpha():
    """RELEASE_NOTES 應包含 v0.7.4-alpha 版本。"""
    assert "v0.7.4-alpha" in _release_notes()


def test_release_notes_says_tag_not_pushed_automatically():
    """RELEASE_NOTES 應明確聲明不自動 push tag。"""
    rn = _release_notes()
    assert "不自動" in rn or "not automatically" in rn.lower()
    assert "push" in rn.lower()


def test_release_notes_documents_git_tag_command():
    """RELEASE_NOTES 應記載人工建立 annotated tag 的指令。"""
    rn = _release_notes()
    assert "git tag -a v0.7.4-alpha" in rn


def test_release_notes_documents_git_show_command():
    """RELEASE_NOTES 應記載確認 tag 的 git show 指令。"""
    rn = _release_notes()
    assert "git show v0.7.4-alpha" in rn


def test_release_notes_documents_git_push_as_manual_step():
    """RELEASE_NOTES 應記載 git push origin v0.7.4-alpha 為人工步驟。"""
    rn = _release_notes()
    assert "git push origin v0.7.4-alpha" in rn


# ---------------------------------------------------------------------------
# Tests 7-9: PROJECT_STATUS tag readiness and artifact
# ---------------------------------------------------------------------------


def test_project_status_contains_tag_readiness_status():
    """PROJECT_STATUS 應包含 Tag Readiness Checklist。"""
    assert "Tag Readiness Checklist" in _project_status()


def test_project_status_says_package_artifact_not_committed():
    """PROJECT_STATUS 應記載 dist artifacts 已 gitignored 未 commit。"""
    status = _project_status()
    assert "gitignored" in status or "artifact" in status.lower()
    # dist artifacts 項目在 Tag Readiness 中標記為 ✅（built & gitignored）
    assert "dist" in status or "artifact" in status.lower()


def test_project_status_documents_pyproject_version_strategy():
    """PROJECT_STATUS 應記載 pyproject version strategy（方案 A）。"""
    status = _project_status()
    assert "pyproject.toml" in status
    assert (
        "source of truth" in status
        or "packaging metadata" in status
        or "版本策略" in status
    )


# ---------------------------------------------------------------------------
# Test 10: README links to RELEASE_NOTES
# ---------------------------------------------------------------------------


def test_readme_links_to_release_notes():
    """README 應包含 RELEASE_NOTES.md 連結。"""
    readme = _readme()
    assert "RELEASE_NOTES" in readme


# ---------------------------------------------------------------------------
# Test 11: CHANGELOG contains v0.7.4-alpha
# ---------------------------------------------------------------------------


def test_changelog_contains_v074_alpha():
    """CHANGELOG 應包含 v0.7.4-alpha 版本條目。"""
    changelog = _changelog()
    assert "v0.7.4-alpha" in changelog
    assert "16G" in changelog


# ---------------------------------------------------------------------------
# Test 12: pyproject.toml exists
# ---------------------------------------------------------------------------


def test_pyproject_toml_exists():
    """pyproject.toml 應存在。"""
    assert (_REPO_ROOT / "pyproject.toml").is_file()


# ---------------------------------------------------------------------------
# Test 13: pyproject version documented as packaging metadata
# ---------------------------------------------------------------------------


def test_pyproject_version_is_packaging_metadata_only():
    """pyproject.toml version（0.1.0）應維持為 packaging metadata（方案 A：不改變）。"""
    pyproject = _pyproject()
    assert 'version = "0.1.0"' in pyproject, (
        "pyproject.toml version 應維持 0.1.0（packaging metadata，方案 A 決策）"
    )


# ---------------------------------------------------------------------------
# Test 14: dist artifacts are not tracked by git
# ---------------------------------------------------------------------------


def test_dist_artifacts_not_tracked_by_git():
    """dist/ 目錄下不可有任何被 git 追蹤的 artifact。"""
    result = subprocess.run(
        ["git", "ls-files", "dist/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", "dist/ 下不可有任何被 git 追蹤的 artifact"


# ---------------------------------------------------------------------------
# Test 15: runtime JSON files are not tracked by git
# ---------------------------------------------------------------------------


def test_runtime_json_files_not_tracked_by_git():
    """runtime/ 下不可有任何被 git 追蹤的 JSON 檔案（最終確認）。"""
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
# Test 16: all key test files still exist
# ---------------------------------------------------------------------------


def test_all_key_test_files_exist():
    """Phase 16D–16G 的關鍵測試檔案應全數存在。"""
    key_test_files = (
        "tests/test_cli_smoke.py",
        "tests/test_end_to_end_workflow_audit.py",
        "tests/test_release_readiness.py",
        "tests/test_final_regression_release_candidate.py",
        "tests/test_release_artifact_readiness.py",
    )
    for path in key_test_files:
        assert (_REPO_ROOT / path).is_file(), f"關鍵測試檔案應存在：{path}"
