"""Phase 21B tests: ApprovalManager.prune_approvals().

驗證重點：
- remove_expired=True 移除 status=expired
- remove_expired=True 移除 expires_at < now 但 status=pending（lazy expiry）
- remove_expired=True 保留 expires_at > now 的 pending approval
- remove_executed=False（預設）保留 executed approval
- remove_executed=True 移除 payload.execution_status == "executed"
- remove_rejected=False（預設）保留 rejected approval
- remove_rejected=True 移除 rejected approval
- max_age_days 移除超齡 approval
- max_age_days 不移除仍 live-pending（未過期）的 approval
- dry_run=True 不呼叫 _save_store()
- dry_run=False 有刪除時 _save_store() 只呼叫一次
- dry_run=False 無刪除時 _save_store() 不呼叫
- 空 store no-op
- ApprovalPruneResult 欄位正確
- JSON backend prune 後 approvals.json 正確反映結果
- SQLite backend prune 後 DB 正確反映結果
- 多 flag 組合
- dry_run=True 不修改 _store dict
- pruned_approval_ids 正確
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.approvals.manager import ApprovalManager
from app.approvals.schemas import Approval, ApprovalPruneResult

# ---------------------------------------------------------------------------
# Fixed reference times
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
_PAST = _NOW - timedelta(hours=2)       # 2h ago — expired
_FUTURE = _NOW + timedelta(hours=2)     # 2h from now — valid
_OLD = _NOW - timedelta(days=60)        # 60 days ago — old


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approval(
    approval_id: str = "aid-001",
    status: str = "pending",
    expires_at: datetime | None = _FUTURE,
    created_at: datetime = _NOW,
    payload: dict | None = None,
) -> Approval:
    return Approval(
        approval_id=approval_id,
        workflow_id="wf-test",
        status=status,
        created_at=created_at,
        expires_at=expires_at,
        payload=payload,
    )


def _manager(tmp_path: Path) -> ApprovalManager:
    """Return a fresh JSON-backed ApprovalManager using tmp_path."""
    return ApprovalManager(store_path=tmp_path / "approvals.json")


def _manager_with(tmp_path: Path, approvals: list[Approval]) -> ApprovalManager:
    """Return a manager pre-loaded with the given approvals."""
    mgr = _manager(tmp_path)
    mgr._store = {a.approval_id: a for a in approvals}
    return mgr


# ---------------------------------------------------------------------------
# 1. remove_expired=True removes status=expired
# ---------------------------------------------------------------------------


def test_prune_removes_status_expired(tmp_path):
    a = _approval("exp-1", status="expired")
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.pruned_count == 1
    assert result.pruned_expired == 1
    assert "exp-1" not in mgr._store


# ---------------------------------------------------------------------------
# 2. remove_expired=True removes expires_at < now but status=pending (lazy)
# ---------------------------------------------------------------------------


def test_prune_removes_lazy_expired_pending(tmp_path):
    a = _approval("lazy-1", status="pending", expires_at=_PAST)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.pruned_count == 1
    assert result.pruned_expired == 1
    assert "lazy-1" not in mgr._store


# ---------------------------------------------------------------------------
# 3. remove_expired=True retains expires_at > now pending
# ---------------------------------------------------------------------------


def test_prune_retains_not_yet_expired_pending(tmp_path):
    a = _approval("valid-1", status="pending", expires_at=_FUTURE)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.pruned_count == 0
    assert result.retained_count == 1
    assert "valid-1" in mgr._store


# ---------------------------------------------------------------------------
# 4. remove_executed=False (default) retains executed approval
# ---------------------------------------------------------------------------


def test_prune_executed_default_retained(tmp_path):
    payload = {"execution_status": "executed", "workflow_id": "wf-1"}
    a = _approval("exec-1", status="approved", payload=payload)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, remove_executed=False, now=_NOW)
    assert result.pruned_count == 0
    assert "exec-1" in mgr._store


# ---------------------------------------------------------------------------
# 5. remove_executed=True removes executed approval
# ---------------------------------------------------------------------------


def test_prune_executed_removed_when_flag(tmp_path):
    payload = {"execution_status": "executed", "workflow_id": "wf-1"}
    a = _approval("exec-2", status="approved", payload=payload)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, remove_executed=True, now=_NOW)
    assert result.pruned_count == 1
    assert result.pruned_executed == 1
    assert "exec-2" not in mgr._store


# ---------------------------------------------------------------------------
# 6. remove_rejected=False (default) retains rejected approval
# ---------------------------------------------------------------------------


def test_prune_rejected_default_retained(tmp_path):
    a = _approval("rej-1", status="rejected")
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, remove_rejected=False, now=_NOW)
    assert result.pruned_count == 0
    assert "rej-1" in mgr._store


# ---------------------------------------------------------------------------
# 7. remove_rejected=True removes rejected approval
# ---------------------------------------------------------------------------


def test_prune_rejected_removed_when_flag(tmp_path):
    a = _approval("rej-2", status="rejected")
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, remove_rejected=True, now=_NOW)
    assert result.pruned_count == 1
    assert result.pruned_rejected == 1
    assert "rej-2" not in mgr._store


# ---------------------------------------------------------------------------
# 8. max_age_days removes old non-pending approval
# ---------------------------------------------------------------------------


def test_prune_max_age_days_removes_old(tmp_path):
    # approved 60 days ago, expires_at in future (not expired) — removed by max_age_days only
    a = _approval("old-1", status="approved", created_at=_OLD, expires_at=_FUTURE)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, max_age_days=30, now=_NOW)
    assert result.pruned_count == 1
    assert result.pruned_old == 1
    assert result.pruned_expired == 0
    assert "old-1" not in mgr._store


# ---------------------------------------------------------------------------
# 9. max_age_days does NOT remove live-pending approval (not expired)
# ---------------------------------------------------------------------------


def test_prune_max_age_days_retains_live_pending(tmp_path):
    # pending, created 60 days ago, but expires_at is in the future (still valid)
    a = _approval("live-pend-1", status="pending", created_at=_OLD, expires_at=_FUTURE)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, max_age_days=30, now=_NOW)
    assert result.pruned_count == 0
    assert "live-pend-1" in mgr._store


# ---------------------------------------------------------------------------
# 10. dry_run=True does not call _save_store()
# ---------------------------------------------------------------------------


def test_prune_dry_run_no_save(tmp_path):
    a = _approval("exp-3", status="expired")
    mgr = _manager_with(tmp_path, [a])
    mgr._save_store = MagicMock()
    result = mgr.prune_approvals(dry_run=True, now=_NOW)
    mgr._save_store.assert_not_called()
    assert result.dry_run is True
    assert result.pruned_count == 1  # counted but not applied


# ---------------------------------------------------------------------------
# 11. dry_run=False with pruning calls _save_store() exactly once
# ---------------------------------------------------------------------------


def test_prune_apply_save_called_once(tmp_path):
    a1 = _approval("exp-4a", status="expired")
    a2 = _approval("exp-4b", status="expired")
    mgr = _manager_with(tmp_path, [a1, a2])
    mgr._save_store = MagicMock()
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    mgr._save_store.assert_called_once()
    assert result.pruned_count == 2


# ---------------------------------------------------------------------------
# 12. dry_run=False with nothing to prune does not call _save_store()
# ---------------------------------------------------------------------------


def test_prune_nothing_to_prune_no_save(tmp_path):
    a = _approval("valid-2", status="pending", expires_at=_FUTURE)
    mgr = _manager_with(tmp_path, [a])
    mgr._save_store = MagicMock()
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    mgr._save_store.assert_not_called()
    assert result.pruned_count == 0


# ---------------------------------------------------------------------------
# 13. Empty store no-op
# ---------------------------------------------------------------------------


def test_prune_empty_store_noop(tmp_path):
    mgr = _manager(tmp_path)
    mgr._save_store = MagicMock()
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    mgr._save_store.assert_not_called()
    assert result.pruned_count == 0
    assert result.retained_count == 0
    assert result.total_before == 0
    assert result.total_after == 0


# ---------------------------------------------------------------------------
# 14. ApprovalPruneResult fields correct
# ---------------------------------------------------------------------------


def test_prune_result_fields(tmp_path):
    exp = _approval("r-exp", status="expired")
    valid = _approval("r-valid", status="approved", expires_at=_FUTURE)
    exec_a = _approval("r-exec", status="approved",
                       payload={"execution_status": "executed"})
    rej = _approval("r-rej", status="rejected")

    mgr = _manager_with(tmp_path, [exp, valid, exec_a, rej])
    result = mgr.prune_approvals(
        dry_run=True,
        remove_executed=True,
        remove_rejected=True,
        now=_NOW,
    )

    assert isinstance(result, ApprovalPruneResult)
    assert result.dry_run is True
    assert result.total_before == 4
    assert result.pruned_count == 3  # exp + exec_a + rej
    assert result.pruned_expired == 1
    assert result.pruned_executed == 1
    assert result.pruned_rejected == 1
    assert result.pruned_old == 0
    assert result.retained_count == 1
    assert result.total_after == 1
    assert set(result.pruned_approval_ids) == {"r-exp", "r-exec", "r-rej"}


# ---------------------------------------------------------------------------
# 15. JSON backend: prune updates approvals.json
# ---------------------------------------------------------------------------


def test_prune_json_backend_updates_file(tmp_path):
    exp = _approval("j-exp", status="expired")
    valid = _approval("j-valid", status="pending", expires_at=_FUTURE)

    mgr = _manager_with(tmp_path, [exp, valid])
    mgr._save_store()  # write initial state to disk

    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.pruned_count == 1

    # Re-load from disk to verify file was updated
    mgr2 = _manager(tmp_path)
    assert "j-exp" not in mgr2._store
    assert "j-valid" in mgr2._store


# ---------------------------------------------------------------------------
# 16. SQLite backend: prune updates DB
# ---------------------------------------------------------------------------


def test_prune_sqlite_backend_updates_db(tmp_path, monkeypatch):
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from app.approvals.manager import ApprovalManager as AM
    from app.core.sqlite_approval_store import SqliteApprovalStore

    store = SqliteApprovalStore()
    mgr = AM(_store_backend=store)

    exp = _approval("s-exp", status="expired")
    valid = _approval("s-valid", status="pending", expires_at=_FUTURE)
    mgr._store = {a.approval_id: a for a in [exp, valid]}
    mgr._save_store()  # write initial state to DB

    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.pruned_count == 1

    # Re-load from DB to verify
    store2 = SqliteApprovalStore()
    loaded = store2.load(tmp_path / "rip.db")
    assert "s-exp" not in loaded
    assert "s-valid" in loaded


# ---------------------------------------------------------------------------
# 17. Combined flags (expired + executed + rejected + max_age)
# ---------------------------------------------------------------------------


def test_prune_combined_flags(tmp_path):
    exp = _approval("c-exp", status="expired")
    exec_a = _approval("c-exec", status="approved",
                       payload={"execution_status": "executed"})
    rej = _approval("c-rej", status="rejected")
    old_app = _approval("c-old", status="approved", created_at=_OLD, expires_at=_PAST)
    valid = _approval("c-valid", status="pending", expires_at=_FUTURE)

    mgr = _manager_with(tmp_path, [exp, exec_a, rej, old_app, valid])
    result = mgr.prune_approvals(
        dry_run=False,
        remove_expired=True,
        remove_executed=True,
        remove_rejected=True,
        max_age_days=30,
        now=_NOW,
    )
    # exp + old_app are both expired → pruned_expired=2
    # exec_a not expired, but executed → pruned_executed=1
    # rej not expired, not executed, is rejected → pruned_rejected=1
    # valid → retained
    assert result.pruned_count == 4
    assert result.retained_count == 1
    assert "c-valid" in mgr._store
    assert "c-exp" not in mgr._store
    assert "c-exec" not in mgr._store
    assert "c-rej" not in mgr._store
    assert "c-old" not in mgr._store


# ---------------------------------------------------------------------------
# 18. dry_run=True does not modify _store dict
# ---------------------------------------------------------------------------


def test_prune_dry_run_store_unchanged(tmp_path):
    a = _approval("dr-1", status="expired")
    mgr = _manager_with(tmp_path, [a])
    before = dict(mgr._store)
    mgr.prune_approvals(dry_run=True, now=_NOW)
    assert mgr._store == before


# ---------------------------------------------------------------------------
# 19. pruned_approval_ids sorted and correct
# ---------------------------------------------------------------------------


def test_prune_approval_ids_in_result(tmp_path):
    a1 = _approval("z-exp", status="expired")
    a2 = _approval("a-exp", status="expired")
    mgr = _manager_with(tmp_path, [a1, a2])
    result = mgr.prune_approvals(dry_run=True, now=_NOW)
    assert result.pruned_approval_ids == ["a-exp", "z-exp"]


# ---------------------------------------------------------------------------
# 20. total_before / total_after / pruned_count / retained_count consistency
# ---------------------------------------------------------------------------


def test_prune_total_counts_consistent(tmp_path):
    approvals = [
        _approval(f"aid-{i}", status="expired") for i in range(5)
    ] + [
        _approval(f"keep-{i}", status="pending", expires_at=_FUTURE) for i in range(3)
    ]
    mgr = _manager_with(tmp_path, approvals)
    result = mgr.prune_approvals(dry_run=False, now=_NOW)
    assert result.total_before == 8
    assert result.pruned_count == 5
    assert result.retained_count == 3
    assert result.total_after == 3
    assert result.total_after == result.retained_count
    assert result.pruned_count + result.retained_count == result.total_before


# ---------------------------------------------------------------------------
# 21. max_age_days: pending with expires_at=None (no expiry) is still live
# ---------------------------------------------------------------------------


def test_prune_max_age_days_retains_pending_no_expires(tmp_path):
    # pending approval with no expires_at — still live
    a = _approval("no-exp", status="pending", created_at=_OLD, expires_at=None)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=False, max_age_days=30, now=_NOW)
    assert result.pruned_count == 0
    assert "no-exp" in mgr._store


# ---------------------------------------------------------------------------
# 22. prune_approval_ids empty when nothing pruned
# ---------------------------------------------------------------------------


def test_prune_approval_ids_empty_when_nothing_pruned(tmp_path):
    a = _approval("keep-it", status="pending", expires_at=_FUTURE)
    mgr = _manager_with(tmp_path, [a])
    result = mgr.prune_approvals(dry_run=True, now=_NOW)
    assert result.pruned_approval_ids == []
    assert result.pruned_count == 0
