"""Phase 20E — approvals.json → SQLite migration library.

Provides a one-shot migration from the JSON approval store (approvals.json)
to the SQLite backend introduced in Phase 20A.

Design notes:
- approvals.json format is a flat JSON array of approval dicts:
    [{approval_id, workflow_id, status, created_at, expires_at, payload}, ...]
  This differs from transaction log JSON which uses {"transactions": [...]}.
- JSON source (approvals.json) is never deleted, renamed, or overwritten.
  Migration is purely read-only on the JSON side.
- Idempotency: INSERT OR IGNORE on the approvals table (approval_id PRIMARY KEY)
  skips rows already present. cursor.rowcount == 1 → migrated; 0 → already_present.
  This differs from SqliteApprovalStore.save() which uses DELETE + re-INSERT
  (replace-all) and is NOT suitable for incremental migration.
- Validation: each raw approval dict is passed through Pydantic model_validate()
  before writing to SQLite. Items failing validation increment corrupted_count
  and are skipped entirely.
- dry_run=True (default): no SQLite writes, rip.db is not created.
- dry_run=False: calls initialize_sqlite_schema() then writes via raw sqlite3.
- Backup is the caller's responsibility (see scripts/migrate_approvals.py).
- No pyproject.toml changes needed: only stdlib (json, sqlite3, dataclasses)
  and app-internal imports.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ApprovalMigrationResult:
    """Summary of one migrate_approvals() call."""

    source_path: Path
    dry_run: bool = True
    kind: Literal["approval"] = "approval"
    migrated_count: int = 0
    already_present_count: int = 0
    corrupted_count: int = 0
    skipped_count: int = 0
    missing_source: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def total_in_source(self) -> int:
        return (
            self.migrated_count
            + self.already_present_count
            + self.corrupted_count
            + self.skipped_count
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_approvals_strict(
    path: Path,
) -> tuple[list | None, str | None]:
    """Read approvals.json strictly.

    approvals.json format: a flat JSON array of approval dicts.
    Returns (data_list, None) on success, or (None, error_reason) on failure.
    Distinguishes three cases that JsonApprovalStore.load() collapses into {}:
      - file_not_found:     path does not exist
      - corrupt_json:       file exists but bytes are not valid JSON
      - invalid_structure:  valid JSON but top-level value is not a list

    Never raises; never modifies the file.
    """
    if not path.exists():
        return None, "file_not_found"
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"corrupt_json: {exc}"
    if not isinstance(data, list):
        return None, "invalid_structure"
    return data, None


# ---------------------------------------------------------------------------
# Core migration function
# ---------------------------------------------------------------------------


def migrate_approvals(
    approvals_json_path: Path,
    db_path: Path,
    *,
    dry_run: bool = True,
    fail_on_corrupt: bool = False,
) -> ApprovalMigrationResult:
    """Migrate approvals.json to the SQLite approvals table.

    If dry_run=True (default), no SQLite writes are performed and rip.db is
    not created or modified.  migrated_count reflects the number of valid
    approvals that *would be* migrated.

    If dry_run=False:
      - initialize_sqlite_schema(db_path) is called (idempotent, creates tables).
      - Each valid approval is written via INSERT OR IGNORE.
      - cursor.rowcount == 1 → migrated_count++
      - cursor.rowcount == 0 → already_present_count++ (PK conflict, skipped)

    If fail_on_corrupt=True, corrupt file or entries cause has_errors=True;
    callers may then exit non-zero.  When fail_on_corrupt=False, corrupt entries
    are reported as warnings only and valid entries continue to be processed.

    Source JSON (approvals.json) is never modified, deleted, or renamed.
    Backup is the caller's responsibility.
    """
    from app.approvals.schemas import Approval

    result = ApprovalMigrationResult(
        source_path=approvals_json_path,
        dry_run=dry_run,
    )

    data, error = _load_approvals_strict(approvals_json_path)
    if error == "file_not_found":
        result.missing_source = True
        return result
    if error is not None:
        msg = f"Cannot read {approvals_json_path}: {error}"
        result.errors.append(msg)
        if not fail_on_corrupt:
            result.warnings.append(msg)
        return result

    raw_entries: list = data  # narrowed: _load_approvals_strict ensures list
    if not raw_entries:
        return result

    # Validate each entry via Pydantic; collect valid approvals
    valid_approvals: list[Approval] = []
    for raw in raw_entries:
        try:
            approval = Approval.model_validate(raw)
            valid_approvals.append(approval)
        except Exception as exc:
            result.corrupted_count += 1
            msg = f"Skipping corrupt approval entry: {exc}"
            result.warnings.append(msg)
            if fail_on_corrupt:
                result.errors.append(msg)

    if dry_run:
        # Dry-run: report would-be-migrated count; do not touch the DB.
        result.migrated_count = len(valid_approvals)
        return result

    # ---------------------------------------------------------------------------
    # Apply path: initialise schema, then INSERT OR IGNORE each approval.
    # ---------------------------------------------------------------------------
    from app.core.sqlite_transaction_log import initialize_sqlite_schema

    initialize_sqlite_schema(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        for approval in valid_approvals:
            expires_at_str = (
                approval.expires_at.isoformat()
                if approval.expires_at is not None
                else None
            )
            payload_json = (
                json.dumps(approval.payload, ensure_ascii=False)
                if approval.payload is not None
                else None
            )
            cur = conn.execute(
                "INSERT OR IGNORE INTO approvals"
                " (approval_id, workflow_id, status, created_at, expires_at, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    approval.approval_id,
                    approval.workflow_id,
                    approval.status,
                    approval.created_at.isoformat(),
                    expires_at_str,
                    payload_json,
                ),
            )
            if cur.rowcount == 1:
                result.migrated_count += 1
            else:
                result.already_present_count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return result
