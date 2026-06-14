"""Phase 18B 測試：JsonApprovalStore JSON I/O helper。

驗證重點：
- approvals.json 仍是 array of approval dicts（schema 不變）
- payload 內 execution_status / executed_at / execution_transaction_id 保留
- corrupted JSON 回傳 {}，不 raise
- load/save 不產生 SQLite 或其他 runtime state
- 使用 tmp_path，不碰真實 runtime/
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.approvals.store import JsonApprovalStore
from app.approvals.schemas import Approval


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _make_approval(**kwargs) -> Approval:
    defaults = dict(
        approval_id="test-id-001",
        workflow_id="wf-test",
        status="pending",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        payload={"workflow_id": "wf-test", "title": "test"},
    )
    defaults.update(kwargs)
    return Approval(**defaults)


# ---------------------------------------------------------------------------
# load() 測試
# ---------------------------------------------------------------------------


def test_json_approval_store_load_nonexistent(tmp_path: Path):
    result = JsonApprovalStore.load(tmp_path / "approvals.json")
    assert result == {}


def test_json_approval_store_load_valid_json(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    approval = _make_approval(approval_id="aid-1", workflow_id="wf-1", status="pending")
    store_path.write_text(
        json.dumps([approval.model_dump(mode="json")], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = JsonApprovalStore.load(store_path)

    assert len(result) == 1
    assert "aid-1" in result
    loaded = result["aid-1"]
    assert loaded.approval_id == "aid-1"
    assert loaded.workflow_id == "wf-1"
    assert loaded.status == "pending"


def test_json_approval_store_load_corrupted_returns_empty(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    store_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

    result = JsonApprovalStore.load(store_path)

    assert result == {}


def test_json_approval_store_load_empty_array(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    store_path.write_text("[]", encoding="utf-8")

    result = JsonApprovalStore.load(store_path)

    assert result == {}


# ---------------------------------------------------------------------------
# save() 測試
# ---------------------------------------------------------------------------


def test_json_approval_store_save_creates_file(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    approval = _make_approval(approval_id="aid-2", workflow_id="wf-2")
    data = {"aid-2": approval}

    JsonApprovalStore.save(store_path, data)

    assert store_path.exists()


def test_json_approval_store_preserves_schema(tmp_path: Path):
    """save() 輸出必須是 array of approval dicts（schema 不變）。"""
    store_path = tmp_path / "approvals.json"
    approval = _make_approval(
        approval_id="aid-3",
        workflow_id="wf-3",
        status="approved",
        payload={"workflow_id": "wf-3", "title": "schema test"},
    )
    data = {"aid-3": approval}

    JsonApprovalStore.save(store_path, data)

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert isinstance(raw, list), "approvals.json must be a JSON array"
    assert len(raw) == 1
    entry = raw[0]
    assert entry["approval_id"] == "aid-3"
    assert entry["workflow_id"] == "wf-3"
    assert entry["status"] == "approved"
    assert entry["payload"]["title"] == "schema test"


def test_json_approval_store_save_no_sqlite_or_extra_files(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    data = {"aid-4": _make_approval(approval_id="aid-4")}

    JsonApprovalStore.save(store_path, data)

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "approvals.json"


# ---------------------------------------------------------------------------
# roundtrip 測試
# ---------------------------------------------------------------------------


def test_json_approval_store_roundtrip_all_statuses(tmp_path: Path):
    store_path = tmp_path / "approvals.json"
    statuses = ["pending", "approved", "rejected", "expired"]
    originals: dict[str, Approval] = {}

    for i, status in enumerate(statuses):
        aid = f"aid-{i}"
        originals[aid] = _make_approval(
            approval_id=aid, workflow_id=f"wf-{i}", status=status
        )

    JsonApprovalStore.save(store_path, originals)
    loaded = JsonApprovalStore.load(store_path)

    assert set(loaded.keys()) == set(originals.keys())
    for aid, original in originals.items():
        assert loaded[aid].status == original.status
        assert loaded[aid].workflow_id == original.workflow_id


def test_json_approval_store_mark_executed_payload_preserved(tmp_path: Path):
    """execution_status / executed_at / execution_transaction_id 在 payload 中正確保留。"""
    store_path = tmp_path / "approvals.json"
    executed_at = "2026-01-01T00:00:00+00:00"
    approval = _make_approval(
        approval_id="aid-exec",
        status="approved",
        payload={
            "workflow_id": "wf-exec",
            "execution_status": "executed",
            "executed_at": executed_at,
            "execution_transaction_id": "tx-abc-123",
        },
    )
    data = {"aid-exec": approval}

    JsonApprovalStore.save(store_path, data)
    loaded = JsonApprovalStore.load(store_path)

    payload = loaded["aid-exec"].payload
    assert payload["execution_status"] == "executed"
    assert payload["executed_at"] == executed_at
    assert payload["execution_transaction_id"] == "tx-abc-123"


# ---------------------------------------------------------------------------
# ApprovalManager 委派整合（確認 manager 行為不變）
# ---------------------------------------------------------------------------


def test_approval_manager_delegates_to_json_store(tmp_path: Path):
    """ApprovalManager._load_store / _save_store 委派後行為與之前相同。"""
    from app.approvals.manager import ApprovalManager

    store_path = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_path)

    approval = manager.create_approval({"workflow_id": "wf-delegate", "title": "t"})
    aid = approval.approval_id

    # 重建 manager，確認 JSON 持久化
    manager2 = ApprovalManager(store_path=store_path)
    got = manager2.get(aid)
    assert got is not None
    assert got.workflow_id == "wf-delegate"
    assert got.status == "pending"


def test_approval_manager_save_produces_array_schema(tmp_path: Path):
    """委派後 approvals.json 仍是 array（schema 不變）。"""
    from app.approvals.manager import ApprovalManager

    store_path = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_path)
    manager.create_approval({"workflow_id": "wf-schema"})

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert raw[0]["workflow_id"] == "wf-schema"
