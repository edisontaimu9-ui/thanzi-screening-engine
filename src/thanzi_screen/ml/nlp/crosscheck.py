"""Compare what a free-text note says with what was entered in the structured fields (D141).

Advisory only. It can add a "check the entry" reason for a person to look at. It never changes a classification,
tier, referral or warning (D9), it never fills in a field, and the classification code never imports it (D142).
It takes plain values, not engine objects, so it imports nothing from the screening code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .extract import ABSENT, PRESENT, UNCERTAIN, Extraction, Mention, extract_mentions
from .lexicon import Lexicon, load_lexicon

SOURCE = "nlp_note_v1"
OEDEMA_RECORDED = {"+", "++", "+++"}

LABELS = {                       # worker-facing wording. DRAFT: needs clinician review (I49)
    "oedema": "swelling of the feet (oedema)",
    "convulsions": "convulsions",
    "unconsciousness": "unconsciousness",
    "lethargy": "lethargy (not alert)",
    "unable_to_drink": "being unable to drink or breastfeed",
    "diarrhoea": "diarrhoea",
    "malaria": "malaria",
}
FIXED_MESSAGES = {
    "note_poor_appetite_but_test_passed": "The note describes a poor appetite, but the appetite test is recorded as passed. Check the appetite entry.",
    "note_good_appetite_but_test_failed": "The note says the child eats well, but the appetite test is recorded as failed. Check the appetite entry.",
}


def _value(x):
    return getattr(x, "value", x)


@dataclass(frozen=True)
class NoteCheck:
    needed: bool
    reasons: tuple[str, ...]
    messages: tuple[str, ...]
    mentions: tuple[Mention, ...]
    truncated: bool = False
    source: str = SOURCE


def _message(reason: str) -> str:
    if reason in FIXED_MESSAGES:
        return FIXED_MESSAGES[reason]
    kind, concept = reason.split(":", 1)
    label = LABELS[concept]
    if kind == "note_not_recorded":
        return f"The note mentions {label}, but it is not recorded in the entry. Check the entry."
    if kind == "note_possible_not_recorded":
        return f"The note says {label} is possible, and it is not recorded in the entry. Check the entry."
    return f"The note says there is no {label}, but the entry records it. Check which is right."


def _best(mentions: Iterable[Mention], concept: str) -> set[str]:
    return {m.polarity for m in mentions if m.concept == concept}


def check_note(text: str, *, oedema=None, appetite=None, danger_signs: Iterable | None = None,
               complications: Iterable | None = None, lexicon: Lexicon | None = None) -> NoteCheck:
    """oedema: "none", "+", "++", "+++" or None (not entered). appetite: "passed", "failed", "not_done" or None.
    danger_signs / complications: the recorded values, or None when not assessed. Enum members are accepted."""
    lex = lexicon or load_lexicon()
    ex: Extraction = extract_mentions(text, lex)
    ds = None if danger_signs is None else {_value(x) for x in danger_signs}
    cp = None if complications is None else {_value(x) for x in complications}
    oed, app = _value(oedema), _value(appetite)
    reasons: list[str] = []

    def compare(concept: str, recorded: bool) -> None:
        pols = _best(ex.mentions, concept)
        if PRESENT in pols and not recorded:
            reasons.append(f"note_not_recorded:{concept}")
        elif UNCERTAIN in pols and not recorded and PRESENT not in pols:
            reasons.append(f"note_possible_not_recorded:{concept}")
        elif ABSENT in pols and recorded and PRESENT not in pols and UNCERTAIN not in pols:
            reasons.append(f"note_denies_recorded:{concept}")

    compare("oedema", oed in OEDEMA_RECORDED)
    for c in lex.concepts:
        if c.target == "danger_signs":
            compare(c.name, ds is not None and c.value in ds)
        elif c.target == "complications":
            compare(c.name, cp is not None and c.value in cp)

    poor = PRESENT in _best(ex.mentions, "poor_appetite") or ABSENT in _best(ex.mentions, "good_appetite")
    good = PRESENT in _best(ex.mentions, "good_appetite") or ABSENT in _best(ex.mentions, "poor_appetite")
    if poor != good:                                   # mixed signals in one note: say nothing rather than guess
        if poor and app == "passed":
            reasons.append("note_poor_appetite_but_test_passed")
        if good and app == "failed":
            reasons.append("note_good_appetite_but_test_failed")

    return NoteCheck(bool(reasons), tuple(reasons), tuple(_message(r) for r in reasons), ex.mentions, ex.truncated)
