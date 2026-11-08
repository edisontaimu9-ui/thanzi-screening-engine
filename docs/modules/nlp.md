# Module: natural language processing, `thanzi_screen.ml.nlp` (add-on, not a numbered phase)

Reads a health worker's free-text note and compares it with the structured entry. Advisory only. It never changes a
classification, tier, referral or warning (D9). Standard library only, offline, English, deterministic. **Draft, not
validated** (I48, I49).

## What it does
- **Extract (`extract_mentions`).** Finds findings the screening rules already know (CMAM 2016 Table 5 items: oedema,
  convulsions, unconsciousness, lethargy, unable to drink or breastfeed, diarrhoea, malaria, poor or good appetite) and
  marks each *present*, *absent* or *uncertain*. "No oedema", "denies convulsions", "malaria negative" are *absent*;
  "? oedema", "possible malaria" are *uncertain*. A comma, full stop, semicolon, line break or a word such as "but" ends
  the reach of a negation (D138). One typing error in a long word is tolerated ("unconcious", D139).
- **Cross-check (`check_note`).** Compares the mentions with the recorded oedema grade, appetite result, danger signs and
  complications, and returns a `NoteCheck` with reasons and plain-language messages, like the Phase 4 review flag.
  Reasons: `note_not_recorded:<finding>`, `note_possible_not_recorded:<finding>`, `note_denies_recorded:<finding>`,
  `note_poor_appetite_but_test_passed`, `note_good_appetite_but_test_failed`. A field that was never assessed counts as
  not recorded. Mixed appetite statements in one note give no reason rather than a guess.
- **Privacy (`redact`, `find_identifiers`, `contains_identifiers`).** Best-effort masking of phone numbers, email
  addresses, dates, long digit runs and names that follow a label ("name:", "mother", "guardian"). It misses a name
  written without a label, villages and nicknames. It is a safety net, not a guarantee (D143, I52).

## Use
```python
from thanzi_screen.ml.nlp import check_note, redact
from thanzi_screen.rules import ClinicalInputs

ci = ClinicalInputs(muac_cm=11.0)
r = check_note("Swelling of both feet, not eating well.", oedema=ci.oedema, appetite=ci.appetite,
               danger_signs=ci.danger_signs, complications=ci.complications)
r.needed, r.reasons, r.messages          # True, ('note_not_recorded:oedema',), ("The note mentions swelling of the feet ...",)
clean = redact(note_text).text           # [NAME], [PHONE], [DATE], [ID], [EMAIL]
```

## Rules it keeps
- **Advisory only (D141).** It adds a reason for a person to look at. It never fills in a field and never alters a result.
- **Independent both ways (D142).** `ml/nlp` imports nothing from `thanzi_screen`. Nothing else imports it. Both are
  enforced by AST tests that were checked to fail when broken. It takes plain values, not engine objects.
- **No patient text in results (D140).** A `Mention` carries the concept, the polarity and the *lexicon term* that matched,
  never the note's own words. A test checks that made-up names do not appear in a result.
- **No HIV (D7, D86).** The lexicon has no HIV concept and the loader refuses any term that touches it.
- **Data, not code (D136).** `lexicon.json` holds every term and trigger. Adding or correcting one is a file edit.
- **Transparent, not trained (D137, D144).** There is no real, authorised note data to train or validate a model. A model
  trained on notes we wrote ourselves would only learn our own phrasing. Every result traces to a lexicon term and a trigger.
- **Not wired to the API (D144).** No route, schema or `openapi.json` change. Screening behaviour is unchanged.

## Limits (I51)
Negation ends at a comma, so "denies fever, convulsions or vomiting" reads "convulsions" as present (it errs towards
asking for a check). No handling of time ("had convulsions last year"), of family history ("his brother had fits"), or
of who is described. English only. Spelling variants not in the lexicon are missed, except the one-typo case. A note that
says "fever" is not mapped to the high-fever danger sign, because the note cannot give the temperature.

## Tests (`tests/ml/test_nlp.py`, 68)
Lexicon maps only to values the engine already has; HIV refused; malformed lexicon rejected; 30 synthetic gold notes
(a **regression set, not validation**, written by the same team that wrote the lexicon); negation scope and bounds;
longest match; typo tolerance and its limits; Unicode and spacing; type and length guards; determinism; no patient text
in results; every cross-check reason; clean notes raise nothing; redaction, idempotence and clinical numbers left alone;
isolation in both directions; standard library only; lexicon shipped in package data.
