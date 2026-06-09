"""Document parser utilities."""

import re


def parse_text(text: str) -> str:
    """Normalize PDF text for extraction."""
    if text is None:
        return ""

    normalized = text.replace("\r", "\n")
    normalized = re.sub(r"[\t ]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()
