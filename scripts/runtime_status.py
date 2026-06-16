"""Phase 22B — Runtime Status / Diagnostics CLI (read-only).

Reports current backend settings, runtime JSON file existence/size, and
SQLite rip.db schema_version / table row counts.

Usage
-----
  # Human-readable summary
  poetry run python scripts/runtime_status.py

  # Machine-readable output
  poetry run python scripts/runtime_status.py --json-report

Notes
-----
  - Pure read-only: never writes any file, never creates runtime/rip.db,
    never calls initialize_sqlite_schema(), never acquires the runtime lock.
  - No --apply flag exists; this script cannot perform any destructive or
    write action.

Exit codes
----------
  0  Success
  1  Unexpected error
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="runtime_status",
        description=(
            "Report current RIP runtime backend status (read-only; "
            "no writes, no lock, no destructive actions)."
        ),
    )
    p.add_argument(
        "--json-report",
        action="store_true",
        default=False,
        help="Output report as JSON instead of human-readable text.",
    )
    return p


def _print_file_status(label: str, file_status) -> None:
    if file_status.exists:
        print(f"  {label:<28}: exists ({file_status.size_bytes} bytes)")
    else:
        print(f"  {label:<28}: not found")


def _print_status(status) -> None:
    print("RIP runtime status")
    print(f"  transaction log backend     : {status.transaction_log_backend}")
    print(f"  approval store backend      : {status.approval_store_backend}")
    print(f"  runtime dir                 : {status.runtime_dir}")
    print()
    _print_file_status("approvals.json", status.approvals_json)
    _print_file_status("rename_transactions.json", status.rename_transactions_json)
    _print_file_status("move_transactions.json", status.move_transactions_json)
    print()
    sqlite_status = status.sqlite
    if sqlite_status.exists:
        print(f"  runtime/rip.db              : exists")
        print(f"    schema_version            : {sqlite_status.schema_version}")
        print(f"    rename_transactions rows  : {sqlite_status.rename_transactions_count}")
        print(f"    move_transactions rows    : {sqlite_status.move_transactions_count}")
        print(f"    approvals rows            : {sqlite_status.approvals_count}")
    else:
        print(f"  runtime/rip.db              : not found")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    from app.core.runtime_status import collect_runtime_status

    try:
        status = collect_runtime_status()
    except Exception as exc:
        print(f"ERROR: Unexpected runtime status error: {exc}", file=sys.stderr)
        return 1

    if args.json_report:
        print(json.dumps(dataclasses.asdict(status), indent=2, ensure_ascii=False))
    else:
        _print_status(status)

    return 0


if __name__ == "__main__":
    sys.exit(main())
