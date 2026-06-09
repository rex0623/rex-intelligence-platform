import json
from pathlib import Path

import pytest

from app.approvals.manager import ApprovalManager


def test_create_and_get_approval(tmp_path: Path):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    plan = {"workflow_id": "wf1", "title": "test"}

    approval = manager.create_approval(plan, ttl_minutes=1)
    assert approval.approval_id is not None

    got = manager.get(approval.approval_id)
    assert got is not None
    assert got.status == "pending"


def test_approve_and_reject_transitions(tmp_path: Path):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    plan = {"workflow_id": "wf2", "title": "t2"}

    approval = manager.create_approval(plan, ttl_minutes=1)
    aid = approval.approval_id

    approved = manager.approve(aid)
    assert approved.status == "approved"
    with pytest.raises(ValueError):
        manager.approve(aid)

    approval2 = manager.create_approval({"workflow_id": "wf3"}, ttl_minutes=1)
    aid2 = approval2.approval_id
    rejected = manager.reject(aid2)
    assert rejected.status == "rejected"
    with pytest.raises(ValueError):
        manager.approve(aid2)


def test_persistent_store_reads_existing_approval(tmp_path: Path):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    plan = {"workflow_id": "wf4", "title": "persistent"}
    approval = manager.create_approval(plan, ttl_minutes=1)
    assert store_file.exists()

    # Recreate manager to simulate new process
    manager2 = ApprovalManager(store_path=store_file)
    got = manager2.get(approval.approval_id)
    assert got is not None
    assert got.workflow_id == "wf4"
    assert got.status == "pending"


def test_file_updates_after_approve(tmp_path: Path):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    approval = manager.create_approval({"workflow_id": "wf5"}, ttl_minutes=1)
    aid = approval.approval_id

    manager.approve(aid)
    raw = json.loads(store_file.read_text(encoding="utf-8"))
    saved = next(item for item in raw if item["approval_id"] == aid)

    assert saved["status"] == "approved"


def test_nonexistent_approval_get_returns_none_and_keyerror_on_actions(tmp_path: Path):
    manager = ApprovalManager(store_path=tmp_path / "approvals.json")
    assert manager.get("no-such-id") is None
    with pytest.raises(KeyError):
        manager.approve("no-such-id")
    with pytest.raises(KeyError):
        manager.reject("no-such-id")
