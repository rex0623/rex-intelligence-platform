"""Phase 17D 測試：Operator Preflight Validation。

涵蓋：
- PreflightItem dataclass 與 run_operator_preflight() 可 import
- Python 版本檢查（pass / fail，透過 _python_version_info override）
- fcntl 可用性
- SAFE_PDF_ROOT 存在時通過；不存在時回報但不建立目錄
- RUNTIME_DIR 不存在時可建立；建立後無 JSON state
- preflight 不呼叫 acquire_runtime_lock（不建立 rip.lock）
- preflight 不建立 approvals.json
- runtime/ 不被 git 追蹤
- dist/ 不被 git 追蹤
- pyproject.toml 有 rip console_scripts 設定
- run_operator_preflight() 回傳 list[PreflightItem]

所有測試使用 tmp_path / 參數 override，不污染真實 runtime/。
"""

import sys
from pathlib import Path

import pytest

from app.core.preflight import (
    PreflightItem,
    _check_fcntl,
    _check_git_ls_files,
    _check_pyproject_console_scripts,
    _check_python_version,
    _check_runtime_dir_writable,
    _check_safe_pdf_root,
    run_operator_preflight,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# Module importability
# ===========================================================================


def test_preflight_module_importable():
    """PreflightItem 與 run_operator_preflight 可 import，型別正確。"""
    assert callable(run_operator_preflight)
    item = PreflightItem(name="test", ok=True, message="ok")
    assert item.name == "test"
    assert item.ok is True


# ===========================================================================
# Python version check
# ===========================================================================


def test_python_version_check_passes_current():
    """目前執行環境 Python 版本應通過（>= 3.12）。"""
    result = _check_python_version()
    assert result.ok, f"目前 Python 應通過版本檢查，訊息：{result.message}"
    assert "3.1" in result.message


def test_python_version_check_fails_old_version():
    """Python 3.11 應回報失敗，訊息含版本號。"""
    result = _check_python_version(version_info=(3, 11, 0))
    assert not result.ok
    assert "3.11" in result.message
    assert result.name == "python_version"


def test_python_version_check_passes_exact_minimum():
    """Python 3.12.0 應剛好通過。"""
    result = _check_python_version(version_info=(3, 12, 0))
    assert result.ok


# ===========================================================================
# fcntl availability
# ===========================================================================


def test_fcntl_check_passes():
    """Linux / WSL2 環境下 fcntl 應可用。"""
    result = _check_fcntl()
    assert result.ok, f"fcntl 應可用，訊息：{result.message}"
    assert result.name == "fcntl_available"


# ===========================================================================
# SAFE_PDF_ROOT
# ===========================================================================


def test_safe_pdf_root_exists_passes(tmp_path):
    """SAFE_PDF_ROOT 目錄存在時應回傳 ok=True。"""
    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()
    result = _check_safe_pdf_root(pdf_root)
    assert result.ok
    assert result.name == "safe_pdf_root_exists"


def test_safe_pdf_root_missing_is_reported(tmp_path):
    """SAFE_PDF_ROOT 不存在時回報 ok=False，訊息含路徑。"""
    missing = tmp_path / "nonexistent_pdf_inbox"
    result = _check_safe_pdf_root(missing)
    assert not result.ok
    assert str(missing) in result.message


def test_safe_pdf_root_missing_does_not_create_directory(tmp_path):
    """preflight 不可自動建立 SAFE_PDF_ROOT 目錄。"""
    missing = tmp_path / "should_not_be_created"
    assert not missing.exists()
    _check_safe_pdf_root(missing)
    assert not missing.exists(), "preflight 不應建立 SAFE_PDF_ROOT 目錄"


# ===========================================================================
# RUNTIME_DIR
# ===========================================================================


def test_runtime_dir_created_if_missing(tmp_path):
    """RUNTIME_DIR 不存在時，preflight 應建立該目錄並回傳 ok=True。"""
    new_runtime = tmp_path / "new_runtime"
    assert not new_runtime.exists()
    result = _check_runtime_dir_writable(new_runtime)
    assert result.ok
    assert new_runtime.is_dir(), "RUNTIME_DIR 應已建立"


def test_runtime_dir_creation_leaves_no_json_state(tmp_path):
    """RUNTIME_DIR 建立後不應產生任何 .json 檔案（no workflow state）。"""
    runtime_dir = tmp_path / "runtime"
    _check_runtime_dir_writable(runtime_dir)
    json_files = list(runtime_dir.glob("*.json"))
    assert json_files == [], f"preflight 不應建立 JSON state：{json_files}"


def test_runtime_dir_no_write_test_file_remaining(tmp_path):
    """寫入測試用的臨時檔案（.preflight_write_test）在 preflight 後應已被刪除。"""
    runtime_dir = tmp_path / "runtime"
    _check_runtime_dir_writable(runtime_dir)
    assert not (runtime_dir / ".preflight_write_test").exists()


# ===========================================================================
# preflight 不呼叫 acquire_runtime_lock / 不建立 approvals.json
# ===========================================================================


def test_preflight_does_not_acquire_runtime_lock(tmp_path):
    """preflight 執行後不應建立 rip.lock（代表未呼叫 acquire_runtime_lock）。"""
    runtime_dir = tmp_path / "runtime"
    run_operator_preflight(
        runtime_dir=runtime_dir,
        safe_pdf_root=tmp_path,
        repo_root=tmp_path,
    )
    assert not (runtime_dir / "rip.lock").exists(), (
        "preflight 不應建立 rip.lock（不可呼叫 acquire_runtime_lock）"
    )


def test_preflight_does_not_touch_approvals_json(tmp_path):
    """preflight 執行後不應建立 approvals.json。"""
    runtime_dir = tmp_path / "runtime"
    run_operator_preflight(
        runtime_dir=runtime_dir,
        safe_pdf_root=tmp_path,
        repo_root=tmp_path,
    )
    assert not (runtime_dir / "approvals.json").exists(), (
        "preflight 不應建立 approvals.json"
    )


# ===========================================================================
# Git tracking checks
# ===========================================================================


def test_runtime_not_git_tracked():
    """runtime/ 下不應有任何被 git 追蹤的檔案。"""
    result = _check_git_ls_files("runtime/", "runtime", _REPO_ROOT)
    assert result.ok, f"runtime/ 下有 git 追蹤檔案：{result.message}"


def test_dist_not_git_tracked():
    """dist/ 下不應有任何被 git 追蹤的檔案。"""
    result = _check_git_ls_files("dist/", "dist", _REPO_ROOT)
    assert result.ok, f"dist/ 下有 git 追蹤檔案：{result.message}"


# ===========================================================================
# pyproject console_scripts
# ===========================================================================


def test_pyproject_has_rip_console_script():
    """pyproject.toml 應含 rip = "scripts.mock_line:main"。"""
    result = _check_pyproject_console_scripts(_REPO_ROOT)
    assert result.ok, f"pyproject.toml 缺少 rip console_scripts：{result.message}"


# ===========================================================================
# Integration: run_operator_preflight()
# ===========================================================================


def test_run_operator_preflight_returns_list_of_preflight_items(tmp_path):
    """run_operator_preflight() 回傳 list[PreflightItem]，共 7 個 check。"""
    results = run_operator_preflight(
        runtime_dir=tmp_path / "runtime",
        safe_pdf_root=tmp_path,
        repo_root=_REPO_ROOT,
    )
    assert isinstance(results, list)
    assert all(isinstance(r, PreflightItem) for r in results)
    assert len(results) == 7, f"預期 7 個 check，實際 {len(results)} 個"
    names = [r.name for r in results]
    assert "python_version" in names
    assert "fcntl_available" in names
    assert "safe_pdf_root_exists" in names
    assert "runtime_dir_writable" in names
    assert "runtime_not_git_tracked" in names
    assert "dist_not_git_tracked" in names
    assert "pyproject_console_scripts" in names
