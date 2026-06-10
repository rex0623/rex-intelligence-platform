"""Filename templates for recognised document types."""

from typing import Optional

from app.filename.normalizer import sanitize_filename

_REQUIRED_TAIPOWER = ["business_id", "electricity_no", "billing_period", "amount_due"]


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
        val = fields.get(name, "").strip()
        if val:
            return val
    return None


def build_taipower_filename(
    fields: dict,
    original_filename: str = "",
) -> tuple[Optional[str], float, list]:
    """Build a Taipower bill filename from extracted fields.

    Returns (proposed_filename, confidence, warnings).
    Confidence starts at 1.0 and drops 0.2 per missing required field.
    """
    warnings: list[str] = []
    found: dict[str, str] = {}

    val = _get_field(fields, "business_id")
    if val:
        found["business_id"] = sanitize_filename(val)
    else:
        warnings.append("缺少 business_id")

    val = _get_field(fields, "電號", "invoice_or_bill_code")
    if val:
        found["electricity_no"] = sanitize_filename(val)
    else:
        warnings.append("缺少電號")

    val = _get_field(fields, "billing_start_date")
    if val:
        period = _roc_to_billing_period(val)
        if period:
            found["billing_period"] = period
        else:
            warnings.append("計費期間格式無法解析")
    else:
        warnings.append("缺少計費期間")

    val = _get_field(fields, "payable_amount", "應繳金額")
    if val:
        amount = val.replace("元", "").replace(",", "").strip()
        if amount:
            found["amount_due"] = amount
        else:
            warnings.append("缺少應繳金額")
    else:
        warnings.append("缺少應繳金額")

    confidence = max(0.0, 1.0 - len(warnings) * 0.2)

    if not found:
        return None, confidence, warnings

    parts = {k: found.get(k, "unknown") for k in _REQUIRED_TAIPOWER}
    stem = (
        f"台電電費單"
        f"_{parts['business_id']}"
        f"_{parts['electricity_no']}"
        f"_{parts['billing_period']}"
        f"_{parts['amount_due']}"
    )
    proposed = sanitize_filename(stem) + ".pdf"
    return proposed, confidence, warnings
