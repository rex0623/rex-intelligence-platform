"""Field extractor for structured documents."""

import re
from typing import List

from app.document.schemas import DocumentField


# ---------------------------------------------------------------------------
# Legacy labeled-field patterns (English-format and labeled billing documents)
# ---------------------------------------------------------------------------
FIELD_PATTERNS = [
    (
        "電號",
        r"(?:電號|account\s*(?:number|no\.?)|acct(?:ount)?\s*no\.?)[:：]?\s*([A-Za-z0-9\-]+)",
        0.95,
    ),
    (
        "計費期間",
        r"(?:計費期間|billing\s*period)[:：]?\s*([0-9\-/]+(?:\s*to\s*[0-9\-/]+)?)",
        0.9,
    ),
    (
        "應繳金額",
        r"(?:應繳金額|amount\s*due|total\s*due|due\s*amount)[:：]?\s*([\d,]+(?:\.\d{1,2})?)",
        0.9,
    ),
    (
        "用戶名稱",
        r"(?:用戶名稱|customer\s*name|name)[:：]?\s*([A-Za-z一-鿿0-9\s]+)",
        0.85,
    ),
    (
        "地址",
        r"(?:地址|address)[:：]?\s*([A-Za-z一-鿿0-9\s\-]+)",
        0.85,
    ),
]

# ---------------------------------------------------------------------------
# TaiPower real-bill compiled patterns
# ---------------------------------------------------------------------------

# ROC billing period: "YYY MM DD YYY MM DD" (both dates on the same line,
# separated by one or more spaces after parse_text normalization)
_DATE_PERIOD = re.compile(
    r'(\d{3})\s+(\d{2})\s+(\d{2})\s+(\d{3})\s+(\d{2})\s+(\d{2})'
)

# Bill code: exactly 2 uppercase letters followed by 8 digits (e.g. XB17839034)
_BILL_CODE = re.compile(r'(?<![A-Za-z\d])([A-Z]{2}\d{8})(?![A-Za-z\d])')

# Site address: a line that contains 市/縣 → 區/鄉/鎮 → 路/街/巷 (in that order)
_SITE_ADDR = re.compile(r'[^\n]*[市縣][^\n]*[區鄉鎮][^\n]*[路街巷][^\n]*')

# Business ID (統一編號): exactly 8 digits on their own line
_BUSINESS_ID = re.compile(r'^(\d{8})$', re.MULTILINE)

# All amounts ending in 元
_AMOUNTS = re.compile(r'(\d+)元')


def _extract_taipower_fields(text: str) -> List[DocumentField]:
    """Extract TaiPower bill-specific fields from normalized text."""
    fields: List[DocumentField] = []

    # billing_start_date / billing_end_date
    m = _DATE_PERIOD.search(text)
    if m:
        start = m.group(1) + m.group(2) + m.group(3)
        end = m.group(4) + m.group(5) + m.group(6)
        fields.append(DocumentField(name="billing_start_date", value=start, confidence=0.9))
        fields.append(DocumentField(name="billing_end_date", value=end, confidence=0.9))

    # invoice_or_bill_code
    m = _BILL_CODE.search(text)
    if m:
        fields.append(DocumentField(name="invoice_or_bill_code", value=m.group(1), confidence=0.95))

    # site_address — prefer last match (site address follows billing address in the document)
    addrs = _SITE_ADDR.findall(text)
    if addrs:
        fields.append(DocumentField(name="site_address", value=addrs[-1].strip(), confidence=0.85))

    # business_id — prefer last standalone 8-digit line
    bids = _BUSINESS_ID.findall(text)
    if bids:
        fields.append(DocumentField(name="business_id", value=bids[-1], confidence=0.85))

    # amount_candidates and payable_amount
    amounts = _AMOUNTS.findall(text)
    if amounts:
        candidates = "、".join(f"{a}元" for a in amounts)
        fields.append(DocumentField(name="amount_candidates", value=candidates, confidence=0.8))
        fields.append(DocumentField(name="payable_amount", value=f"{amounts[-1]}元", confidence=0.75))

    return fields


def extract_fields(text: str) -> List[DocumentField]:
    """Extract structured fields from normalized document text."""
    if not text:
        return []

    fields: List[DocumentField] = []
    seen: set[str] = set()

    for name, pattern, confidence in FIELD_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value and name not in seen:
                fields.append(DocumentField(name=name, value=value, confidence=confidence))
                seen.add(name)

    for field in _extract_taipower_fields(text):
        if field.name not in seen:
            fields.append(field)
            seen.add(field.name)

    return fields
