"""Phase 20E — approvals.json → SQLite approval store migration CLI.

Usage
-----
  # Preview only (default — no DB writes)
  poetry run python scripts/migrate_approvals.py --dry-run

  # Apply migration (acquires runtime lock)
  poetry run python scripts/migrate_approvals.py --apply --backup

  # Custom paths
  poetry run python scripts/migrate_approvals.py \\
      --apply --source-json-path /path/to/approvals.json --db-path /path/to/rip.db

Notes
-----
  - This script migrates approvals.json → runtime/rip.db (approvals table).
  - It does NOT migrate rename/move transaction logs (see migrate_transaction_logs.py).
  - approvals.json is never modified by this script (read-only source).
  - Migration does NOT automatically switch APPROVAL_STORE_BACKEND.
    After a successful --apply, set APPROVAL_STORE_BACKEND=sqlite in .env manually.
  - Idempotent: running --apply multiple times is safe; already-present approvals
    are counted in already_present_count and not overwritten.

Exit codes
----------
  0  Success (dry-run or apply, including "nothing to migrate")
  1  Runtime lock busy
  2  Corrupt source data with --fail-on-corrupt
  3  Unexpected CLI / runtime error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_approvals",
        description=(
            "Migrate RIP approvals.json to the experimental SQLite backend.  "
            "Defaults to dry-run; use --apply to write to the DB."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview migration without writing to the DB (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Perform the migration.  Acquires the runtime lock.",
    )
    p.add_argument(
        "--backup",
        action="store_true",
        default=False,
        help=(
            "Back up approvals.json and the existing rip.db before applying. "
            "Ignored during dry-run."
        ),
    )
    p.add_argument(
        "--source-json-path",
        metavar="PATH",
        default=None,
        help="Path to approvals.json (default: RUNTIME_DIR/approvals.json).",
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        default=None,
        help="SQLite DB target path (default: runtime/rip.db).",
    )
    p.add_argument(
        "--fail-on-corrupt",
        action="store_true",
        default=False,
        help="Exit with code 2 if any corrupt file or entry is encountered.",
    )
    p.add_argument(
        "--json-report",
        action="store_true",
        default=False,
        help="Output migration report as JSON instead of human-readable text.",
    )
    return p


def _result_to_dict(r) -> dict:
    return {
        "source_path": str(r.source_path),
        "kind": r.kind,
        "dry_run": r.dry_run,
        "migrated_count": r.migrated_count,
        "already_present_count": r.already_present_count,
        "corrupted_count": r.corrupted_count,
        "skipped_count": r.skipped_count,
        "missing_source": r.missing_source,
        "errors": r.errors,
        "warnings": r.warnings,
    }


def _print_result(r) -> None:
    mode = "DRY-RUN" if r.dry_run else "APPLIED"
    tag = f"[{r.kind}]"
    if r.missing_source:
        print(f"  {tag} {mode}: source not found — skipped ({r.source_path})")
        return
    print(
        f"  {tag} {mode}: "
        f"migrated={r.migrated_count}  "
        f"already_present={r.already_present_count}  "
        f"corrupted={r.corrupted_count}  "
        f"skipped={r.skipped_count}"
    )
    for w in r.warnings:
        print(f"    WARNING: {w}")
    for e in r.errors:
        print(f"    ERROR:   {e}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    apply_mode = args.apply
    dry_run = not apply_mode

    from app.core.config import get_sqlite_db_path, settings

    source_json_path = (
        Path(args.source_json_path)
        if args.source_json_path
        else Path(settings.RUNTIME_DIR) / "approvals.json"
    )
    db_path = Path(args.db_path) if args.db_path else get_sqlite_db_path()

    from app.core.approval_migration import migrate_approvals

    if apply_mode:
        from app.core.runtime_lock import RuntimeLockBusy, acquire_runtime_lock

        try:
            with acquire_runtime_lock():
                if args.backup:
                    from datetime import datetime, timezone

                    from app.core.transaction_log_migration import _backup_file

                    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    if source_json_path.exists():
                        _backup_file(source_json_path, ts)
                    if db_path.exists():
                        _backup_file(db_path, ts)

                result = migrate_approvals(
                    source_json_path,
                    db_path,
                    dry_run=False,
                    fail_on_corrupt=args.fail_on_corrupt,
                )
        except RuntimeLockBusy:
            print(
                "ERROR: 另一個 RIP 操作正在執行中，請等待完成後再重試 migration。",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            print(f"ERROR: Unexpected migration error: {exc}", file=sys.stderr)
            return 3
    else:
        try:
            result = migrate_approvals(
                source_json_path,
                db_path,
                dry_run=True,
                fail_on_corrupt=args.fail_on_corrupt,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3

    if args.json_report:
        print(json.dumps(_result_to_dict(result), indent=2, ensure_ascii=False))
    else:
        mode_label = "DRY-RUN" if dry_run else "APPLY"
        print(f"RIP approval store migration — {mode_label}")
        print(f"  source : {source_json_path}")
        print(f"  db path: {db_path}")
        _print_result(result)
        if dry_run:
            print("\n(Dry-run: no changes written. Use --apply to perform migration.)")

    if result.has_errors and args.fail_on_corrupt:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
