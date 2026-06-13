"""Phase 17D — Operator Preflight Validation.

Safe preflight（low-write）：驗證 operator 本機環境是否滿足 RIP 執行條件。

允許的寫入：
  - 建立 RUNTIME_DIR 目錄（mkdir only）
  - 寫入並立即刪除 .preflight_write_test（寫入測試，非 JSON state）

不會做的事：
  - 不呼叫 acquire_runtime_lock()（不取得 fcntl lock）
  - 不建立 approvals.json / rename_transactions.json / move_transactions.json
  - 不修改任何 workflow state
  - SAFE_PDF_ROOT 不存在時只回報，不自動建立
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PreflightItem:
    """Result of a single preflight check."""

    name: str
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Individual check functions（可單獨測試）
# ---------------------------------------------------------------------------


def _check_python_version(version_info: tuple | None = None) -> PreflightItem:
    """Python 版本 ≥ 3.12。

    Args:
        version_info: 版本 tuple override（測試用）；None 時使用 sys.version_info。
    """
    if version_info is None:
        version_info = sys.version_info[:3]
    ok = version_info >= (3, 12)
    ver_str = ".".join(str(x) for x in version_info[:3])
    return PreflightItem(
        name="python_version",
        ok=ok,
        message=(
            f"Python {ver_str}"
            if ok
            else f"Python {ver_str}（需要 3.12 以上，請升級 Python）"
        ),
    )


def _check_fcntl() -> PreflightItem:
    """fcntl 模組可 import（Linux / macOS / WSL2 only）。"""
    try:
        import fcntl  # noqa: F401

        return PreflightItem(
            name="fcntl_available",
            ok=True,
            message="fcntl 可用（runtime lock 支援）",
        )
    except ImportError:
        return PreflightItem(
            name="fcntl_available",
            ok=False,
            message="fcntl 不可用（Windows native 不支援 runtime lock；請使用 WSL2 或 macOS）",
        )


def _check_safe_pdf_root(safe_pdf_root: Path) -> PreflightItem:
    """SAFE_PDF_ROOT 目錄存在。

    不存在時只回報失敗，不自動建立目錄。
    """
    exists = safe_pdf_root.is_dir()
    return PreflightItem(
        name="safe_pdf_root_exists",
        ok=exists,
        message=(
            str(safe_pdf_root)
            if exists
            else (
                f"SAFE_PDF_ROOT 目錄不存在：{safe_pdf_root}"
                f"（請建立目錄或設定正確的 SAFE_PDF_ROOT 環境變數）"
            )
        ),
    )


def _check_runtime_dir_writable(runtime_dir: Path) -> PreflightItem:
    """RUNTIME_DIR 存在或可建立，且可寫入。

    允許 mkdir（只建立目錄）；寫入測試使用 .preflight_write_test（非 JSON state），
    測試後立即刪除。不建立 approvals.json / transaction logs。
    """
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        test_file = runtime_dir / ".preflight_write_test"
        try:
            test_file.write_text("ok", encoding="utf-8")
        finally:
            test_file.unlink(missing_ok=True)
        return PreflightItem(
            name="runtime_dir_writable",
            ok=True,
            message=str(runtime_dir),
        )
    except OSError as e:
        return PreflightItem(
            name="runtime_dir_writable",
            ok=False,
            message=f"RUNTIME_DIR 不可寫入：{runtime_dir}（{e}）",
        )


def _check_git_ls_files(path: str, label: str, repo_root: Path) -> PreflightItem:
    """確認 path 下無任何被 git 追蹤的檔案（讀取 git index，不修改任何檔案）。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return PreflightItem(
                name=f"{label}_not_git_tracked",
                ok=False,
                message=f"git ls-files 失敗（非 git repo 或 git 不可用）：{result.stderr.strip()}",
            )
        ok = result.stdout.strip() == ""
        return PreflightItem(
            name=f"{label}_not_git_tracked",
            ok=ok,
            message=(
                f"{path} 未被 git 追蹤 ✓"
                if ok
                else f"{path} 下有被 git 追蹤的檔案，請確認 .gitignore 設定"
            ),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return PreflightItem(
            name=f"{label}_not_git_tracked",
            ok=False,
            message=f"無法執行 git ls-files：{e}",
        )


def _check_pyproject_console_scripts(repo_root: Path) -> PreflightItem:
    """pyproject.toml 已定義 rip console_scripts entry point。"""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return PreflightItem(
            name="pyproject_console_scripts",
            ok=False,
            message="pyproject.toml 不存在",
        )
    content = pyproject.read_text(encoding="utf-8")
    ok = 'rip = "scripts.mock_line:main"' in content
    return PreflightItem(
        name="pyproject_console_scripts",
        ok=ok,
        message=(
            'rip = "scripts.mock_line:main" 已設定'
            if ok
            else "pyproject.toml 缺少 rip console_scripts 設定（請確認 Phase 17A 已套用）"
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_operator_preflight(
    runtime_dir: Path | None = None,
    safe_pdf_root: Path | None = None,
    repo_root: Path | None = None,
    _python_version_info: tuple | None = None,
) -> list[PreflightItem]:
    """Run all operator preflight checks and return results.

    Safe preflight（low-write）：
    - 允許建立 RUNTIME_DIR 目錄（不寫 JSON state）
    - 不呼叫 acquire_runtime_lock()
    - 不建立 approvals.json / rename_transactions.json / move_transactions.json
    - SAFE_PDF_ROOT 不存在時只回報，不自動建立

    Args:
        runtime_dir:           RUNTIME_DIR override（None 使用 config 預設值）
        safe_pdf_root:         SAFE_PDF_ROOT override（None 使用 config 預設值）
        repo_root:             repo 根目錄 override（None 自動推導）
        _python_version_info:  Python 版本 tuple override（測試用）

    Returns:
        list[PreflightItem] — 每個 item 含 name / ok / message。
    """
    from app.core.config import get_runtime_dir, get_safe_pdf_root

    if runtime_dir is None:
        runtime_dir = get_runtime_dir()
    if safe_pdf_root is None:
        safe_pdf_root = get_safe_pdf_root()
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    return [
        _check_python_version(_python_version_info),
        _check_fcntl(),
        _check_safe_pdf_root(safe_pdf_root),
        _check_runtime_dir_writable(runtime_dir),
        _check_git_ls_files("runtime/", "runtime", repo_root),
        _check_git_ls_files("dist/", "dist", repo_root),
        _check_pyproject_console_scripts(repo_root),
    ]
