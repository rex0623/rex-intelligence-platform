"""CLI / Mock LINE display formatting for MovePlan (dry-run output).

Display only: never touches the real filesystem.
"""

from app.folder_intelligence.schemas import MovePlan


def format_move_plan_for_cli(plan: MovePlan) -> str:
    """Format a MovePlan (with optional validation_report) for CLI output."""
    validation = plan.validation_report
    val_by_file = {}
    if validation is not None:
        val_by_file = {v.original_filename: v for v in validation.candidates}

    lines = ["小雷收到：已產生搬移計畫（dry-run）"]
    lines.append("- 模式：dry-run，不會實際搬移")
    lines.append(f"- 待處理檔案：{plan.total_files} 份")

    if validation is not None:
        lines.append("")
        lines.append("風險摘要：")
        lines.append(
            f"  低風險 {validation.low_count} 份"
            f" | 中風險 {validation.medium_count} 份"
            f" | 高風險 {validation.high_count} 份"
            f" | 封鎖 {validation.blocked_count} 份"
        )
        for issue in validation.plan_issues:
            lines.append(f"  ⚠ {issue}")

    lines.append("")
    lines.append("搬移計畫：")

    for i, c in enumerate(plan.candidates, 1):
        lines.append(f"  [{i}] {c.original_filename or c.original_path or '?'}")
        lines.append(f"      建議資料夾：{c.proposed_folder}")
        lines.append(f"      建議目標路徑：{c.proposed_path}")
        lines.append(f"      信心度：{c.confidence:.2f}")
        val = val_by_file.get(c.original_filename)
        if val is not None:
            lines.append(f"      風險：{val.risk_level}")
            if val.issues:
                lines.append(f"      問題：{'、'.join(val.issues)}")
        elif c.warnings:
            lines.append(f"      問題：{'、'.join(c.warnings)}")

    lines.append("")
    lines.append("目前僅產生 MovePlan（dry-run），尚未實際搬移任何檔案。")
    return "\n".join(lines)
