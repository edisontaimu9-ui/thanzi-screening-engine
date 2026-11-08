"""Best-effort detection and masking of obvious personal identifiers in free text (D143).

This is a safety net, not a guarantee. It finds phone numbers, email addresses, long digit runs (national or
record numbers), dates, and names that follow a label such as "name:" or "mother". It cannot find a name written
without a label, a village, or a nickname. Free text that may identify a child must still be kept out of any place it
should not go (see I43). Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters: the first pattern to claim a stretch of text wins.
_PATTERNS = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\w.])(?:\+265|265|0)[ -]?\d(?:[ -]?\d){7,9}(?!\w)")),
    ("date", re.compile(r"(?<![\w.])(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-](?:\d{4}|\d{2}))(?![\w])")),
    ("id", re.compile(r"(?<![\w.])\d{8,}(?![\w])")),
    ("name", re.compile(r"\b(?i:name|mother|father|guardian|caregiver|caretaker)\b(?:\s+(?i:is|called)\b|\s*[:=-])?\s+"
                        r"([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){0,2})")),
)
TOKENS = {"email": "[EMAIL]", "phone": "[PHONE]", "date": "[DATE]", "id": "[ID]", "name": "[NAME]"}


@dataclass(frozen=True)
class Span:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: dict


def find_identifiers(text: str) -> tuple[Span, ...]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    spans: list[Span] = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            s, e = (m.start(1), m.end(1)) if kind == "name" else (m.start(), m.end())
            if not any(s < o.end and e > o.start for o in spans):
                spans.append(Span(kind, s, e))
    return tuple(sorted(spans, key=lambda x: x.start))


def contains_identifiers(text: str) -> bool:
    return bool(find_identifiers(text))


def redact(text: str) -> Redaction:
    spans = find_identifiers(text)
    out, pos, counts = [], 0, {}
    for sp in spans:
        out.append(text[pos:sp.start])
        out.append(TOKENS[sp.kind])
        counts[sp.kind] = counts.get(sp.kind, 0) + 1
        pos = sp.end
    out.append(text[pos:])
    return Redaction("".join(out), counts)
