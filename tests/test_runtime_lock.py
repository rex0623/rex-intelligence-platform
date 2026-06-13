"""Phase 17B 測試：Runtime Lock / Concurrency Guard。

涵蓋：
- app.core.runtime_lock 基礎功能（建立、釋放、busy 時拋例外）
- _LOCK_BUSY_REPLY 內容驗證
- help / preview 在 lock busy 時仍可正常回覆（不需要 lock）
- planning / approval / destructive / rollback 在 lock busy 時回覆 runtime_lock_busy

Testing strategy for lock contention（fcntl.flock 在同一 process 內為 re-entrant）：
  - Infrastructure tests：monkeypatch fcntl.flock → 拋 BlockingIOError，
    確認 RuntimeLockBusy 正確拋出。
  - mock_line_payload tests：monkeypatch acquire_runtime_lock → _always_busy
    context manager，確認 mock_line_payload 正確回傳 _LOCK_BUSY_REPLY。
"""

import contextlib
import subprocess
from pathlib import Path

import pytest

from app.approvals.manager import approval_manager
from app.core.config import settings
from app.core.runtime_lock import RuntimeLockBusy, acquire_runtime_lock
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog
from scripts.mock_line import _LOCK_BUSY_REPLY, command_help_text, mock_line_payload

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helper: context manager that always simulates a busy lock
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _always_busy():
    """Simulates acquire_runtime_lock when another process holds the lock."""
    raise RuntimeLockBusy("runtime_lock_busy")
    yield  # unreachable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    return tmp_path


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
# Infrastructure: app.core.runtime_lock
# ===========================================================================


def test_runtime_lock_module_importable():
    """RuntimeLockBusy 與 acquire_runtime_lock 可 import 且型別正確。"""
    assert callable(acquire_runtime_lock)
    assert issubclass(RuntimeLockBusy, RuntimeError)


def test_acquire_creates_lock_file(isolated_runtime):
    """acquire_runtime_lock() 在 RUNTIME_DIR 建立 rip.lock。"""
    lock_path = isolated_runtime / "rip.lock"
    with acquire_runtime_lock():
        assert lock_path.exists(), "rip.lock 應在 lock 持有期間存在"


def test_lock_released_after_context(isolated_runtime):
    """context 結束後可再次 acquire（sequential re-acquire）。"""
    with acquire_runtime_lock():
        pass
    # 同一 process 依序呼叫，first context 結束後 second 可成功
    with acquire_runtime_lock():
        pass


def test_lock_busy_raises_runtime_lock_busy(isolated_runtime, monkeypatch):
    """BlockingIOError from flock 應轉為 RuntimeLockBusy。"""
    import app.core.runtime_lock as rl

    def _blocking(fd, op):
        raise BlockingIOError("Simulated lock busy")

    monkeypatch.setattr(rl.fcntl, "flock", _blocking)

    with pytest.raises(RuntimeLockBusy):
        with acquire_runtime_lock():
            pass


def test_lock_path_follows_settings_runtime_dir(isolated_runtime):
    """Lock file 路徑為 settings.RUNTIME_DIR / rip.lock。"""
    expected = isolated_runtime / "rip.lock"
    with acquire_runtime_lock():
        assert expected.exists()


def test_runtime_lock_file_covered_by_gitignore():
    """runtime/rip.lock 不被 git 追蹤（由 runtime/ gitignore 覆蓋）。"""
    result = subprocess.run(
        ["git", "ls-files", "runtime/rip.lock"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", "runtime/rip.lock 不可被 git 追蹤"


# ===========================================================================
# _LOCK_BUSY_REPLY content
# ===========================================================================


def test_lock_busy_reply_contains_required_content():
    """_LOCK_BUSY_REPLY 含中文提示、reason code、小雷收到前綴。"""
    assert "小雷收到" in _LOCK_BUSY_REPLY
    assert "另一個操作" in _LOCK_BUSY_REPLY
    assert "runtime_lock_busy" in _LOCK_BUSY_REPLY


# ===========================================================================
# Help / Preview：lock busy 時仍可正常回覆（不需要 lock）
# ===========================================================================


def test_help_works_when_lock_is_busy(monkeypatch, isolated_approvals):
    """說明 / help 在 lock busy 時仍回傳 command_help_text()（不走 lock 路徑）。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)

    for cmd in ("說明", "help", "/help", "指令說明"):
        result = mock_line_payload(cmd)
        assert result == command_help_text(), (
            f"「{cmd}」在 lock busy 時應回傳 help text，實際：{result[:80]}"
        )


def test_preview_rename_rollback_works_when_lock_is_busy(monkeypatch, rename_log):
    """預覽回滾改名 在 lock busy 時仍回覆（不走 lock 路徑，純讀取）。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload(
        "預覽回滾改名 FAKE-TX-LOCKTEST-001", transaction_log=rename_log
    )
    assert "runtime_lock_busy" not in result, "預覽回滾改名 不應被 lock 阻擋"
    assert "找不到" in result or "transaction" in result.lower()


def test_preview_move_rollback_works_when_lock_is_busy(monkeypatch, move_log):
    """預覽回滾搬移 在 lock busy 時仍回覆（不走 lock 路徑，純讀取）。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload(
        "預覽回滾搬移 FAKE-TX-LOCKTEST-001", move_transaction_log=move_log
    )
    assert "runtime_lock_busy" not in result, "預覽回滾搬移 不應被 lock 阻擋"
    assert "找不到" in result or "transaction" in result.lower()


# ===========================================================================
# Locked command paths → return _LOCK_BUSY_REPLY when lock busy
# ===========================================================================


def test_confirm_rename_returns_lock_busy_message(monkeypatch):
    """確認改名 在 lock busy 時回傳 _LOCK_BUSY_REPLY，不觸發 approval / rename。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("確認改名 FAKE-APPROVAL-LOCKTEST-001")
    assert result == _LOCK_BUSY_REPLY


def test_rollback_rename_returns_lock_busy_message(monkeypatch):
    """回滾改名 在 lock busy 時回傳 _LOCK_BUSY_REPLY，不觸發 rollback。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("回滾改名 FAKE-TX-LOCKTEST-002")
    assert result == _LOCK_BUSY_REPLY


def test_confirm_move_returns_lock_busy_message(monkeypatch):
    """確認搬移 在 lock busy 時回傳 _LOCK_BUSY_REPLY，不觸發 approval / move。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("確認搬移 FAKE-APPROVAL-LOCKTEST-001")
    assert result == _LOCK_BUSY_REPLY


def test_rollback_move_returns_lock_busy_message(monkeypatch):
    """回滾搬移 在 lock busy 時回傳 _LOCK_BUSY_REPLY，不觸發 rollback。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("回滾搬移 FAKE-TX-LOCKTEST-002")
    assert result == _LOCK_BUSY_REPLY


def test_planning_command_returns_lock_busy_message(monkeypatch):
    """整理檔名 在 lock busy 時回傳 _LOCK_BUSY_REPLY（lock 在 planning 路徑）。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("整理檔名")
    assert result == _LOCK_BUSY_REPLY


def test_generic_router_returns_lock_busy_message(monkeypatch):
    """確認 fake_id（generic router path）在 lock busy 時回傳 _LOCK_BUSY_REPLY。"""
    import scripts.mock_line as ml

    monkeypatch.setattr(ml, "acquire_runtime_lock", _always_busy)
    result = mock_line_payload("確認 00000000-0000-0000-0000-000000000000")
    assert result == _LOCK_BUSY_REPLY
