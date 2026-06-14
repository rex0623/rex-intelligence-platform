"""Shared JSON transaction log I/O helpers (Phase 18C).

Extracted from RenameTransactionLog._read() / _write() and
MoveTransactionLog._read() / _write(), which were byte-for-byte identical.

Design notes:
- Stateless module-level functions only; no class, no Protocol.
- read_json_log / write_json_log own the {"transactions": [...]} file format.
- ensure_utc_aware consolidates the _aware() helper duplicated in both
  prune_transactions() implementations.
- No SQLite, no DB files, no runtime lock interaction.
- TransactionLog Protocol and SQLite implementations are out-of-scope (Phase 18D).
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def read_json_log(log_path: Path) -> dict:
    """Read a {"transactions": [...]} JSON log file.

    Returns {"transactions": []} when the file is absent, corrupt, or has an
    unexpected structure.  Never raises; never modifies the file.
    """
    if not log_path.exists():
        return {"transactions": []}
    try:
        raw = log_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "transactions" not in data:
            return {"transactions": []}
        if not isinstance(data["transactions"], list):
            return {"transactions": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"transactions": []}


def write_json_log(log_path: Path, data: dict) -> None:
    """Write *data* to *log_path*, creating parent directories as needed.

    Uses indent=2 and ensure_ascii=False to match the existing log format.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_utc_aware(dt: datetime) -> datetime:
    """Return a UTC-aware datetime.

    If *dt* already carries timezone info, it is returned unchanged.
    Naive datetimes are treated as UTC.

    Uses the datetime() constructor (not dt.replace()) to remain compatible
    with modules that forbid .replace() calls for AST safety reasons.
    """
    if dt.tzinfo is not None:
        return dt
    return datetime(
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second, dt.microsecond,
        tzinfo=timezone.utc,
    )
