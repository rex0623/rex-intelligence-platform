"""Document classifier."""

from app.document.schemas import DocumentType

_TAIPOWER_KEYWORDS = [
    "電費通知單",
    "本公司購電",
    "台灣電力公司",
    "購電電費",
    "應付總金額",
    "taiwan power company",
    "electric bill",
]


def _is_taipower(normalized: str) -> bool:
    if any(kw in normalized for kw in _TAIPOWER_KEYWORDS):
        return True
    # 「電號」+ 「計費期間」組合
    if "電號" in normalized and "計費期間" in normalized:
        return True
    return False


def classify_document_type(text: str) -> dict[str, object]:
    """Classify document type from text content.

    taipower_bill has highest priority so that embedded invoice info on
    a power bill does not cause a mis-classification.
    """
    if not text:
        return {"document_type": DocumentType.unknown, "confidence": 0.5}

    normalized = text.lower()

    if _is_taipower(normalized):
        return {"document_type": DocumentType.taipower_bill, "confidence": 0.95}
    if "發票" in normalized or "統一發票" in normalized or "invoice" in normalized:
        return {"document_type": DocumentType.invoice, "confidence": 0.9}
    if "契約" in normalized or "contract" in normalized:
        return {"document_type": DocumentType.contract, "confidence": 0.9}

    return {"document_type": DocumentType.unknown, "confidence": 0.5}
