"""Phase 19J — JSON → SQLite transaction log migration CLI.

Usage
-----
  # Preview only (default — no DB writes)
  poetry run python scripts/migrate_transaction_logs.py --dry-run

  # Apply migration (acquires runtime lock)
  poetry run python scripts/migrate_transaction_logs.py --apply --backup

  # Custom paths
  poetry run python scripts/migrate_transaction_logs.py \\
      --apply --source-json-dir /path/to/runtime --db-path /path/to/rip.db

Exit codes
----------
  0  Success (dry-run or apply, including "nothing to migrate")
  1  Runtime lock busy
  2  Corrupt source data and --fail-on-corrupt
  3  Unexpected DB / migration error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_transaction_logs",
        description=(
            "Migrate RIP JSON transaction logs (rename / move) to the "
            "experimental SQLite backend.  Defaults to dry-run; use --apply "
            "to write."
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
            "Back up source JSON files and the existing rip.db before applying. "
            "Ignored during dry-run."
        ),
    )
    p.add_argument(
        "--source-json-dir",
        metavar="PATH",
        default=None,
        help="Directory containing rename/move_transactions.json (default: RUNTIME_DIR).",
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        default=None,
        help="SQLite DB target path (default: runtime/rip.db).",
    )
    p.add_argument(
        "--rename-only",
        action="store_true",
        default=False,
        help="Only migrate rename_transactions.json.",
    )
    p.add_argument(
        "--move-only",
        action="store_true",
        default=False,
        help="Only migrate move_transactions.json.",
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


def _print_result(r, *, prefix: str = "") -> None:
    tag = f"[{prefix}{r.kind}]" if prefix else f"[{r.kind}]"
    mode = "DRY-RUN" if r.dry_run else "APPLIED"
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

    # Resolve dry_run / apply
    apply_mode = args.apply
    dry_run = not apply_mode

    # Resolve paths
    from app.core.config import get_sqlite_db_path, settings

    source_json_dir = (
        Path(args.source_json_dir)
        if args.source_json_dir
        else Path(settings.RUNTIME_DIR)
    )
    db_path = Path(args.db_path) if args.db_path else get_sqlite_db_path()

    # Resolve rename/move flags
    if args.rename_only and args.move_only:
        print("ERROR: --rename-only and --move-only are mutually exclusive.", file=sys.stderr)
        return 3
    do_rename = not args.move_only
    do_move = not args.rename_only

    from app.core.transaction_log_migration import migrate_all

    if apply_mode:
        # Acquire runtime lock for the full apply
        from app.core.runtime_lock import RuntimeLockBusy, acquire_runtime_lock

        try:
            with acquire_runtime_lock():
                results = migrate_all(
                    source_json_dir,
                    db_path,
                    dry_run=False,
                    backup=args.backup,
                    rename=do_rename,
                    move=do_move,
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
        # Dry-run: no lock needed, no writes
        try:
            results = migrate_all(
                source_json_dir,
                db_path,
                dry_run=True,
                backup=False,
                rename=do_rename,
                move=do_move,
                fail_on_corrupt=args.fail_on_corrupt,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3

    if args.json_report:
        report = {k: _result_to_dict(v) for k, v in results.items()}
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        mode_label = "DRY-RUN" if dry_run else "APPLY"
        print(f"RIP transaction log migration — {mode_label}")
        print(f"  source dir : {source_json_dir}")
        print(f"  db path    : {db_path}")
        for r in results.values():
            _print_result(r)
        if dry_run:
            print("\n(Dry-run: no changes written. Use --apply to perform migration.)")

    # Determine exit code
    has_corrupt = any(r.has_errors for r in results.values())
    if has_corrupt and args.fail_on_corrupt:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
