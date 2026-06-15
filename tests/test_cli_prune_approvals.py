"""Phase 21B tests: scripts/prune_approvals.py CLI.

驗證重點：
- 預設 dry-run 不修改資料
- --apply 實際 prune
- --remove-executed flag 生效
- --remove-rejected flag 生效
- --max-age-days 生效
- --json-report 輸出合法 JSON
- --apply 會 acquire runtime lock
- dry-run 不 acquire runtime lock（lock 被持有時仍可執行）
- lock busy 時 exit code 1
- script 可 import 無 side effects
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.approvals.manager import ApprovalManager
from app.approvals.schemas import Approval

_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
_PAST = _NOW - timedelta(hours=2)
_FUTURE = _NOW + timedelta(hours=2)
_OLD = _NOW - timedelta(days=60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approval(
    approval_id: str = "cli-aid",
    status: str = "pending",
    expires_at: datetime | None = _FUTURE,
    created_at: datetime = _NOW,
    payload: dict | None = None,
) -> Approval:
    return Approval(
        approval_id=approval_id,
        workflow_id="wf-cli",
        status=status,
        created_at=created_at,
        expires_at=expires_at,
        payload=payload,
    )


def _mgr_with(tmp_path: Path, approvals: list[Approval]) -> ApprovalManager:
    mgr = ApprovalManager(store_path=tmp_path / "approvals.json")
    mgr._store = {a.approval_id: a for a in approvals}
    mgr._save_store()
    return mgr


def _run(argv: list[str], tmp_path: Path) -> int:
    """Run prune_approvals.main() with a monkeypatched approval manager."""
    from scripts.prune_approvals import main
    return main(argv)


# ---------------------------------------------------------------------------
# 16. CLI default is dry-run — does not modify data
# ---------------------------------------------------------------------------


def test_cli_default_dry_run_no_change(tmp_path, monkeypatch):
    exp = _approval("cli-exp", status="expired")
    _mgr_with(tmp_path, [exp])

    # Monkeypatch make_approval_manager to use our tmp_path
    from app.approvals import manager as mgr_mod
    monkeypatch.setattr(mgr_mod, "get_approval_store_path",
                        lambda: tmp_path / "approvals.json")

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        rc = main([])  # default: no --apply
    assert rc == 0
    # No changes: expired approval still on disk
    mgr2 = ApprovalManager(store_path=tmp_path / "approvals.json")
    assert "cli-exp" in mgr2._store


# ---------------------------------------------------------------------------
# 17. CLI --apply actually prunes
# ---------------------------------------------------------------------------


def test_cli_apply_prunes(tmp_path):
    exp = _approval("a-exp", status="expired")
    valid = _approval("a-valid", status="pending", expires_at=_FUTURE)
    mgr = _mgr_with(tmp_path, [exp, valid])

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            mock_lock.return_value.__enter__ = lambda s: None
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            rc = main(["--apply"])

    assert rc == 0
    mgr2 = ApprovalManager(store_path=tmp_path / "approvals.json")
    assert "a-exp" not in mgr2._store
    assert "a-valid" in mgr2._store


# ---------------------------------------------------------------------------
# 18. CLI --remove-executed passes through
# ---------------------------------------------------------------------------


def test_cli_remove_executed(tmp_path):
    payload = {"execution_status": "executed"}
    exec_a = _approval("e-exec", status="approved", expires_at=_FUTURE, payload=payload)
    valid = _approval("e-valid", status="pending", expires_at=_FUTURE)
    _mgr_with(tmp_path, [exec_a, valid])

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            mock_lock.return_value.__enter__ = lambda s: None
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            rc = main(["--apply", "--remove-executed"])

    assert rc == 0
    mgr2 = ApprovalManager(store_path=tmp_path / "approvals.json")
    assert "e-exec" not in mgr2._store
    assert "e-valid" in mgr2._store


# ---------------------------------------------------------------------------
# 19. CLI --remove-rejected passes through
# ---------------------------------------------------------------------------


def test_cli_remove_rejected(tmp_path):
    rej = _approval("r-rej", status="rejected", expires_at=_FUTURE)
    valid = _approval("r-valid", status="pending", expires_at=_FUTURE)
    _mgr_with(tmp_path, [rej, valid])

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            mock_lock.return_value.__enter__ = lambda s: None
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            rc = main(["--apply", "--remove-rejected"])

    assert rc == 0
    mgr2 = ApprovalManager(store_path=tmp_path / "approvals.json")
    assert "r-rej" not in mgr2._store
    assert "r-valid" in mgr2._store


# ---------------------------------------------------------------------------
# 20. CLI --max-age-days passes through
# ---------------------------------------------------------------------------


def test_cli_max_age_days(tmp_path):
    old_app = _approval("m-old", status="approved", created_at=_OLD, expires_at=_PAST)
    live = _approval("m-live", status="pending", created_at=_OLD, expires_at=_FUTURE)
    _mgr_with(tmp_path, [old_app, live])

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            mock_lock.return_value.__enter__ = lambda s: None
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            rc = main(["--apply", "--max-age-days", "30"])

    assert rc == 0
    mgr2 = ApprovalManager(store_path=tmp_path / "approvals.json")
    # old_app: approved, expires_at in past → removed (expired first)
    assert "m-old" not in mgr2._store
    # live: pending + future expires_at → kept (live-pending protection)
    assert "m-live" in mgr2._store


# ---------------------------------------------------------------------------
# 21. CLI --json-report outputs valid JSON
# ---------------------------------------------------------------------------


def test_cli_json_report(tmp_path, capsys):
    exp = _approval("j-exp", status="expired")
    _mgr_with(tmp_path, [exp])

    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        rc = main(["--json-report"])

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "dry_run" in data
    assert "pruned_count" in data
    assert "pruned_expired" in data
    assert "pruned_approval_ids" in data
    assert data["dry_run"] is True  # default dry-run


# ---------------------------------------------------------------------------
# 22. CLI --apply acquires runtime lock
# ---------------------------------------------------------------------------


def test_cli_apply_acquires_lock(tmp_path):
    _mgr_with(tmp_path, [])
    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            mock_lock.return_value.__enter__ = lambda s: None
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            main(["--apply"])
        mock_lock.assert_called_once()


# ---------------------------------------------------------------------------
# 23. CLI dry-run does NOT acquire runtime lock (even if lock is held)
# ---------------------------------------------------------------------------


def test_cli_dry_run_no_lock(tmp_path):
    _mgr_with(tmp_path, [])
    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock") as mock_lock:
            rc = main([])  # dry-run
        mock_lock.assert_not_called()
    assert rc == 0


# ---------------------------------------------------------------------------
# 24. CLI lock busy → exit code 1
# ---------------------------------------------------------------------------


def test_cli_lock_busy_exit_1(tmp_path):
    from app.core.runtime_lock import RuntimeLockBusy

    _mgr_with(tmp_path, [])
    real_mgr = ApprovalManager(store_path=tmp_path / "approvals.json")

    with patch("app.core.approval_manager_factory.make_approval_manager",
               return_value=real_mgr):
        from scripts.prune_approvals import main
        with patch("app.core.runtime_lock.acquire_runtime_lock",
                   side_effect=RuntimeLockBusy("busy")):
            rc = main(["--apply"])

    assert rc == 1


# ---------------------------------------------------------------------------
# 25. Script importable without side effects
# ---------------------------------------------------------------------------


def test_cli_no_import_side_effects():
    import importlib
    import scripts.prune_approvals as mod
    importlib.reload(mod)
    assert callable(mod.main)
    assert callable(mod._build_parser)
