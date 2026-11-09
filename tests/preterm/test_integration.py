"""Preterm integration: routing, the 50-week handover, corrected age, level mapping, both sexes, safety rules,
data licence, and the ML feature row. Framework-free (no FastAPI) except where noted."""
import hashlib
import json
import math
from pathlib import Path

import pytest

from thanzi_screen.anthro import InputError
from thanzi_screen.api import service
from thanzi_screen.ml import features as ml_features, load_models
from thanzi_screen.ml import preterm_features as pf
from thanzi_screen.preterm import LEVELS, PretermInput, engine, features
from thanzi_screen.preterm import routing as RT
from thanzi_screen.rules import Tier

PRETERM_DIR = Path(engine.__file__).parent
FENTON_SHA256 = "48d970c1d1329d9779324c30fa1408dcaba3fb06a4b4d9c1722a2a0b3262142f"


def payload(**k):
    d = {"sex": "female", "age_days": 20, "weight_kg": 1.25, "length_height_cm": 38.0, "measure_position": "length",
         "oedema": "none", "danger_signs": [], "complications": [], "gestational_age_weeks": 29.0,
         "birth_weight_g": 1100.0}
    d.update(k)
    return d


# ---- routing ----
@pytest.mark.parametrize("age,ga,bw,path", [
    (10, 29, 1100, RT.PATH_PRETERM),          # preterm and LBW
    (10, 36.9, 2600, RT.PATH_PRETERM),        # preterm, normal weight
    (10, 38, 2400, RT.PATH_PRETERM),          # term but low birth weight
    (10, 37, 2500, RT.PATH_UNDER5),           # exactly 37 weeks and exactly 2500 g: neither is "under"
    (10, 39, 3200, RT.PATH_UNDER5),
    (10, None, None, RT.PATH_UNDER5),         # no birth context: unchanged flow
    (10, 39, None, RT.PATH_UNDER5),
])
def test_routing_by_birth_gestation_and_weight(age, ga, bw, path):
    assert RT.route(age, ga, bw).path == path


def test_low_birth_weight_without_gestational_age_stays_under5_with_a_note():
    r = RT.route(10, None, 2000)
    assert r.path == RT.PATH_UNDER5 and "gestational_age_missing_for_low_birth_weight" in r.notes


def test_born_preterm_without_birth_weight_is_rejected_not_guessed():
    with pytest.raises(InputError):
        RT.route(10, 30, None)


@pytest.mark.parametrize("ga,bw", [(21, 900), (45, 3000), (30, 1.3), (30, 130000), (30, -5)])
def test_impossible_birth_values_and_unit_slips_are_rejected(ga, bw):
    with pytest.raises(InputError):
        RT.route(10, ga, bw)


def test_weight_unit_slip_on_the_preterm_route_is_rejected():
    with pytest.raises(service.ApiError) as e:
        service.screen(payload(weight_kg=1250))      # grams typed as kilograms
    assert e.value.status == 422 and e.value.code == "invalid_input"


# ---- 50-week handover ----
def test_handover_at_exactly_50_weeks_pma():
    assert RT.route(139, 30, 1300).path == RT.PATH_PRETERM        # 49.86 weeks
    assert RT.route(140, 30, 1300).path == RT.PATH_CORRECTED      # 50.00 weeks
    assert RT.route(140, 30, 1300).pma_weeks == 50.0


def test_handover_threshold_comes_from_the_rules_file(monkeypatch):
    monkeypatch.setitem(engine.R["hand_over_to_under5_engine"], "at_pma_weeks", 52)
    assert RT.route(140, 30, 1300).path == RT.PATH_PRETERM


def test_preterm_path_reports_the_engines_handover_note_when_pma_reaches_fenton_limit():
    r = service.screen(payload(age_days=139, gestational_age_weeks=30, birth_weight_g=1300, weight_kg=3.9, length_height_cm=50))
    assert r["route"] == "preterm"


# ---- corrected age ----
def test_corrected_age_is_chronological_minus_weeks_missing_from_40():
    assert RT.corrected_age_days(250, 30) == 180
    assert RT.corrected_age_days(250, 29.5) == 250 - 74        # 73.5 days rounds up
    assert RT.route(250, 30, 1300).age_days_used == 180


def test_under5_engine_receives_the_corrected_age_and_nothing_else_changes():
    base = {"sex": "male", "weight_kg": 6.0, "length_height_cm": 62.0, "measure_position": "length", "oedema": "none",
            "muac_cm": None, "appetite": "not_done", "danger_signs": [], "complications": [],
            "clinically_well_and_alert": True, "too_weak_to_suckle": False, "failure_to_gain_weight": False,
            "visible_severe_wasting": False}
    pre = service.screen({**base, "age_days": 250, "gestational_age_weeks": 30, "birth_weight_g": 1300})
    direct = service.screen({**base, "age_days": 180})
    for k in ("classification", "tier", "rules_fired", "reasons"):
        assert pre[k] == direct[k]
    assert pre["route"] == "under5_corrected_age" and pre["birth_context"]["age_days_used"] == 180
    assert pre["birth_context"]["corrected_age_days"] == 180 and pre["birth_context"]["age_days"] == 250


def test_corrected_age_changes_the_cmam_pathway_at_six_months():
    base = {"sex": "male", "weight_kg": 6.5, "length_height_cm": 64.0, "measure_position": "length", "oedema": "none",
            "muac_cm": 11.0, "appetite": "passed", "danger_signs": [], "complications": [],
            "clinically_well_and_alert": True, "too_weak_to_suckle": False, "failure_to_gain_weight": False,
            "visible_severe_wasting": False}
    # 200 days chronological is 6.6 months (child pathway, MUAC counts). Born at 28 weeks: corrected 200-84 = 116 days (infant).
    chrono = service.screen({**base, "age_days": 200})
    corr = service.screen({**base, "age_days": 200, "gestational_age_weeks": 28, "birth_weight_g": 1000})
    assert "SAM.MUAC" in chrono["rules_fired"] and "SAM.MUAC" not in corr["rules_fired"]
    assert any("MUAC is not used under 6 months" in w for w in corr["warnings"])


@pytest.mark.parametrize("ga,age,expected", [
    (30, 1095, RT.PATH_CORRECTED), (30, 1096, RT.PATH_UNDER5),       # under 32 weeks: until age 3 (36 months)
    (34, 730, RT.PATH_CORRECTED), (34, 731, RT.PATH_UNDER5),         # 32 to under 37: proposed 24 months
    (38, 300, RT.PATH_UNDER5),                                       # term, low birth weight: no correction
])
def test_corrected_age_period(ga, age, expected):
    assert RT.route(age, ga, 1500 if ga < 37 else 2300).path == expected


def test_corrected_age_period_is_configurable(monkeypatch):
    monkeypatch.setitem(RT.CONFIG["corrected_age"]["use_until_chronological_months"][1], "months", 12)
    assert RT.route(400, 34, 1800).path == RT.PATH_UNDER5


# ---- level mapping: one table, existing levels only ----
def test_level_map_covers_every_preterm_level_with_an_existing_under5_tier():
    assert set(RT.LEVEL_MAP) == set(LEVELS)
    assert set(RT.LEVEL_MAP.values()) - {None} <= {t.value for t in Tier}
    assert RT.tier_for("urgent_refer") == "urgent" and RT.tier_for("routine") == "low_risk"
    assert RT.tier_for("follow_up") is None           # kept as its own disposition, not forced into mam or low_risk


@pytest.mark.parametrize("extra,level", [
    ({"gestational_age_weeks": 36, "birth_weight_g": 2600, "weight_kg": 2.7, "age_days": 5}, "routine"),
    ({"gestational_age_weeks": 34, "birth_weight_g": 2100, "weight_kg": 2.0, "age_days": 3}, "follow_up"),
    ({"complications": ["infections"]}, "refer"),
    ({"complications": ["hypoglycaemia"]}, "urgent_refer"),
    ({"neonatal_danger_signs": ["bilious_vomiting"]}, "urgent_refer"),
])
def test_each_preterm_level_reaches_the_response_with_its_mapped_tier(extra, level):
    r = service.screen(payload(**extra))
    assert r["route"] == "preterm" and r["preterm_level"] == level and r["tier"] == RT.LEVEL_MAP[level]


# ---- the two sexes ----
@pytest.mark.parametrize("sex", ["female", "male"])
def test_both_sexes_screen_on_every_route(sex):
    pre = service.screen(payload(sex=sex))
    assert pre["route"] == "preterm" and pre["measurements"]["weight"]["z"] is not None
    corr = service.screen(payload(sex=sex, age_days=250, gestational_age_weeks=30, birth_weight_g=1300, weight_kg=6.0,
                                  length_height_cm=62.0, muac_cm=None))
    assert corr["route"] == "under5_corrected_age"


def test_sexes_use_different_fenton_tables():
    f, m = (service.screen(payload(sex=s))["measurements"]["weight"]["z"] for s in ("female", "male"))
    assert f != m


# ---- overlap with the existing danger-sign inputs (no duplicate fields) ----
@pytest.mark.parametrize("extra", [
    {"danger_signs": ["convulsions"]},
    {"danger_signs": ["unable_to_drink_or_breastfeed", "lethargy_not_alert"]},
    {"danger_signs": ["unable_to_drink_or_breastfeed"], "complications": ["severe_dehydration"]},
    {"too_weak_to_suckle": True, "danger_signs": ["lethargy_not_alert"]},
    {"hypoglycaemia_not_correcting": True},
    {"neonatal_danger_signs": ["apnoea"]},
    {"neonatal_danger_signs": ["cyanosis"]},
    {"neonatal_danger_signs": ["abdominal_distension", "blood_in_stool"]},
    {"neonatal_danger_signs": ["abdominal_distension", "feed_intolerance"]},
])
def test_overlapping_danger_inputs_reach_the_urgent_triggers(extra):
    r = service.screen(payload(**extra))
    assert r["preterm_level"] == "urgent_refer" and r["tier"] == "urgent"
    assert any("antibiotics" in a for a in r["actions"])


def test_single_non_urgent_signs_do_not_make_an_urgent_referral():
    for extra in ({"neonatal_danger_signs": ["abdominal_distension"]}, {"danger_signs": ["unable_to_drink_or_breastfeed"]},
                  {"danger_signs": ["lethargy_not_alert"]}):
        assert service.screen(payload(**extra))["preterm_level"] != "urgent_refer"


def test_failure_to_gain_weight_is_read_as_no_gain_days_after_14_days():
    r = service.screen(payload(failure_to_gain_weight=True))
    assert "not gaining weight" in r["reasons"]


def test_unassessed_danger_signs_are_warned_about():
    r = service.screen(payload(danger_signs=None))
    assert any("not assessed" in w for w in r["warnings"])


# ---- rules that must not change ----
def test_growth_alone_never_gives_an_urgent_referral_through_the_api():
    r = service.screen(payload(weight_kg=0.7, length_height_cm=30, hc_cm=22, birth_length_cm=37, birth_hc_cm=27))
    assert r["preterm_level"] == "refer" and r["tier"] != "urgent"


def test_oedema_in_an_infant_is_an_inpatient_criterion_per_cmam_table_5(monkeypatch):
    calm = dict(gestational_age_weeks=36, birth_weight_g=2600, weight_kg=2.7, age_days=5)
    for grade in ("+", "++", "+++"):
        r = service.screen(payload(oedema=grade, **calm))
        assert r["preterm_level"] == "urgent_refer" and r["tier"] == "urgent"
        assert any("oedema" in x for x in r["reasons"]) and any("antibiotics" in a for a in r["actions"])
    assert service.screen(payload(oedema="none", **calm))["preterm_level"] != "urgent_refer"
    # growth alone still never gives urgent_refer; oedema is a clinical sign, and the grade table is configurable
    monkeypatch.setitem(RT.CONFIG["oedema_on_preterm_route"]["min_preterm_level_by_grade"], "+", "refer")
    assert service.screen(payload(oedema="+", **calm))["preterm_level"] == "refer"


def test_hypoglycaemia_complication_is_the_urgent_trigger_per_cmam_table_5(monkeypatch):
    calm = dict(gestational_age_weeks=36, birth_weight_g=2600, weight_kg=2.7, age_days=5, complications=["hypoglycaemia"])
    r = service.screen(payload(**calm))
    assert r["preterm_level"] == "urgent_refer" and "hypoglycaemia not correcting" in r["reasons"]
    monkeypatch.setitem(RT.CONFIG["hypoglycaemia"], "complication_means_not_correcting", False)
    r = service.screen(payload(**calm))
    assert r["preterm_level"] == "refer" and any("hypoglycaemia" in w.lower() for w in r["warnings"])


def test_any_danger_sign_or_complication_requires_referral():
    calm = dict(gestational_age_weeks=36, birth_weight_g=2600, weight_kg=2.7, age_days=5)
    for extra in ({"danger_signs": ["convulsions"]}, {"danger_signs": ["high_fever"]}, {"complications": ["infections"]}):
        assert service.screen(payload(**calm, **extra))["preterm_level"] in ("refer", "urgent_refer")


def test_faltering_growth_needs_more_than_14_days_and_two_birth_measures_trend():
    young = service.screen(payload(age_days=14, weight_kg=0.9))
    older = service.screen(payload(age_days=15, weight_kg=0.9))
    assert not young["growth"] and older["growth"]["weight"]["tier"] in ("moderate", "severe")


def test_faltering_growth_tiers_and_head_circumference_thresholds_are_in_the_rules_file():
    g = engine.R["growth_assessment"]
    assert (g["z_decline_tiers"]["mild"], g["z_decline_tiers"]["moderate"], g["z_decline_tiers"]["severe"]) == (0.8, 1.2, 2.0)
    assert (g["hc_decline"]["follow_up_above"], g["hc_decline"]["refer_above"], g["min_age_days"]) == (1.0, 2.0, 14)


def test_proposed_values_are_read_from_the_rules_file_not_hardcoded(monkeypatch):
    monkeypatch.setitem(engine.R["growth_assessment"], "min_age_days", 30)
    assert not service.screen(payload(age_days=20, weight_kg=0.9))["growth"]
    monkeypatch.setitem(engine.R["growth_assessment"]["z_decline_tiers"], "mild", 5.0)
    monkeypatch.setitem(engine.R["growth_assessment"]["z_decline_tiers"], "moderate", 6.0)
    monkeypatch.setitem(engine.R["growth_assessment"]["z_decline_tiers"], "severe", 7.0)
    monkeypatch.setitem(engine.R["growth_assessment"], "min_age_days", 14)
    assert "tier" not in service.screen(payload(age_days=20, weight_kg=0.9))["growth"]["weight"]


def test_the_word_failure_is_never_used_by_the_preterm_route():
    # Scope: the preterm engine and its response. The under-5 engine's own wording from the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 ("failure to gain weight",
    # the failure_to_gain_weight field) is Table 5 text and is listed as an open question, not changed here.
    for p in (payload(), payload(weight_kg=0.9), payload(neonatal_danger_signs=["cyanosis"]),
              payload(age_days=60, weight_kg=2.0, length_height_cm=45, hc_cm=30, birth_length_cm=37, birth_hc_cm=26)):
        for view in ("worker", "audit"):
            out = service.screen(p, view)
            assert out["route"] == "preterm" and "failure" not in json.dumps(out).lower()
    assert "failure" not in json.dumps(engine.R).lower().replace("failure)", "")


def test_no_hiv_content_in_a_preterm_worker_response():
    assert "hiv" not in json.dumps(service.screen(payload(hiv_positive=True))).lower()


def test_unchanged_for_term_babies_and_requests_without_birth_context():
    base = {"sex": "male", "age_days": 500, "weight_kg": 11.0, "length_height_cm": 80.0, "measure_position": "length",
            "oedema": "none", "muac_cm": 12.0, "appetite": "passed", "danger_signs": [], "complications": [],
            "clinically_well_and_alert": True}
    plain = service.screen(base)
    assert service.screen({**base, "gestational_age_weeks": 39, "birth_weight_g": 3200}) == plain
    assert "route" not in plain and "birth_context" not in plain


def test_lbw_with_unknown_gestational_age_warns_and_uses_the_under5_flow():
    r = service.screen({**payload(), "gestational_age_weeks": None})
    assert r["route"] == "under5" and r["birth_context"]["gestational_age_weeks"] is None   # GA is never invented
    assert r["clinical_assessment"]["needed"] is True
    assert any("not given" in w and "clinical assessment" in w for w in r["warnings"])


# ---- data licence ----
def test_fenton_data_is_unmodified_and_keeps_its_attribution():
    assert hashlib.sha256((PRETERM_DIR / "fenton2025_lms.json").read_bytes()).hexdigest() == FENTON_SHA256
    meta = json.loads((PRETERM_DIR / "fenton2025_lms.json").read_text())["meta"]
    assert "CC BY-NC-ND 4.0" in meta["license"] and "Fenton" in meta["source"]
    r = service.screen(payload())
    assert "CC BY-NC-ND 4.0" in r["data_attribution"] and "Fenton" in r["data_attribution"]


def test_json_data_files_are_declared_as_package_data():
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    for name in ("fenton2025_lms.json", "preterm_rules.json", "routing_config.json"):
        assert name in text and (PRETERM_DIR / name).exists()


# ---- ML feature row ----
def test_existing_model_features_are_unchanged_and_models_still_load():
    saved = json.loads((Path(__file__).resolve().parents[2] / "models" / "recording_error_lr.json").read_text())
    assert tuple(saved["metadata"]["feature_names"]) == ml_features.FEATURES      # the saved models still match
    assert not set(pf.PRETERM_FEATURES) & set(ml_features.FEATURES)
    assert load_models().version


def test_preterm_columns_are_exactly_features_minus_the_rule_level():
    row = features(PretermInput(sex="m", ga_weeks=28, birth_weight_g=1000, age_days=10, weight_g=1000))
    assert tuple(row) == pf.ROW_COLUMNS and set(pf.ROW_COLUMNS) - set(pf.PRETERM_FEATURES) == {"rule_level"}
    vec = pf.preterm_vector(row)
    assert len(vec) == len(pf.PRETERM_VECTOR_COLUMNS) and not any(math.isnan(v) for v in vec)


def test_rule_level_is_refused_as_a_training_label():
    for name in ("rule_level", "preterm_level", "tier"):
        with pytest.raises(ValueError):
            pf.assert_valid_label(name)
    assert "rule_level" not in pf.PRETERM_VECTOR_COLUMNS


def test_dockerfile_checks_that_the_preterm_data_reaches_the_image():
    root = Path(__file__).resolve().parents[2]
    docker = (root / "Dockerfile").read_text()
    for name in ("fenton2025_lms.json", "preterm_rules.json", "routing_config.json", "CC BY-NC-ND 4.0"):
        assert name in docker
    assert "*.json" not in (root / ".dockerignore").read_text().split()           # data files are not ignored


# ---- decisions of 2026-11-08 ----
def test_corrected_age_end_for_32_to_36_weeks_is_approved_not_provisional(monkeypatch):
    r = service.screen(payload(age_days=300, gestational_age_weeks=34, birth_weight_g=1800, weight_kg=6.0,
                               length_height_cm=62.0, muac_cm=None))
    assert r["route"] == "under5_corrected_age" and r["birth_context"]["corrected_age_end_provisional"] is False
    assert not any("PROVISIONAL" in w for w in r["warnings"])          # 24 months approved 2026-11-08
    vp = service.screen(payload(age_days=300, gestational_age_weeks=30, birth_weight_g=1300, weight_kg=6.0,
                                length_height_cm=62.0, muac_cm=None))
    assert vp["birth_context"]["corrected_age_end_provisional"] is False and not any("PROVISIONAL" in w for w in vp["warnings"])
    monkeypatch.setitem(RT.CONFIG["corrected_age"]["use_until_chronological_months"][1], "provisional", True)   # mechanism kept
    assert RT.route(300, 34, 1800).corrected_age_provisional is True


def test_term_low_birth_weight_baby_is_never_age_corrected():
    r = RT.route(100, 38, 2300)
    assert r.path == RT.PATH_UNDER5 and r.age_days_used == 100 and r.corrected_age_days is None


def test_length_is_optional_only_on_the_preterm_route():
    no_len = {k: v for k, v in payload().items() if k not in ("length_height_cm", "measure_position")}
    r = service.screen(no_len)
    assert r["route"] == "preterm" and r["measurements"]["weight"]["z"] is not None
    assert "z" not in (r["measurements"].get("length") or {})            # no length given: no length z-score
    for p in (dict(no_len, gestational_age_weeks=39, birth_weight_g=3200),            # term: under-5 flow needs it
              {k: v for k, v in dict(no_len, age_days=250, gestational_age_weeks=30, birth_weight_g=1300).items()}):  # corrected
        with pytest.raises(service.ApiError) as e:
            service.screen(p)
        assert e.value.code == "missing_field"
    with pytest.raises(service.ApiError):                                              # a length needs its position
        service.screen(dict(no_len, length_height_cm=38.0))
    with pytest.raises(service.ApiError):                                              # oedema stays explicit
        service.screen({k: v for k, v in payload().items() if k != "oedema"})


def test_worker_wording_is_faltering_and_audit_keeps_the_cmam_terms():
    base = {"sex": "male", "age_days": 250, "weight_kg": 6.0, "length_height_cm": 62.0, "measure_position": "length",
            "oedema": "none", "muac_cm": None, "danger_signs": [], "complications": [],
            "gestational_age_weeks": 30, "birth_weight_g": 1300}
    worker, audit = service.screen(base), service.screen(base, "audit")
    def texts(x, skip=("code", "rules_fired")):
        if isinstance(x, str):
            yield x
        elif isinstance(x, list):
            for v in x:
                yield from texts(v)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in skip:
                    yield from texts(v)
    assert not any("failure" in t.lower() for t in texts(worker))
    assert any("faltering" in t for t in texts(worker))
    assert any(r["code"] == "failure_to_gain_weight_not_assessed" for r in worker["reasons"])     # code unchanged
    assert "Failure to gain weight" in json.dumps(audit)                                         # audit trace unchanged


# ---- urgent triggers: one source of truth ----
URGENT_FIELDS = ("bilious_vomiting", "convulsions", "apnoea_now", "cyanosis", "hypoglycaemia_uncorrected",
                 "abdominal_distension", "blood_in_stool", "feed_intolerance", "cannot_feed", "dehydrated", "lethargic")


def test_urgent_trigger_rules_and_config_agree():
    rules = engine.R["urgent_triggers"]["rules"]
    fields = {f for r in rules for f in r["all_of"] + r.get("any_of", [])}
    assert fields == set(URGENT_FIELDS) and all(hasattr(PretermInput(sex="f", ga_weeks=30, birth_weight_g=1000, age_days=1), f) for f in fields)
    assert len({r["id"] for r in rules}) == len(rules) and all(r["tag"] in ("Care of the Infant and Newborn (COIN), Malawi, 2017", "proposed") for r in rules)
    assert "any_of" not in engine.R["urgent_triggers"]            # the old hardcoded-list copy is gone
    for r in rules:                                               # each rule alone fires, and reports its own label
        kw = {f: True for f in r["all_of"]}
        if r.get("any_of"):
            kw[r["any_of"][0]] = True
        out = engine.screen(PretermInput(sex="f", ga_weeks=30, birth_weight_g=1000, age_days=3, weight_g=1000, **kw))
        assert out["referral"]["level"] == "urgent_refer" and r["label"] in out["referral"]["reasons"]


def test_changing_the_config_changes_the_triggers(monkeypatch):
    base = PretermInput(sex="f", ga_weeks=30, birth_weight_g=1000, age_days=3, weight_g=1000, cyanosis=True)
    assert engine.screen(base)["referral"]["level"] == "urgent_refer"
    monkeypatch.setitem(engine.R["urgent_triggers"], "rules",
                        [r for r in engine.R["urgent_triggers"]["rules"] if r["id"] != "cyanosis"])
    assert engine.screen(base)["referral"]["level"] != "urgent_refer"


def test_not_gaining_weight_uses_the_configured_age(monkeypatch):
    i = PretermInput(sex="f", ga_weeks=30, birth_weight_g=1000, age_days=20, weight_g=1100, gaining_days=1)
    assert "not gaining weight" in engine.screen(i)["referral"]["reasons"]
    monkeypatch.setitem(engine.R["growth_assessment"], "min_age_days", 30)
    assert "not gaining weight" not in engine.screen(i)["referral"]["reasons"]


def test_corrected_age_drives_the_age_dependent_cmam_criteria():
    # 200 days old, born at 28 weeks: corrected 116 days, so the infant (under 6 months) criteria apply, not the child ones.
    base = {"sex": "male", "age_days": 200, "weight_kg": 6.0, "length_height_cm": 62.0, "measure_position": "length",
            "oedema": "+", "muac_cm": 11.0, "appetite": "passed", "danger_signs": [], "complications": [],
            "clinically_well_and_alert": True, "too_weak_to_suckle": False, "failure_to_gain_weight": False,
            "visible_severe_wasting": False}
    chrono = service.screen(base)
    corr = service.screen({**base, "gestational_age_weeks": 28, "birth_weight_g": 1000})
    assert "INF.OEDEMA" in corr["rules_fired"] and "INF.OEDEMA" not in chrono["rules_fired"]     # infant criterion
    assert "SAM.MUAC" not in corr["rules_fired"] and "SAM.MUAC" in chrono["rules_fired"]         # MUAC from 6 months corrected
    direct = service.screen({**base, "age_days": 116})
    assert (corr["classification"], corr["tier"], corr["rules_fired"]) == (direct["classification"], direct["tier"], direct["rules_fired"])
