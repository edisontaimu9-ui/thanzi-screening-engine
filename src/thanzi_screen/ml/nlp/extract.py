"""Find clinical mentions in a free-text note and say whether each is present, absent or uncertain (D137, D138).

A transparent lexicon-and-scope method, not a trained model: every result can be traced to a lexicon term and a
trigger word. Standard library only. The result never repeats the patient's text, only lexicon terms (D140).
"""
from __future__ import annotations

from dataclasses import dataclass

from .lexicon import Lexicon, load_lexicon
from .text import MAX_CHARS, clauses, normalise

PRESENT, ABSENT, UNCERTAIN = "present", "absent", "uncertain"
FUZZY_MIN_LEN = 8        # only long single words may match with one typing error (D139)


@dataclass(frozen=True)
class Mention:
    concept: str
    polarity: str            # "present" | "absent" | "uncertain"
    term: str                # the lexicon term that matched, never the patient's own words


@dataclass(frozen=True)
class Extraction:
    mentions: tuple[Mention, ...]
    truncated: bool = False


def _one_edit(a: str, b: str) -> bool:
    """True when a and b differ by one insertion, deletion, substitution or swap of neighbours."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1 or a[0] != b[0]:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def _matches(tokens: list[str], term: tuple[str, ...]) -> list[int]:
    n, hits = len(term), []
    for i in range(len(tokens) - n + 1):
        window = tokens[i:i + n]
        if window == list(term):
            hits.append(i)
        elif n == 1 and len(term[0]) >= FUZZY_MIN_LEN and len(window[0]) >= FUZZY_MIN_LEN and _one_edit(window[0], term[0]):
            hits.append(i)
    return hits


def _find(tokens: list[str], phrases, start: int, stop: int) -> bool:
    """Does any phrase sit wholly inside tokens[start:stop]?"""
    seg = tokens[max(start, 0):stop]
    for ph in phrases:
        n = len(ph)
        for i in range(len(seg) - n + 1):
            if tuple(seg[i:i + n]) == ph:
                return True
    return False


def _polarity(tokens: list[str], i: int, j: int, lex: Lexicon) -> str:
    before = (max(i - lex.window_before, 0), i)
    after = (j, j + lex.window_after)
    if _find(tokens, lex.negation_before, *before) or _find(tokens, lex.negation_after, *after):
        return ABSENT
    if _find(tokens, lex.uncertain_before, i - 3, i) or "?" in tokens[j:j + 1]:
        return UNCERTAIN
    return PRESENT


def extract_mentions(text: str, lexicon: Lexicon | None = None) -> Extraction:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    lex = lexicon or load_lexicon()
    truncated = len(text) > MAX_CHARS
    found: list[Mention] = []
    for tokens in clauses(normalise(text[:MAX_CHARS]), lex.contrast):
        cands = []                                           # (length, start, end, concept, term)
        for c in lex.concepts:
            for term in c.terms:
                for i in _matches(tokens, term):
                    cands.append((len(term), i, i + len(term), c.name, " ".join(term)))
        cands.sort(key=lambda x: (-x[0], x[1], x[3]))        # longest first, so "not eating well" beats "eating well"
        taken: set[int] = set()
        chosen = []
        for length, i, j, concept, term in cands:
            span = set(range(i, j))
            if span & taken:
                continue
            taken |= span
            chosen.append((i, j, concept, term))
        for i, j, concept, term in sorted(chosen):
            found.append(Mention(concept, _polarity(tokens, i, j, lex), term))
    return Extraction(tuple(found), truncated)
