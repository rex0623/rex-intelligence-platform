"""Phase 16B 測試：Runtime Settings Consolidation。

runtime 路徑集中於 app/core/config.py 的 settings + helpers：
- get_runtime_dir / get_approval_store_path /
  get_rename_transaction_log_path / get_move_transaction_log_path /
  get_safe_pdf_root
- 預設值與 16B 前完全相容（runtime/*.json）
- monkeypatch settings.RUNTIME_DIR 即可全面隔離
- runtime JSON 持續 gitignored 且不被 git 追蹤
"""

import subprocess
from pathlib import Path

import pytest

from app.core.config import (
    get_approval_store_path,
    get_move_transaction_log_path,
    get_rename_transaction_log_path,
    get_runtime_dir,
    get_safe_pdf_root,
    settings,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 測試 1–4：預設值（與 16B 前行為相容）
# ---------------------------------------------------------------------------


def test_default_runtime_dir_is_repo_runtime():
    assert get_runtime_dir() == _REPO_ROOT / "runtime"


def test_default_approval_store_path():
    assert get_approval_store_path() == _REPO_ROOT / "runtime" / "approvals.json"


def test_default_rename_transaction_log_path():
    assert (
        get_rename_transaction_log_path()
        == _REPO_ROOT / "runtime" / "rename_transactions.json"
    )


def test_default_move_transaction_log_path():
    assert (
        get_move_transaction_log_path()
        == _REPO_ROOT / "runtime" / "move_transactions.json"
    )


# ---------------------------------------------------------------------------
# 測試 5：helpers 可由 monkeypatch 覆寫
# ---------------------------------------------------------------------------


def test_helpers_follow_monkeypatched_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path / "rt"))

    assert get_runtime_dir() == tmp_path / "rt"
    assert get_approval_store_path() == tmp_path / "rt" / "approvals.json"
    assert (
        get_rename_transaction_log_path()
        == tmp_path / "rt" / "rename_transactions.json"
    )
    assert (
        get_move_transaction_log_path() == tmp_path / "rt" / "move_transactions.json"
    )


def test_safe_pdf_root_follows_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(tmp_path / "pdfs"))

    assert get_safe_pdf_root() == tmp_path / "pdfs"


# ---------------------------------------------------------------------------
# 測試 6–8：各模組預設路徑改由 settings 取得
# ---------------------------------------------------------------------------


def test_approval_manager_default_path_uses_settings(tmp_path, monkeypatch):
    from app.approvals.manager import ApprovalManager

    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path / "rt"))

    manager = ApprovalManager()  # 不傳 store_path → 走 settings 預設

    assert manager.store_path == tmp_path / "rt" / "approvals.json"


def test_default_rename_log_uses_settings(tmp_path, monkeypatch):
    """mock_line 未注入 log 時，rename log 寫到 settings 指定的 runtime dir。"""
    import scripts.mock_line as mock_line_module

    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path / "rt"))
    from app.core.config import get_rename_transaction_log_path as helper

    assert helper() == tmp_path / "rt" / "rename_transactions.json"
    # mock_line 原始碼不再 hardcode runtime 路徑，改 import settings helper
    import inspect

    source = inspect.getsource(mock_line_module)
    assert "get_rename_transaction_log_path" in source
    assert '"runtime"' not in source and "'runtime'" not in source


def test_default_move_log_uses_settings(tmp_path, monkeypatch):
    from app.folder_intelligence.approval_bridge import default_move_transaction_log

    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path / "rt"))

    log = default_move_transaction_log()

    assert log._log_path == tmp_path / "rt" / "move_transactions.json"


# ---------------------------------------------------------------------------
# 測試 9–10：gitignore / git 追蹤稽核
# ---------------------------------------------------------------------------


def test_gitignore_includes_runtime_json_files():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for runtime_file in (
        "runtime/approvals.json",
        "runtime/rename_transactions.json",
        "runtime/move_transactions.json",
    ):
        assert runtime_file in gitignore


def test_git_does_not_track_runtime_json_files():
    result = subprocess.run(
        ["git", "ls-files", "runtime/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert [l for l in result.stdout.splitlines() if l.strip()] == []


# ---------------------------------------------------------------------------
# 補充：app/ 與 scripts/ 不再散落 hardcoded runtime 路徑
# ---------------------------------------------------------------------------


def test_no_hardcoded_runtime_paths_outside_config():
    """runtime 路徑只允許定義在 app/core/config.py（單一事實來源）。"""
    offenders: list[str] = []
    for py_file in list((_REPO_ROOT / "app").rglob("*.py")) + list(
        (_REPO_ROOT / "scripts").rglob("*.py")
    ):
        if "__pycache__" in py_file.parts:
            continue
        if py_file == _REPO_ROOT / "app" / "core" / "config.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        for needle in ('/ "runtime"', "/ 'runtime'"):
            if needle in text:
                offenders.append(str(py_file))
    assert offenders == [], f"runtime 路徑不可 hardcode 在 config 之外：{offenders}"
