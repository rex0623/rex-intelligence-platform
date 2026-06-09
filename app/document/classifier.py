"""Document classifier."""

from app.document.schemas import DocumentType


def classify_document_type(text: str) -> dict[str, object]:
    """Classify document type from text content."""
    if not text:
        return {"document_type": DocumentType.unknown, "confidence": 0.5}

    normalized = text.lower()
    if "台灣電力公司" in normalized or "電費通知單" in normalized or "taiwan power company" in normalized or "electric bill" in normalized:
        return {"document_type": DocumentType.taipower_bill, "confidence": 0.95}
    if "發票" in normalized or "invoice" in normalized:
        return {"document_type": DocumentType.invoice, "confidence": 0.9}
    if "契約" in normalized or "contract" in normalized:
        return {"document_type": DocumentType.contract, "confidence": 0.9}

    return {"document_type": DocumentType.unknown, "confidence": 0.5}
