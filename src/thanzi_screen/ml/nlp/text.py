"""Text normalisation, clause splitting and tokenising. Standard library only."""
from __future__ import annotations

import re
import unicodedata

MAX_CHARS = 10_000      # longer notes are cut here and reported as truncated
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "`": "'"})
_SPLIT = re.compile(r"[.;:!\n\r]+|,")
_TOKEN = re.compile(r"[a-z0-9']+|\?")


def normalise(text: str) -> str:
    """NFKC, case-folded, straight apostrophes, single spaces."""
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).casefold()
    return " ".join(text.split())


def clauses(text: str, contrast: frozenset[str]) -> list[list[str]]:
    """Split a normalised note into token lists. A full stop, semicolon, colon, comma, line break or a
    contrast word ("but", "however", ...) ends a clause, so a negation never reaches across one (D138)."""
    out: list[list[str]] = []
    for piece in _SPLIT.split(text):
        current: list[str] = []
        for tok in _TOKEN.findall(piece):
            if tok in contrast:
                if current:
                    out.append(current)
                current = []
            else:
                current.append(tok)
        if current:
            out.append(current)
    return out
