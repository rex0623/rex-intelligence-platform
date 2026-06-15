"""Phase 20B 測試：make_approval_manager() factory。

驗證重點：
- APPROVAL_STORE_BACKEND="json"  → 回傳 ApprovalManager（JSON backend）
- APPROVAL_STORE_BACKEND="sqlite" → 回傳 ApprovalManager（SQLite backend）
- APPROVAL_STORE_BACKEND 未知值   → raise ValueError
- json backend 下 rip.db 不建立（regression）
- sqlite backend 下 rip.db 建立（smoke）
- 回傳的 ApprovalManager 可正常 create_approval / get / approve
- factory 呼叫時讀取 settings（monkeypatch 有效）
"""

from pathlib import Path

import pytest

from app.core.approval_manager_factory import make_approval_manager


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def test_json_backend_returns_approval_manager(tmp_path: Path, monkeypatch):
    """APPROVAL_STORE_BACKEND='json' → 回傳 ApprovalManager。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from app.approvals.manager import ApprovalManager
    manager = make_approval_manager()
    assert isinstance(manager, ApprovalManager)


def test_sqlite_backend_returns_approval_manager(tmp_path: Path, monkeypatch):
    """APPROVAL_STORE_BACKEND='sqlite' → 回傳 ApprovalManager（SQLite-backed）。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    from app.approvals.manager import ApprovalManager
    manager = make_approval_manager()
    assert isinstance(manager, ApprovalManager)


def test_unknown_backend_raises_value_error(monkeypatch):
    """未知 backend 值 → raise ValueError。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "unknown")

    with pytest.raises(ValueError, match="Unknown APPROVAL_STORE_BACKEND"):
        make_approval_manager()


# ---------------------------------------------------------------------------
# rip.db isolation
# ---------------------------------------------------------------------------


def test_json_backend_does_not_create_rip_db(tmp_path: Path, monkeypatch):
    """APPROVAL_STORE_BACKEND='json' → rip.db 不建立。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    make_approval_manager()
    assert not (tmp_path / "rip.db").exists()


def test_sqlite_backend_creates_rip_db_on_write(tmp_path: Path, monkeypatch):
    """APPROVAL_STORE_BACKEND='sqlite' → create_approval 後 rip.db 存在。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    manager.create_approval({"workflow_id": "wf-smoke", "title": "factory smoke"})
    assert (tmp_path / "rip.db").exists()


# ---------------------------------------------------------------------------
# Functional smoke — returned manager is fully operational
# ---------------------------------------------------------------------------


def test_json_manager_create_and_get(tmp_path: Path, monkeypatch):
    """json backend manager: create_approval → get → status=pending。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    approval = manager.create_approval({"workflow_id": "wf-json", "title": "test"})
    fetched = manager.get(approval.approval_id)
    assert fetched is not None
    assert fetched.status == "pending"


def test_json_manager_approve(tmp_path: Path, monkeypatch):
    """json backend manager: create → approve → status=approved。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    approval = manager.create_approval({"workflow_id": "wf-approve", "title": "test"})
    approved = manager.approve(approval.approval_id)
    assert approved.status == "approved"


def test_sqlite_manager_create_and_get(tmp_path: Path, monkeypatch):
    """sqlite backend manager: create_approval → get → status=pending。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    approval = manager.create_approval({"workflow_id": "wf-sqlite", "title": "test"})
    fetched = manager.get(approval.approval_id)
    assert fetched is not None
    assert fetched.status == "pending"


def test_sqlite_manager_approve(tmp_path: Path, monkeypatch):
    """sqlite backend manager: create → approve → status=approved。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    approval = manager.create_approval({"workflow_id": "wf-sqlite-approve", "title": "test"})
    approved = manager.approve(approval.approval_id)
    assert approved.status == "approved"


def test_sqlite_manager_reject(tmp_path: Path, monkeypatch):
    """sqlite backend manager: create → reject → status=rejected。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    manager = make_approval_manager()
    approval = manager.create_approval({"workflow_id": "wf-sqlite-reject", "title": "test"})
    rejected = manager.reject(approval.approval_id)
    assert rejected.status == "rejected"


# ---------------------------------------------------------------------------
# Factory reads settings at call time (monkeypatch effective)
# ---------------------------------------------------------------------------


def test_factory_reads_settings_at_call_time(tmp_path: Path, monkeypatch):
    """factory 每次呼叫時讀取 settings，不快取 backend 值。"""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "RUNTIME_DIR", str(tmp_path))

    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "json")
    m1 = make_approval_manager()

    monkeypatch.setattr(cfg.settings, "APPROVAL_STORE_BACKEND", "sqlite")
    m2 = make_approval_manager()

    # m1 uses JSON backend (no _backend attribute injected), m2 uses SQLite
    assert m1._backend is None  # JSON path: no injected backend
    assert m2._backend is not None  # SQLite path: SqliteApprovalStore injected
