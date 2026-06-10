"""Filename sanitization utilities."""

import re

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WHITESPACE = re.compile(r'\s+')
_RESERVED = frozenset([
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
])
_MAX_STEM_LEN = 200


def sanitize_filename(name: str) -> str:
    """Remove invalid chars and enforce cross-platform naming rules."""
    stem, _, ext = name.rpartition(".")
    if not stem:
        stem, ext = name, ""
    else:
        ext = "." + ext

    stem = _INVALID_CHARS.sub("", stem)
    stem = _WHITESPACE.sub(" ", stem).strip()
    stem = stem[:_MAX_STEM_LEN]

    if stem.upper() in _RESERVED:
        stem = "_" + stem

    return stem + ext
