"""Document parser utilities."""

import re


def _fw2hw(text: str) -> str:
    """Convert full-width digits, ASCII letters, and special spaces to half-width."""
    buf = []
    for ch in text:
        cp = ord(ch)
        if 0xFF10 <= cp <= 0xFF19:       # ０-９
            buf.append(chr(cp - 0xFF10 + ord('0')))
        elif 0xFF21 <= cp <= 0xFF3A:     # Ａ-Ｚ
            buf.append(chr(cp - 0xFF21 + ord('A')))
        elif 0xFF41 <= cp <= 0xFF5A:     # ａ-ｚ
            buf.append(chr(cp - 0xFF41 + ord('a')))
        elif cp in (0x3000, 0x00A0, 0x202F, 0xFEFF):  # ideographic/NBSP/narrow NBSP/BOM
            buf.append(' ')
        else:
            buf.append(ch)
    return ''.join(buf)


def parse_text(text: str) -> str:
    """Normalize PDF text for extraction."""
    if text is None:
        return ""

    normalized = text.replace("\r", "\n")
    normalized = _fw2hw(normalized)
    normalized = re.sub(r"[\t ]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()
