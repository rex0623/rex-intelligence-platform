"""Approval JSON persistence — stateless I/O helper.

JsonApprovalStore provides two static methods (load / save) that encapsulate
the JSON serialisation logic previously embedded in ApprovalManager.

Design notes (Phase 18B):
- Stateless: no instance attributes, no in-memory cache.
- store_path and the in-memory _store dict remain owned by ApprovalManager.
- ApprovalStore Protocol and SQLiteApprovalStore are out-of-scope (Phase 18C).
- approvals.json schema is unchanged: an array of Approval dicts.
"""

import json
from pathlib import Path
from typing import Dict

from app.approvals.schemas import Approval
from app.core.logger import get_logger

logger = get_logger(__name__)


class JsonApprovalStore:
    """Stateless JSON I/O helper for ApprovalManager."""

    @staticmethod
    def load(store_path: Path) -> Dict[str, Approval]:
        """Read approvals.json → Dict[approval_id, Approval].

        Returns {} when the file does not exist or JSON is corrupted.
        """
        if not store_path.exists():
            return {}
        try:
            raw = json.loads(store_path.read_text(encoding="utf-8"))
            return {
                item["approval_id"]: Approval.model_validate(item) for item in raw
            }
        except Exception:
            logger.warning(
                "Failed to load approval store, starting with empty store",
                exc_info=True,
            )
            return {}

    @staticmethod
    def save(store_path: Path, data: Dict[str, Approval]) -> None:
        """Write Dict[approval_id, Approval] → approvals.json (array schema).

        Parent directory creation is the caller's responsibility (ApprovalManager
        already calls store_path.parent.mkdir in __init__).
        """
        serialized = [approval.model_dump(mode="json") for approval in data.values()]
        store_path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8"
        )
