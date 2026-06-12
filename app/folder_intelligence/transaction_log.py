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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.folder_intelligence.schemas import (
    MoveRollbackPreview,
    MoveRollbackPreviewAction,
    MoveTransaction,
    MoveTransactionAction,
    MoveTransactionLogPruneResult,
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

    # ── Phase 15J — Rotation / cleanup ──────────────────────────────────────

    def prune_transactions(
        self,
        older_than_days: int = 30,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> MoveTransactionLogPruneResult:
        """Prune old transactions from the log（維運 API，Phase 15J，鏡像 14F）。

        清理規則：
          - log 不存在 → 安全 no-op（不建立 log）。
          - 整檔 invalid JSON / 結構錯誤 → 不刪、不覆寫，corrupted 計數 ≥ 1。
          - entry 無法解析成 MoveTransaction → 原樣保留（corrupted_entries +1）。
          - 仍有 status=="success" 的 action（rollbackable）→ 永不刪除
            （protected，即使已過期）。
          - 全部 rolled_back 或只有 failed/pending/skipped → created_at 超過
            older_than_days 才刪，未過期則保留（retained）。
          - dry_run=True → 只回報將刪除哪些 transaction，不重寫 log。
          - 無可刪項目（pruned_count == 0）→ 不重寫 log。

        Safety rules：
          - 只動 log 檔；不檢查 filesystem、不搬移/回滾任何檔案、
            不建資料夾、不改變任何 action status。
          - 以 raw entry 過濾重寫：保留的 entry（含 corrupted 與未知欄位）
            原樣保留，不重新序列化。
        """
        if now is None:
            now = datetime.now(timezone.utc)

        if not self._log_path.exists():
            return MoveTransactionLogPruneResult(dry_run=dry_run)

        try:
            data = json.loads(self._log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return MoveTransactionLogPruneResult(
                corrupted_count=1, corrupted_entries=1, dry_run=dry_run
            )
        if not isinstance(data, dict) or not isinstance(
            data.get("transactions"), list
        ):
            return MoveTransactionLogPruneResult(
                corrupted_count=1, corrupted_entries=1, dry_run=dry_run
            )

        raw_entries = data["transactions"]
        before_count = len(raw_entries)
        cutoff = now - timedelta(days=older_than_days)

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

        prune_indexes: set[int] = set()
        pruned_ids: list[str] = []
        retained_ids: list[str] = []
        protected_ids: list[str] = []
        corrupted = 0

        for i, entry in enumerate(raw_entries):
            try:
                tx = MoveTransaction.model_validate(entry)
            except Exception:
                corrupted += 1  # 無法解析的 entry 永不刪除，原樣保留
                continue

            # 仍可回滾（任一 success action）→ 永不刪除，即使已過期
            if any(action.status == "success" for action in tx.actions):
                protected_ids.append(tx.transaction_id)
                continue

            if _aware(tx.created_at) < cutoff:
                prune_indexes.add(i)
                pruned_ids.append(tx.transaction_id)
            else:
                retained_ids.append(tx.transaction_id)

        if pruned_ids and not dry_run:
            data["transactions"] = [
                entry
                for i, entry in enumerate(raw_entries)
                if i not in prune_indexes
            ]
            self._write(data)

        return MoveTransactionLogPruneResult(
            before_count=before_count,
            after_count=before_count - len(pruned_ids),
            pruned_count=len(pruned_ids),
            retained_count=len(retained_ids),
            protected_count=len(protected_ids),
            corrupted_count=corrupted,
            corrupted_entries=corrupted,
            dry_run=dry_run,
            pruned_transaction_ids=pruned_ids,
            retained_transaction_ids=retained_ids,
            protected_transaction_ids=protected_ids,
        )


def prune_move_transactions(
    transaction_log: MoveTransactionLog,
    older_than_days: int = 30,
    dry_run: bool = False,
) -> MoveTransactionLogPruneResult:
    """Module-level convenience wrapper for prune_transactions()（15J）。

    僅為維運 API：未接任何 Mock LINE 指令。
    """
    return transaction_log.prune_transactions(
        older_than_days=older_than_days, dry_run=dry_run
    )


# ---------------------------------------------------------------------------
# Phase 15H — Move rollback preview（read-only；鏡像 14D-3A rename preview）
# ---------------------------------------------------------------------------


def preview_move_rollback_transaction(
    transaction: MoveTransaction,
) -> MoveRollbackPreview:
    """Build a read-only rollback preview for an in-memory MoveTransaction.

    Strictly read-only: never touches the filesystem, never writes to any
    transaction log, never calls any rollback/move function.

    Per-action semantics:
      - status == "success" 且 rollback_from / rollback_to 存在 → rollbackable
      - status == "success" 但缺 rollback 路徑 → reason "missing_rollback_paths"
      - status == "rolled_back"                → reason "already_rolled_back"
      - status == "failed"                     → reason "action_failed"
      - status == "pending"                    → reason "action_pending"
    """
    actions: list[MoveRollbackPreviewAction] = []
    rollbackable_count = already_rolled_back = failed = 0

    for action in transaction.actions:
        rollbackable = False
        reason: str | None = None

        if action.status == "success":
            if action.rollback_from and action.rollback_to:
                rollbackable = True
                rollbackable_count += 1
            else:
                reason = "missing_rollback_paths"
        elif action.status == "rolled_back":
            reason = "already_rolled_back"
            already_rolled_back += 1
        elif action.status == "failed":
            reason = "action_failed"
            failed += 1
        elif action.status == "pending":
            reason = "action_pending"

        actions.append(MoveRollbackPreviewAction(
            original_path=action.original_path,
            new_path=action.new_path,
            rollback_from=action.rollback_from,
            rollback_to=action.rollback_to,
            status=action.status,
            rollbackable=rollbackable,
            reason=reason,
        ))

    return MoveRollbackPreview(
        transaction_id=transaction.transaction_id,
        total=len(transaction.actions),
        rollbackable_count=rollbackable_count,
        already_rolled_back_count=already_rolled_back,
        failed_count=failed,
        actions=actions,
    )


def preview_move_rollback_transaction_by_id(
    transaction_id: str,
    transaction_log: MoveTransactionLog,
) -> MoveRollbackPreview | None:
    """Load a persisted transaction and build a read-only rollback preview.

    Returns None if transaction_id is not found.  Never moves files,
    never creates folders, never modifies the transaction or the log.
    """
    tx = transaction_log.load_transaction(transaction_id)
    if tx is None:
        return None
    return preview_move_rollback_transaction(tx)
