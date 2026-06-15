"""Phase 21B — Approval prune / expiry cleanup CLI.

Removes expired, executed, rejected, or old approvals from the approval store.
Works with both JSON and SQLite backends (reads APPROVAL_STORE_BACKEND from env).

Usage
-----
  # Preview only (default — no writes)
  poetry run python scripts/prune_approvals.py

  # Apply prune (acquires runtime lock)
  poetry run python scripts/prune_approvals.py --apply

  # Remove expired + executed + rejected approvals older than 30 days
  poetry run python scripts/prune_approvals.py --apply \\
      --remove-executed --remove-rejected --max-age-days 30

  # Machine-readable output
  poetry run python scripts/prune_approvals.py --json-report

Notes
-----
  - By default only expired approvals are removed (remove_expired=True).
  - Live-pending approvals (status=pending, not yet expired) are never removed
    by --max-age-days, regardless of age.
  - This script does NOT change APPROVAL_STORE_BACKEND.
  - approvals.json and rip.db are only modified under --apply.

Exit codes
----------
  0  Success (dry-run or apply, including "nothing to prune")
  1  Runtime lock busy
  3  Unexpected error
"""

from __future__ import annotations

import argparse
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prune_approvals",
        description=(
            "Remove expired, executed, rejected, or old approvals from the "
            "approval store. Defaults to dry-run; use --apply to write."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview prune without writing (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Perform prune. Acquires the runtime lock.",
    )
    p.add_argument(
        "--remove-executed",
        action="store_true",
        default=False,
        help="Also remove approvals with execution_status == 'executed'.",
    )
    p.add_argument(
        "--remove-rejected",
        action="store_true",
        default=False,
        help="Also remove approvals with status == 'rejected'.",
    )
    p.add_argument(
        "--max-age-days",
        metavar="N",
        type=int,
        default=None,
        help=(
            "Remove approvals older than N days. "
            "Live pending (not yet expired) approvals are never removed by this flag."
        ),
    )
    p.add_argument(
        "--json-report",
        action="store_true",
        default=False,
        help="Output report as JSON instead of human-readable text.",
    )
    return p


def _result_to_dict(r) -> dict:
    return {
        "dry_run": r.dry_run,
        "total_before": r.total_before,
        "total_after": r.total_after,
        "pruned_count": r.pruned_count,
        "retained_count": r.retained_count,
        "pruned_expired": r.pruned_expired,
        "pruned_executed": r.pruned_executed,
        "pruned_rejected": r.pruned_rejected,
        "pruned_old": r.pruned_old,
        "pruned_approval_ids": r.pruned_approval_ids,
    }


def _print_result(r, *, mode_label: str) -> None:
    print(f"RIP approval prune — {mode_label}")
    print(f"  total before : {r.total_before}")
    print(f"  total after  : {r.total_after}")
    print(f"  pruned       : {r.pruned_count}")
    print(f"    expired    : {r.pruned_expired}")
    print(f"    executed   : {r.pruned_executed}")
    print(f"    rejected   : {r.pruned_rejected}")
    print(f"    old        : {r.pruned_old}")
    print(f"  retained     : {r.retained_count}")
    if r.dry_run:
        print("\n(Dry-run: no changes written. Use --apply to perform prune.)")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    apply_mode = args.apply
    dry_run = not apply_mode

    from app.core.approval_manager_factory import make_approval_manager

    if apply_mode:
        from app.core.runtime_lock import RuntimeLockBusy, acquire_runtime_lock

        try:
            with acquire_runtime_lock():
                manager = make_approval_manager()
                result = manager.prune_approvals(
                    dry_run=False,
                    remove_executed=args.remove_executed,
                    remove_rejected=args.remove_rejected,
                    max_age_days=args.max_age_days,
                )
        except RuntimeLockBusy:
            print(
                "ERROR: 另一個 RIP 操作正在執行中，請等待完成後再重試。",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            print(f"ERROR: Unexpected prune error: {exc}", file=sys.stderr)
            return 3
    else:
        try:
            manager = make_approval_manager()
            result = manager.prune_approvals(
                dry_run=True,
                remove_executed=args.remove_executed,
                remove_rejected=args.remove_rejected,
                max_age_days=args.max_age_days,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3

    mode_label = "DRY-RUN" if dry_run else "APPLY"

    if args.json_report:
        print(json.dumps(_result_to_dict(result), indent=2, ensure_ascii=False))
    else:
        _print_result(result, mode_label=mode_label)

    return 0


if __name__ == "__main__":
    sys.exit(main())
