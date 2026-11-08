"""Lexicon loader and validator (D136). The lexicon is data (lexicon.json), so adding or correcting a term is a
file edit with no code change. Standard library only."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).with_name("lexicon.json")
# D7 and D86: HIV information is sensitive and never appears in a worker-facing output. The NLP never extracts it.
FORBIDDEN_WORDS = frozenset({"aids", "art", "arv", "arvs", "antiretroviral", "antiretrovirals", "cd4"})   # and anything starting "hiv"


class LexiconError(ValueError):
    pass


@dataclass(frozen=True)
class Concept:
    name: str
    target: str                      # the structured field it can be compared with
    value: str | None                # the value in that field (None for the appetite signals)
    terms: tuple[tuple[str, ...], ...]   # each term as a token tuple


@dataclass(frozen=True)
class Lexicon:
    version: str
    status: str
    negation_before: tuple[tuple[str, ...], ...]
    negation_after: tuple[tuple[str, ...], ...]
    uncertain_before: tuple[tuple[str, ...], ...]
    contrast: frozenset[str]
    concepts: tuple[Concept, ...]
    window_before: int
    window_after: int

    def concept(self, name: str) -> Concept:
        for c in self.concepts:
            if c.name == name:
                return c
        raise KeyError(name)


def _phrases(raw, where: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw, list) or not raw:
        raise LexiconError(f"{where}: expected a non-empty list")
    out = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise LexiconError(f"{where}: terms must be non-empty strings")
        if item != item.casefold() or item != " ".join(item.split()):
            raise LexiconError(f"{where}: {item!r} must be lower case with single spaces")
        if where.startswith("concept") and any(w in FORBIDDEN_WORDS or w.startswith("hiv") for w in item.split(" ")):
            raise LexiconError(f"{where}: {item!r} touches a sensitive topic the NLP must not extract (D7, D86)")
        out.append(tuple(item.split(" ")))
    return tuple(out)


def parse(data: dict) -> Lexicon:
    try:
        concepts = []
        for name, c in data["concepts"].items():
            concepts.append(Concept(name, c["target"], c.get("value"), _phrases(c["terms"], f"concept {name}")))
        if not concepts:
            raise LexiconError("no concepts")
        return Lexicon(
            version=str(data["version"]), status=str(data["status"]),
            negation_before=_phrases(data["negation_before"], "negation_before"),
            negation_after=_phrases(data["negation_after"], "negation_after"),
            uncertain_before=_phrases(data["uncertain_before"], "uncertain_before"),
            contrast=frozenset(w for p in _phrases(data["contrast"], "contrast") for w in p),
            concepts=tuple(concepts),
            window_before=int(data["window_before"]), window_after=int(data["window_after"]))
    except (KeyError, TypeError, AttributeError) as e:
        raise LexiconError(f"malformed lexicon: {e!r}") from None


@lru_cache(maxsize=1)
def load_lexicon() -> Lexicon:
    return parse(json.loads(LEXICON_PATH.read_text(encoding="utf-8")))
