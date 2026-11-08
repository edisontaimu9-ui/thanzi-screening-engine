"""NLP for free-text notes (D135-D144): extraction, negation, cross-check, privacy, isolation, packaging."""
import ast
import tomllib
from pathlib import Path

import pytest

from tests.ml.nlp_gold import GOLD
from thanzi_screen.ml.nlp import (Lexicon, LexiconError, check_note, contains_identifiers, extract_mentions,
                                  find_identifiers, load_lexicon, redact)
from thanzi_screen.ml.nlp import lexicon as lexmod
from thanzi_screen.ml.nlp.extract import MAX_CHARS, _one_edit
from thanzi_screen.rules import Appetite, Complication, DangerSign, OedemaGrade

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "thanzi_screen"
NLP = SRC / "ml" / "nlp"


def pairs(text):
    return {(m.concept, m.polarity) for m in extract_mentions(text).mentions}


# ---- lexicon: traceable to the engine, nothing sensitive ----
def test_every_concept_maps_to_a_value_the_engine_already_has():
    lex = load_lexicon()
    danger = {d.value for d in DangerSign}
    comps = {c.value for c in Complication}
    for c in lex.concepts:
        if c.target == "danger_signs":
            assert c.value in danger, c
        elif c.target == "complications":
            assert c.value in comps, c
        elif c.target == "oedema":
            assert c.value == "present"
        else:
            assert c.target == "appetite" and c.value is None, c
    assert {a.value for a in Appetite} >= {"passed", "failed"}
    assert {o.value for o in OedemaGrade} >= {"none", "+"}


def test_lexicon_has_no_hiv_terms_and_the_loader_refuses_them():
    lex = load_lexicon()
    for c in lex.concepts:
        for term in c.terms:
            assert not any(w.startswith("hiv") or w in lexmod.FORBIDDEN_WORDS for w in term), (c.name, term)
    bad = {"version": "x", "status": "x", "window_before": 5, "window_after": 3, "contrast": ["but"],
           "negation_before": ["no"], "negation_after": ["absent"], "uncertain_before": ["?"],
           "concepts": {"x": {"target": "complications", "value": "malaria", "terms": ["hiv positive"]}}}
    with pytest.raises(LexiconError):
        lexmod.parse(bad)


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("concepts"),
    lambda d: d["concepts"]["malaria"].update(terms=[]),
    lambda d: d["concepts"]["malaria"].update(terms=["Malaria"]),
    lambda d: d.pop("window_before"),
])
def test_malformed_lexicon_is_rejected(mutate):
    import json
    data = json.loads(lexmod.LEXICON_PATH.read_text(encoding="utf-8"))
    mutate(data)
    with pytest.raises(LexiconError):
        lexmod.parse(data)


def test_lexicon_is_marked_draft():
    assert "DRAFT" in load_lexicon().status and isinstance(load_lexicon(), Lexicon)


# ---- extraction ----
@pytest.mark.parametrize("text,expected", GOLD, ids=[str(i) for i in range(len(GOLD))])
def test_gold_notes(text, expected):
    assert pairs(text) == expected


def test_negation_does_not_cross_a_comma_or_a_contrast_word():
    assert pairs("no oedema, convulsions") == {("oedema", "absent"), ("convulsions", "present")}
    assert pairs("no oedema but convulsions") == {("oedema", "absent"), ("convulsions", "present")}
    assert pairs("no oedema. convulsions") == {("oedema", "absent"), ("convulsions", "present")}


def test_negation_window_is_bounded():
    assert pairs("no new complaint at all today from mother about the child and oedema") == {("oedema", "present")}


def test_longest_match_wins_over_a_shorter_overlap():
    assert pairs("not eating well") == {("poor_appetite", "present")}      # not also "good appetite"
    assert pairs("eating well") == {("good_appetite", "present")}


def test_one_typing_error_in_a_long_word_still_matches_but_short_words_do_not():
    assert pairs("convulsionss at night") == {("convulsions", "present")}
    assert pairs("unconscius") == {("unconsciousness", "present")}
    assert pairs("oedma") == set()                  # too short to risk a fuzzy match
    assert pairs("fit") == set()


def test_edit_distance_helper():
    assert _one_edit("abcdefgh", "abcdefgh") and _one_edit("abcdefgh", "abcdefg") and _one_edit("abcdefgh", "abcdfegh")
    assert _one_edit("abcdefgh", "abcdxfgh") and _one_edit("abcdefg", "abcdefgh")
    assert not _one_edit("abcdefgh", "abcdxxgh") and not _one_edit("abcdefgh", "xbcdefgh") and not _one_edit("abcdefgh", "abcdef")


def test_unicode_case_spacing_and_curly_apostrophes():
    assert pairs("CAN\u2019T   DRINK") == {("unable_to_drink", "present")}
    assert pairs("OEDEMA\n\nseen") == {("oedema", "present")}
    assert pairs("Ｏｅｄｅｍａ") == {("oedema", "present")}           # full-width letters, NFKC


def test_inputs_must_be_text_and_long_notes_are_cut():
    for bad in (None, 5, b"oedema", ["oedema"]):
        with pytest.raises(TypeError):
            extract_mentions(bad)
        with pytest.raises(TypeError):
            find_identifiers(bad)
    ex = extract_mentions("x " * (MAX_CHARS // 2 + 10) + " oedema")
    assert ex.truncated and not ex.mentions
    assert not extract_mentions("oedema").truncated


def test_deterministic():
    t = "Child has swelling of both feet, no convulsions. Mother says not eating well."
    assert extract_mentions(t) == extract_mentions(t)


def test_results_never_repeat_the_patients_words():
    note = "Zzyzx has swelling of both feet and is not eating well. Zzyzx mother Qwerty."
    r = check_note(note, oedema="none", appetite="passed", danger_signs=set(), complications=set())
    blob = repr(r).lower()
    assert "zzyzx" not in blob and "qwerty" not in blob
    assert all(m.term in {" ".join(t) for c in load_lexicon().concepts for t in c.terms} for m in r.mentions)


# ---- cross-check ----
def test_oedema_in_the_note_but_none_recorded():
    r = check_note("swelling of both feet", oedema=OedemaGrade.NONE)
    assert r.needed and r.reasons == ("note_not_recorded:oedema",) and "swelling of the feet" in r.messages[0]
    assert not check_note("swelling of both feet", oedema="++").needed
    assert check_note("swelling of both feet", oedema=None).needed        # not entered counts as not recorded


def test_note_denies_what_is_recorded():
    r = check_note("no oedema", oedema=OedemaGrade.PLUS)
    assert r.reasons == ("note_denies_recorded:oedema",)
    r = check_note("denies convulsions", danger_signs={DangerSign.CONVULSIONS})
    assert r.reasons == ("note_denies_recorded:convulsions",)
    assert not check_note("denies convulsions", danger_signs=set()).needed


def test_danger_signs_and_complications():
    r = check_note("lethargic, unable to drink, diarrhoea and malaria", danger_signs=frozenset(), complications=frozenset())
    assert set(r.reasons) == {"note_not_recorded:lethargy", "note_not_recorded:unable_to_drink",
                              "note_not_recorded:diarrhoea", "note_not_recorded:malaria"}
    ok = check_note("lethargic, unable to drink, diarrhoea and malaria",
                    danger_signs={DangerSign.LETHARGY_NOT_ALERT, DangerSign.UNABLE_TO_DRINK_OR_BREASTFEED},
                    complications={Complication.DIARRHOEA, Complication.MALARIA})
    assert not ok.needed
    assert check_note("convulsions", danger_signs=None).needed           # not assessed counts as not recorded


def test_uncertain_mentions_get_their_own_softer_reason():
    r = check_note("? convulsions", danger_signs=set())
    assert r.reasons == ("note_possible_not_recorded:convulsions",) and "possible" in r.messages[0]
    assert not check_note("? convulsions", danger_signs={DangerSign.CONVULSIONS}).needed


def test_appetite_cross_check():
    assert check_note("not eating well", appetite=Appetite.PASSED).reasons == ("note_poor_appetite_but_test_passed",)
    assert check_note("eating well", appetite=Appetite.FAILED).reasons == ("note_good_appetite_but_test_failed",)
    assert not check_note("not eating well", appetite=Appetite.FAILED).needed
    assert not check_note("eating well", appetite=Appetite.PASSED).needed
    assert not check_note("not eating well", appetite=Appetite.NOT_DONE).needed
    assert not check_note("not eating well", appetite=None).needed


def test_mixed_appetite_signals_say_nothing():
    assert not check_note("eating well in the morning, poor appetite at night", appetite="passed").needed


def test_clean_and_empty_notes_raise_nothing():
    for t in ("", "Routine visit. Child alert and playful.", "MUAC 11.5 cm, weight 8.2 kg, age 14 months."):
        r = check_note(t, oedema="none", appetite="passed", danger_signs=set(), complications=set())
        assert not r.needed and r.reasons == () and r.messages == ()


def test_reasons_and_messages_line_up_and_source_is_labelled():
    r = check_note("swollen feet, convulsions, malaria", oedema="none", danger_signs=set(), complications=set())
    assert len(r.reasons) == len(r.messages) == 3 and r.source == "nlp_note_v1" and r.mentions


# ---- privacy ----
def test_redaction_masks_identifiers_and_keeps_clinical_numbers():
    note = ("Name: Chikondi Banda, mother Mary Phiri, phone 0991 234 567 or +265 888 123 456, seen 12/11/2026, "
            "ID 12345678, a.b@example.mw. MUAC 11.5 cm, weight 8.2 kg, age 14 months, oedema +")
    r = redact(note)
    assert r.text == ("Name: [NAME], mother [NAME], phone [PHONE] or [PHONE], seen [DATE], ID [ID], [EMAIL]. "
                      "MUAC 11.5 cm, weight 8.2 kg, age 14 months, oedema +")
    assert r.counts == {"name": 2, "phone": 2, "date": 1, "id": 1, "email": 1}
    assert redact(r.text).text == r.text and not redact(r.text).counts          # idempotent


@pytest.mark.parametrize("text", ["MUAC 11.5 cm", "weight 8.2 kg", "age 14 months", "length 72.5 cm, z -2.3", "0.5 kg gained",
                                  "mother is breastfeeding", "Appetite test passed", "seen on day 14"])
def test_ordinary_clinical_text_is_left_alone(text):
    assert redact(text).text == text and not contains_identifiers(text)


def test_spans_do_not_overlap_and_are_ordered():
    spans = find_identifiers("Name: Jane Doe 0991234567 jane@x.org 2026-11-08")
    assert [s.kind for s in spans] == ["name", "phone", "email", "date"]
    assert all(a.end <= b.start for a, b in zip(spans, spans[1:]))


# ---- isolation (D142) and packaging ----
def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield 0, a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or ""


def test_nlp_imports_nothing_from_the_screening_code():
    for path in NLP.glob("*.py"):
        for level, module in _imports(path):
            if level == 0:
                assert not module.startswith("thanzi_screen"), (path.name, module)
            else:
                assert level == 1, f"{path.name} reaches outside the nlp package"


def test_nothing_else_imports_the_nlp_package():
    offenders = []
    for path in SRC.rglob("*.py"):
        if NLP in path.parents:
            continue
        for level, module in _imports(path):
            if "nlp" in module.split("."):
                offenders.append(str(path.relative_to(SRC)))
    assert not offenders, offenders


def test_nlp_is_standard_library_only():
    stdlib = set(__import__("sys").stdlib_module_names)
    for path in NLP.glob("*.py"):
        for level, module in _imports(path):
            if level == 0:
                assert module.split(".")[0] in stdlib, (path.name, module)


def test_lexicon_ships_in_the_package():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "lexicon.json" in cfg["tool"]["setuptools"]["package-data"]["thanzi_screen.ml.nlp"]
    assert (NLP / "lexicon.json").is_file() and (NLP / "__init__.py").is_file()
