"""Phase 16D 測試：Packaging / CLI Smoke Test。

確認 RIP 具備「可交付、可啟動、可驗證」的最小操作包裝：
README operator 文件、pyproject packaging metadata、mock_line CLI 入口、
runtime / gitignore 行為。不重複 16A E2E 稽核，只做入口層 smoke。

subprocess 僅用於「說明」（help）與 git 查詢等無副作用指令；
其餘一律直接呼叫 mock_line_payload，所有測試使用 tmp_path / monkeypatch。
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.mock_line import command_help_text, mock_line_payload
from app.approvals.manager import approval_manager
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME_JSON = (
    "runtime/approvals.json",
    "runtime/rename_transactions.json",
    "runtime/move_transactions.json",
)


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Task 1 稽核 — README operator 文件
# ---------------------------------------------------------------------------


def test_readme_exists():
    assert (_REPO_ROOT / "README.md").is_file()


def test_readme_documents_version_and_positioning():
    readme = _readme()
    assert "v0.7.4-alpha" in readme
    assert "Rex Intelligence Platform" in readme
    assert "本機文件智慧整理平台" in readme


def test_readme_documents_install_and_test_commands():
    readme = _readme()
    assert "poetry install" in readme
    assert "poetry run pytest -q" in readme


def test_readme_documents_mock_line_usage():
    readme = _readme()
    assert 'poetry run python scripts/mock_line.py "說明"' in readme
    for cmd in ("整理檔名", "分析 PDF 詳細", "整理資料夾", "產生搬移計畫"):
        assert f'poetry run python scripts/mock_line.py "{cmd}"' in readme


def test_readme_documents_planning_commands_are_safe():
    readme = _readme()
    assert "Planning 指令不會改檔案" in readme


def test_readme_documents_destructive_commands():
    readme = _readme()
    for cmd in ("確認改名 {approval_id}", "回滾改名 {transaction_id}",
                "確認搬移 {approval_id}", "回滾搬移 {transaction_id}"):
        assert cmd in readme, f"README 應記載 destructive 指令：{cmd}"
    assert "full match" in readme, "README 應記載 destructive 指令必須 full match"
    assert "模糊文字不會觸發 destructive action" in readme


def test_readme_documents_preview_read_only():
    readme = _readme()
    assert "預覽回滾改名 {transaction_id}" in readme
    assert "預覽回滾搬移 {transaction_id}" in readme
    assert "Preview 指令不會改檔案、不改 log" in readme


def test_readme_documents_runtime_files_gitignored():
    readme = _readme()
    for runtime_file in _RUNTIME_JSON:
        assert runtime_file in readme
    assert "gitignored" in readme


def test_readme_documents_safe_root_behavior():
    readme = _readme()
    assert "SAFE_PDF_ROOT" in readme


def test_readme_documents_known_limitations():
    readme = _readme()
    assert "非資料庫" in readme
    assert "console_scripts" in readme, (
        "README 應記載 console_scripts entry point 資訊（Phase 17A）"
    )


# ---------------------------------------------------------------------------
# Task 3 — Packaging metadata audit
# ---------------------------------------------------------------------------


def test_pyproject_exists_with_poetry_and_pytest():
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.poetry]" in pyproject
    assert "pytest" in pyproject, "pytest 應為 dev dependency（poetry run pytest -q）"
    assert '{ include = "app" }' in pyproject
    assert '{ include = "scripts" }' in pyproject, "scripts/ 應在 packages 中（Phase 17A）"


def test_pyproject_defines_rip_console_script():
    """pyproject.toml 應定義 rip console_scripts entry point（Phase 17A）。"""
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.poetry.scripts]" in pyproject, (
        "pyproject.toml 應含 [tool.poetry.scripts] 區塊"
    )
    assert 'rip = "scripts.mock_line:main"' in pyproject, (
        "rip entry point 應指向 scripts.mock_line:main"
    )


def test_rip_entry_point_callable():
    """scripts.mock_line:main 應可 import 且可呼叫（rip entry point 驗證）。"""
    import importlib
    module = importlib.import_module("scripts.mock_line")
    assert callable(module.main), "scripts.mock_line:main 必須可呼叫"


def test_readme_documents_rip_entry_point():
    """README 應記載 poetry run rip 的使用方式（Phase 17A）。"""
    readme = _readme()
    assert "poetry run rip" in readme, "README 應文件化 poetry run rip 用法"


def test_mock_line_cli_entrypoint_exists():
    assert (_REPO_ROOT / "scripts" / "mock_line.py").is_file()


def test_mock_line_module_imports_successfully():
    module = importlib.import_module("scripts.mock_line")
    assert callable(module.mock_line_payload)
    assert callable(module.command_help_text)
    assert callable(module.main)


# ---------------------------------------------------------------------------
# Task 2 — CLI smoke（help / unknown / planning；無副作用路徑）
# ---------------------------------------------------------------------------


def test_help_command_returns_help_text(isolated_approvals):
    output = mock_line_payload("說明")
    assert output == command_help_text()


def test_slash_help_command_returns_help_text(isolated_approvals):
    output = mock_line_payload("/help")
    assert output == command_help_text()


def test_help_output_includes_rename_and_move_commands():
    output = command_help_text()
    for cmd in ("確認改名", "回滾改名", "預覽回滾改名",
                "確認搬移", "回滾搬移", "預覽回滾搬移"):
        assert cmd in output


def test_help_command_does_not_create_runtime_logs(
    tmp_path, isolated_approvals, rename_log, move_log
):
    mock_line_payload("說明", transaction_log=rename_log, move_transaction_log=move_log)
    assert isolated_approvals._store == {}
    assert not rename_log._log_path.exists()
    assert not move_log._log_path.exists()


def test_unknown_command_returns_safe_response(
    tmp_path, isolated_approvals, rename_log, move_log
):
    output = mock_line_payload(
        "今天天氣如何", transaction_log=rename_log, move_transaction_log=move_log
    )
    assert isinstance(output, str) and output, "未知指令應回覆字串而非 crash"
    assert isolated_approvals._store == {}, "未知指令不可建立 approval"
    assert not rename_log._log_path.exists()
    assert not move_log._log_path.exists()


def test_planning_command_smoke_does_not_crash(
    tmp_path, monkeypatch, isolated_approvals
):
    """「整理檔名」對空的 SAFE_PDF_ROOT 不可 crash，也不可動任何檔案。"""
    from app.core.config import settings

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()
    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    output = mock_line_payload("整理檔名")

    assert isinstance(output, str) and output
    assert list(pdf_root.rglob("*")) == [], "planning 不可建立或改動任何檔案"


def test_cli_subprocess_help_smoke():
    """真實 CLI 入口 smoke：只跑無副作用的「說明」，並驗證 runtime 零污染。"""
    runtime_before = {
        p: (_REPO_ROOT / p).read_bytes()
        for p in _RUNTIME_JSON
        if (_REPO_ROOT / p).exists()
    }

    result = subprocess.run(
        [sys.executable, "scripts/mock_line.py", "說明"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"CLI help 不可失敗：{result.stderr}"
    assert "指令說明" in result.stdout
    assert "確認改名" in result.stdout and "確認搬移" in result.stdout

    runtime_after = {
        p: (_REPO_ROOT / p).read_bytes()
        for p in _RUNTIME_JSON
        if (_REPO_ROOT / p).exists()
    }
    assert runtime_after == runtime_before, "CLI help 不可改動 runtime JSON"


# ---------------------------------------------------------------------------
# Task 4 — Runtime / gitignore smoke
# ---------------------------------------------------------------------------


def test_runtime_json_paths_are_gitignored():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for runtime_file in _RUNTIME_JSON:
        assert runtime_file in gitignore


def test_git_does_not_track_runtime_files():
    result = subprocess.run(
        ["git", "ls-files", "runtime/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", "runtime/ 下不可有任何被 git 追蹤的檔案"
