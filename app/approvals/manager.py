"""File-backed approval manager."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from app.approvals.schemas import Approval
from app.approvals.store import JsonApprovalStore
from app.core.config import get_approval_store_path
from app.core.logger import get_logger

logger = get_logger(__name__)


class ApprovalManager:
    def __init__(
        self,
        store_path: Optional[Path | str] = None,
        _store_backend=None,
    ):
        self.store_path = (
            Path(store_path)
            if store_path is not None
            else get_approval_store_path()
        )
        self._backend = _store_backend
        if self._backend is None:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: Dict[str, Approval] = {}
        self._load_store()

    def _load_store(self) -> None:
        if self._backend is not None:
            self._store = self._backend.load(self.store_path)
        else:
            self._store = JsonApprovalStore.load(self.store_path)

    def _save_store(self) -> None:
        if self._backend is not None:
            self._backend.save(self.store_path, self._store)
        else:
            JsonApprovalStore.save(self.store_path, self._store)

    def create_approval(self, workflow_plan: dict, ttl_minutes: int = 60) -> Approval:
        approval_id = str(uuid.uuid4())
        workflow_id = workflow_plan.get("workflow_id", "")
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        approval = Approval(
            approval_id=approval_id,
            workflow_id=workflow_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            payload=workflow_plan,
        )
        self._store[approval_id] = approval
        self._save_store()
        logger.info("Created approval", extra={"approval_id": approval_id})
        return approval

    def get(self, approval_id: str) -> Optional[Approval]:
        approval = self._store.get(approval_id)
        if approval and approval.is_expired():
            approval.status = "expired"
            self._save_store()
        return approval

    def approve(self, approval_id: str) -> Approval:
        approval = self._store.get(approval_id)
        if approval is None:
            raise KeyError("approval not found")
        if approval.is_expired():
            approval.status = "expired"
            self._save_store()
            return approval
        if approval.status != "pending":
            raise ValueError("approval not in pending state")
        approval.status = "approved"
        self._save_store()
        logger.info("Approval approved", extra={"approval_id": approval_id})
        return approval

    def mark_executed(
        self, approval_id: str, transaction_id: Optional[str] = None
    ) -> Optional[Approval]:
        """Record execution state on an approval (Phase 14E once-only guard).

        Stores execution metadata inside the existing payload dict, so the
        record stays backward compatible: old approvals without
        "execution_status" are treated as not yet executed.
        """
        approval = self._store.get(approval_id)
        if approval is None:
            return None
        if approval.payload is None:
            approval.payload = {}
        approval.payload["execution_status"] = "executed"
        approval.payload["executed_at"] = datetime.now(timezone.utc).isoformat()
        if transaction_id:
            approval.payload["execution_transaction_id"] = transaction_id
        self._save_store()
        logger.info("Approval marked executed", extra={"approval_id": approval_id})
        return approval

    def reject(self, approval_id: str) -> Approval:
        approval = self._store.get(approval_id)
        if approval is None:
            raise KeyError("approval not found")
        if approval.is_expired():
            approval.status = "expired"
            self._save_store()
            return approval
        if approval.status != "pending":
            raise ValueError("approval not in pending state")
        approval.status = "rejected"
        self._save_store()
        logger.info("Approval rejected", extra={"approval_id": approval_id})
        return approval


def _make_singleton() -> ApprovalManager:
    from app.core.config import settings
    backend = getattr(settings, "APPROVAL_STORE_BACKEND", "json")
    if backend == "sqlite":
        from app.core.sqlite_approval_store import SqliteApprovalStore
        return ApprovalManager(_store_backend=SqliteApprovalStore())
    return ApprovalManager()


approval_manager = _make_singleton()
