"""Phase 15E — Persistent move transaction log.

Stores MoveTransaction objects in a JSON file (mirrors the rename
transaction log from Phase 14C).  Format on disk:
  {
    "transactions": [ { ...MoveTransaction fields... }, ... ]
  }

All datetime values are serialised as ISO 8601 strings via Pydantic's
model_dump(mode="json") and deserialized via model_validate().

這是底層持久化 API：未接任何 Mock LINE 指令；建議的預設路徑為
runtime/move_transactions.json（已列入 .gitignore），但 log_path 由
呼叫方指定。
"""

import json
from pathlib import Path

from app.folder_intelligence.schemas import (
    MoveTransaction,
    MoveTransactionAction,
)


class MoveTransactionLog:
    """JSON-backed persistent store for MoveTransaction objects."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = Path(log_path)

    # ── Private I/O ──────────────────────────────────────────────────────────

    def _read(self) -> dict:
        """Return parsed log dict.  Returns empty structure on any error."""
        if not self._log_path.exists():
            return {"transactions": []}
        try:
            raw = self._log_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict) or "transactions" not in data:
                return {"transactions": []}
            return data
        except (json.JSONDecodeError, OSError):
            return {"transactions": []}

    def _write(self, data: dict) -> None:
        """Write log dict to file, creating parent dirs as needed."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _upsert(self, transaction: MoveTransaction) -> None:
        """Insert or replace a transaction entry by transaction_id."""
        data = self._read()
        serialized = transaction.model_dump(mode="json")
        for i, entry in enumerate(data["transactions"]):
            if entry.get("transaction_id") == transaction.transaction_id:
                data["transactions"][i] = serialized
                self._write(data)
                return
        data["transactions"].append(serialized)
        self._write(data)

    # ── Public API ───────────────────────────────────────────────────────────

    def save_transaction(self, transaction: MoveTransaction) -> None:
        """Persist transaction, appending or upserting by transaction_id."""
        self._upsert(transaction)

    def load_transaction(self, transaction_id: str) -> MoveTransaction | None:
        """Return transaction by id, or None if not found."""
        data = self._read()
        for entry in data["transactions"]:
            if entry.get("transaction_id") == transaction_id:
                try:
                    return MoveTransaction.model_validate(entry)
                except Exception:
                    return None
        return None

    def list_transactions(self) -> list[MoveTransaction]:
        """Return all stored transactions; empty list if log missing or corrupt."""
        data = self._read()
        result: list[MoveTransaction] = []
        for entry in data["transactions"]:
            try:
                result.append(MoveTransaction.model_validate(entry))
            except Exception:
                continue
        return result

    def update_transaction(self, transaction: MoveTransaction) -> None:
        """Replace existing transaction by id, or add it if not found."""
        self._upsert(transaction)

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> MoveTransaction | None:
        """Update action statuses matched by original_path or new_path.

        action_updates: {path_key: new_status}
          path_key may be the action's original_path OR new_path.
          new_status must be a valid MoveTransactionAction status.

        Returns the updated transaction, or None if transaction_id not found.
        """
        tx = self.load_transaction(transaction_id)
        if tx is None:
            return None

        new_actions: list[MoveTransactionAction] = []
        for action in tx.actions:
            new_status = action_updates.get(action.original_path)
            if new_status is None:
                new_status = action_updates.get(action.new_path)

            if new_status is not None:
                new_actions.append(MoveTransactionAction(
                    original_path=action.original_path,
                    new_path=action.new_path,
                    status=new_status,
                    rollback_from=action.rollback_from,
                    rollback_to=action.rollback_to,
                ))
            else:
                new_actions.append(action)

        tx.actions = new_actions
        self._upsert(tx)
        return tx
