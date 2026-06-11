"""Deterministic folder template rules for recognised document types.

Pure string logic: never reads or writes the real filesystem.
"""

import re
from typing import Optional

# 與 filename normalizer 相同的非法字元概念，套用在單一 folder segment 上。
# "/" 與 "\\" 也在排除清單內，確保 segment 不會自行展開成多層路徑。
_INVALID_SEGMENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WHITESPACE = re.compile(r"\s+")
_MAX_SEGMENT_LEN = 100

UNKNOWN_BUSINESS = "unknown-business"
UNKNOWN_PERIOD = "unknown-period"
UNCLASSIFIED_FOLDER = "未分類/unknown-document/"


def sanitize_folder_segment(segment: str) -> str:
    """Remove path separators / invalid chars from a single folder segment."""
    cleaned = _INVALID_SEGMENT_CHARS.sub("", segment)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    # 移除前後的點，避免 ".."、"." 之類的相對路徑 segment
    cleaned = cleaned.strip(".")
    return cleaned[:_MAX_SEGMENT_LEN]


def _roc_to_billing_period(raw: str) -> Optional[str]:
    """Convert a ROC date string 'YYYMMDD' to 'YYYY-MM' (Western year)."""
    raw = raw.strip()
    if len(raw) == 7:
        try:
            western_year = int(raw[:3]) + 1911
            month = raw[3:5]
            return f"{western_year}-{month}"
        except ValueError:
            pass
    return None


def _get_field(fields: dict, *names: str) -> Optional[str]:
    for name in names:
        val = str(fields.get(name, "") or "").strip()
        if val:
            return val
    return None


def build_taipower_folder(fields: dict) -> tuple[str, float, list[str]]:
    """Build the archive folder for a Taipower bill.

    Format: 電費單/{business_id}/{billing_period}/
    Missing segments fall back to unknown-business / unknown-period.

    Returns (proposed_folder, confidence, warnings).
    Confidence starts at 1.0 and drops 0.3 per fallback segment.
    """
    warnings: list[str] = []

    business_id = _get_field(fields, "business_id")
    if business_id:
        business_id = sanitize_folder_segment(business_id) or UNKNOWN_BUSINESS
    if not business_id or business_id == UNKNOWN_BUSINESS:
        business_id = UNKNOWN_BUSINESS
        warnings.append("缺少 business_id，使用 unknown-business")

    # 優先使用既有 billing_period（YYYY-MM），否則由 ROC 日期推導
    billing_period = _get_field(fields, "billing_period")
    if billing_period:
        billing_period = sanitize_folder_segment(billing_period) or UNKNOWN_PERIOD
    else:
        raw_start = _get_field(fields, "billing_start_date")
        billing_period = _roc_to_billing_period(raw_start) if raw_start else None
    if not billing_period or billing_period == UNKNOWN_PERIOD:
        billing_period = UNKNOWN_PERIOD
        warnings.append("缺少計費期間，使用 unknown-period")

    confidence = max(0.0, 1.0 - len(warnings) * 0.3)
    folder = f"電費單/{business_id}/{billing_period}/"
    return folder, confidence, warnings
