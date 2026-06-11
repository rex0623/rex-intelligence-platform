"""Phase 14C — Persistent rename transaction log.

Stores RenameTransaction objects in a JSON file.
Format on disk:
  {
    "transactions": [ { ...RenameTransaction fields... }, ... ]
  }

All datetime values are serialised as ISO 8601 strings via Pydantic's
model_dump(mode="json") and deserialized via model_validate().
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.filename.schemas import (
    RenameTransaction,
    RenameTransactionAction,
    RollbackPreview,
    RollbackPreviewAction,
    TransactionLogPruneResult,
)


class RenameTransactionLog:
    """JSON-backed persistent store for RenameTransaction objects."""

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

    def _upsert(self, transaction: RenameTransaction) -> None:
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

    def save_transaction(self, transaction: RenameTransaction) -> None:
        """Persist transaction, appending or upserting by transaction_id."""
        self._upsert(transaction)

    def load_transaction(self, transaction_id: str) -> RenameTransaction | None:
        """Return transaction by id, or None if not found."""
        data = self._read()
        for entry in data["transactions"]:
            if entry.get("transaction_id") == transaction_id:
                try:
                    return RenameTransaction.model_validate(entry)
                except Exception:
                    return None
        return None

    def list_transactions(self) -> list[RenameTransaction]:
        """Return all stored transactions; empty list if log missing or corrupt."""
        data = self._read()
        result: list[RenameTransaction] = []
        for entry in data["transactions"]:
            try:
                result.append(RenameTransaction.model_validate(entry))
            except Exception:
                continue
        return result

    def update_transaction(self, transaction: RenameTransaction) -> None:
        """Replace existing transaction by id, or add it if not found."""
        self._upsert(transaction)

    def mark_transaction_actions(
        self,
        transaction_id: str,
        action_updates: dict[str, str],
    ) -> RenameTransaction | None:
        """Update action statuses matched by original_path or new_path.

        action_updates: {path_key: new_status}
          path_key may be the action's original_path OR new_path.
          new_status must be a valid RenameTransactionAction status.

        Returns the updated transaction, or None if transaction_id not found.
        """
        tx = self.load_transaction(transaction_id)
        if tx is None:
            return None

        new_actions: list[RenameTransactionAction] = []
        for action in tx.actions:
            new_status = action_updates.get(action.original_path)
            if new_status is None:
                new_status = action_updates.get(action.new_path)

            if new_status is not None:
                new_actions.append(RenameTransactionAction(
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

    # ── Phase 14F — Rotation / cleanup ───────────────────────────────────────

    def prune_transactions(
        self,
        max_transactions: int | None = None,
        max_age_days: int | None = None,
        now: datetime | None = None,
    ) -> TransactionLogPruneResult:
        """Prune old transactions from the log (maintenance API, Phase 14F).

        Criteria (both optional; with neither given this is a no-op):
          - max_age_days: transactions created more than N days ago become
            prune candidates.
          - max_transactions: keep at most N most-recent transactions; older
            ones beyond the limit become prune candidates.

        Safety rules:
          - A transaction with any action in status "success" is still
            rollbackable and is NEVER pruned, even if it matches the
            criteria (counted in kept_rollbackable_count).
          - Entries that fail validation are never pruned.
          - Only the log file is touched; renamed files are never affected.
          - The file is rewritten only when something was actually pruned.
        """
        data = self._read()
        raw_entries = data["transactions"]
        total_before = len(raw_entries)

        if now is None:
            now = datetime.now(timezone.utc)

        def _aware(dt: datetime) -> datetime:
            # naive datetime 視為 UTC；不用 dt.replace() 以符合本模組
            # 「不得出現 rename/move/replace 呼叫」的 AST 安全防護
            if dt.tzinfo is not None:
                return dt
            return datetime(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second, dt.microsecond,
                tzinfo=timezone.utc,
            )

        parsed: list[tuple[int, RenameTransaction]] = []
        for i, entry in enumerate(raw_entries):
            try:
                parsed.append((i, RenameTransaction.model_validate(entry)))
            except Exception:
                continue  # 無法解析的 entry 永不刪除

        candidate_indexes: set[int] = set()

        if max_age_days is not None:
            cutoff = now - timedelta(days=max_age_days)
            for i, tx in parsed:
                if _aware(tx.created_at) < cutoff:
                    candidate_indexes.add(i)

        if max_transactions is not None and len(parsed) > max_transactions:
            oldest_first = sorted(parsed, key=lambda p: _aware(p[1].created_at))
            excess = len(parsed) - max_transactions
            for i, _tx in oldest_first[:excess]:
                candidate_indexes.add(i)

        tx_by_index = dict(parsed)
        prune_indexes: set[int] = set()
        pruned_ids: list[str] = []
        kept_rollbackable = 0

        for i in sorted(candidate_indexes):
            tx = tx_by_index[i]
            if any(action.status == "success" for action in tx.actions):
                kept_rollbackable += 1
                continue
            prune_indexes.add(i)
            pruned_ids.append(tx.transaction_id)

        if prune_indexes:
            data["transactions"] = [
                entry for i, entry in enumerate(raw_entries) if i not in prune_indexes
            ]
            self._write(data)

        return TransactionLogPruneResult(
            total_before=total_before,
            total_after=len(data["transactions"]),
            pruned_count=len(pruned_ids),
            kept_rollbackable_count=kept_rollbackable,
            pruned_transaction_ids=pruned_ids,
        )


# ---------------------------------------------------------------------------
# Phase 14D-3A — Read-only rollback preview
# ---------------------------------------------------------------------------


def preview_rollback_transaction(
    transaction_id: str,
    transaction_log: RenameTransactionLog,
) -> RollbackPreview | None:
    """Build a read-only rollback preview for a persisted transaction.

    Returns None if transaction_id is not found.

    Strictly read-only: never touches the filesystem, never writes to the
    transaction log, never calls any rollback/rename function.  An action is
    rollbackable only when its status is "success"; rolled_back / failed /
    pending actions are not.
    """
    tx = transaction_log.load_transaction(transaction_id)
    if tx is None:
        return None

    actions: list[RollbackPreviewAction] = []
    success = rolled_back = failed = pending = 0

    for action in tx.actions:
        if action.status == "success":
            success += 1
        elif action.status == "rolled_back":
            rolled_back += 1
        elif action.status == "failed":
            failed += 1
        elif action.status == "pending":
            pending += 1

        actions.append(RollbackPreviewAction(
            original_path=action.original_path,
            new_path=action.new_path,
            status=action.status,
            rollbackable=(action.status == "success"),
        ))

    return RollbackPreview(
        transaction_id=tx.transaction_id,
        plan_id=tx.plan_id,
        total_actions=len(tx.actions),
        success_count=success,
        rolled_back_count=rolled_back,
        failed_count=failed,
        pending_count=pending,
        rollbackable_count=success,
        actions=actions,
    )
