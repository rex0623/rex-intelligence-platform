"""Field extractor for structured documents."""

import re
from typing import List

from app.document.schemas import DocumentField


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
        r"(?:用戶名稱|customer\s*name|name)[:：]?\s*([A-Za-z\u4e00-\u9fff0-9\s]+)",
        0.85,
    ),
    (
        "地址",
        r"(?:地址|address)[:：]?\s*([A-Za-z\u4e00-\u9fff0-9\s\-]+)",
        0.85,
    ),
]


def extract_fields(text: str) -> List[DocumentField]:
    """Extract structured fields from normalized document text."""
    fields: List[DocumentField] = []

    if not text:
        return fields

    for name, pattern, confidence in FIELD_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                fields.append(DocumentField(name=name, value=value, confidence=confidence))

    return fields
