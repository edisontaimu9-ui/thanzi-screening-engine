"""Classification trace (Phase 5). Describes how the Phase 2 result arose. Never changes it (D9).

Rules fired come straight from `ClassificationResult.rules_fired`. The criteria table shows the values
against the same cut-offs the rules use (constants imported from `rules_v2016`), so nothing is re-decided here.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..rules import rules_v2016 as R
from ..rules.classify import IMPLAUSIBLE
from ..rules.models import Appetite, OedemaGrade
from . import messages as M


@dataclass(frozen=True)
class RuleRef:
    id: str
    description: str
    source: str
    page: str
    tag: str          # DOCUMENTED, ASSUMPTION or RECOMMENDATION
    worker_text: str


@dataclass(frozen=True)
class Criterion:
    code: str
    label: str
    value: float | str | bool | None
    status: str                       # severe, moderate, normal, present, absent, not_assessed, not_used, below, ok
    cutoffs: tuple[float, ...]
    nearest_cutoff: float | None
    margin: float | None              # value minus nearest cut-off (positive = above)
    used: bool
    note: str | None
    text: str


@dataclass(frozen=True)
class ClassificationTrace:
    classification: str
    tier: str
    programme: str | None
    pathway: str                      # "infant" (<6 months) or "child"
    rules: tuple[RuleRef, ...]
    criteria: tuple[Criterion, ...]
    reasons: tuple[tuple[str, str], ...]   # (code, text)
    warnings: tuple[str, ...]
    referral_text: str
    rule_set_version: str
    audit_notes: tuple[str, ...] = ()      # audit-only notes (HIV wording lives here, Q7)


def nearest(value: float, cutoffs) -> tuple[float, float]:
    """Nearest cut-off and signed margin (value - cutoff)."""
    c = min(cutoffs, key=lambda k: abs(value - k))
    return c, round(value - c, 4)


def margin_text(label: str, unit: str, value: float, cutoff: float, margin: float, at_is: str) -> str:
    u = f" {unit}" if unit else ""
    if margin == 0:
        return f"{label} {value:g}{u} is exactly on the {cutoff:g}{u} cut-off ({at_is})."
    side = "above" if margin > 0 else "below"
    return f"{label} {value:g}{u} is {abs(margin):g}{u} {side} the {cutoff:g}{u} cut-off."


def _band_muac(m: float) -> str:
    return "severe" if m < R.MUAC_SEVERE_CM else ("moderate" if m < R.MUAC_MODERATE_CM else "normal")


def _band_z(z: float) -> str:
    return "severe" if z < R.WFLH_SEVERE_Z else ("moderate" if z < R.WFLH_MODERATE_Z else "normal")


def worker_text(rule_id: str, ctx: dict) -> str:
    """Fill a rule's worker text from the record. Unknown fields fall back to a neutral placeholder."""
    class _D(dict):
        def __missing__(self, k):
            return "?"
    return M.RULE_WORKER[rule_id].format_map(_D(ctx))


def context(anthro, clinical) -> dict:
    def z(ind):
        return f"{ind.z:.2f}" if ind.status == "ok" and ind.z is not None else "?"
    return {"muac": "?" if clinical.muac_cm is None else f"{clinical.muac_cm:g}", "wflh": z(anthro.wflh),
            "wfa": z(anthro.wfa), "weight": "?" if anthro.weight_kg is None else f"{anthro.weight_kg:g}",
            "oedema": clinical.oedema.value}


def _muac_criterion(clinical) -> Criterion:
    m = clinical.muac_cm
    cuts = (R.MUAC_SEVERE_CM, R.MUAC_MODERATE_CM)
    if m is None:
        return Criterion("muac", "MUAC", None, "not_assessed", cuts, None, None, False, "MUAC not entered.",
                         "MUAC was not entered.")
    c, mg = nearest(m, cuts)
    band = _band_muac(m)
    side = margin_text("MUAC", "cm", m, c, mg, "counts as the less severe side")
    return Criterion("muac", "MUAC", m, band, cuts, c, mg, True, None, f"{side} Band: {band}.")


def _z_criterion(code, label, ind, cuts, *, skip_note=None, band_fn=_band_z) -> Criterion:
    if skip_note:
        return Criterion(code, label, None if ind.status != "ok" else ind.z, "not_used", cuts, None, None, False,
                         skip_note, f"{label} was not used: {skip_note}")
    if ind.status != "ok" or ind.z is None:
        return Criterion(code, label, None, "not_assessed", cuts, None, None, False, "Could not be computed.",
                         f"{label} could not be computed.")
    if IMPLAUSIBLE in ind.flags:
        n = "Flagged implausible, so not used."
        return Criterion(code, label, ind.z, "not_used", cuts, None, None, False, n, f"{label} {ind.z:.2f}: {n}")
    c, mg = nearest(ind.z, cuts)
    band = band_fn(ind.z)
    side = margin_text(label, "", round(ind.z, 2), c, round(mg, 2), "counts as the less severe side")
    return Criterion(code, label, round(ind.z, 4), band, cuts, c, mg, True, None, f"{side} Band: {band}.")


def _flag_criterion(code, label, value) -> Criterion:
    if value is None:
        return Criterion(code, label, None, "not_assessed", (), None, None, False, "Not assessed.", f"{label}: not assessed.")
    s = "present" if value else "absent"
    return Criterion(code, label, bool(value), s, (), None, None, True, None, f"{label}: {s}.")


def _context_criteria(clinical) -> list[Criterion]:
    out = []
    ap = clinical.appetite
    out.append(Criterion("appetite", "Appetite test", ap.value,
                         "not_assessed" if ap == Appetite.NOT_DONE else ap.value, (), None, None,
                         ap != Appetite.NOT_DONE, None, f"Appetite test: {ap.value.replace('_', ' ')}."))
    ds, cp = clinical.danger_signs, clinical.complications
    out.append(Criterion("danger_signs", "Danger signs", None if ds is None else len(ds),
                         "not_assessed" if ds is None else ("present" if ds else "absent"), (), None, None,
                         ds is not None, None,
                         "Danger signs: not assessed." if ds is None else
                         ("Danger signs: present." if ds else "Danger signs: none.")))
    out.append(Criterion("complications", "Medical complications", None if cp is None else len(cp),
                         "not_assessed" if cp is None else ("present" if cp else "absent"), (), None, None,
                         cp is not None, None,
                         "Medical complications: not assessed." if cp is None else
                         ("Medical complications: present." if cp else "Medical complications: none.")))
    out.append(_flag_criterion("well_and_alert", "Clinically well and alert", clinical.clinically_well_and_alert))
    return out


def build_trace(anthro, clinical, result) -> ClassificationTrace:
    oedema = clinical.oedema != OedemaGrade.NONE
    infant = anthro.age_months < R.CHILD_PATHWAY_MIN_MONTHS
    crit: list[Criterion] = [Criterion("oedema", "Bilateral pitting oedema", clinical.oedema.value,
                                       "present" if oedema else "absent", (), None, None, True, None,
                                       f"Oedema: {clinical.oedema.value}." if oedema else "No oedema entered.")]
    if infant:
        length_ok = anthro.length_height_used_cm >= R.INFANT_WFL_MIN_LENGTH_CM
        skip = ("oedema was entered (D14)" if oedema else
                (None if length_ok else f"length is under {R.INFANT_WFL_MIN_LENGTH_CM:g} cm"))
        crit.append(_z_criterion("wflh_z", "Weight-for-length z", anthro.wflh, (R.WFLH_SEVERE_Z,), skip_note=skip,
                                 band_fn=lambda z: "severe" if z < R.WFLH_SEVERE_Z else "normal"))
        crit.append(_z_criterion("wfa_z", "Weight-for-age z", anthro.wfa, (R.INFANT_WFA_REFER_Z,),
                                 band_fn=lambda z: "severe" if z < R.INFANT_WFA_REFER_Z else "normal"))
        crit.append(_flag_criterion("visible_severe_wasting", "Visible severe wasting", clinical.visible_severe_wasting))
        crit.append(_flag_criterion("too_weak_to_suckle", "Too weak to suckle", clinical.too_weak_to_suckle))
        crit.append(_flag_criterion("failure_to_gain_weight", "Failure to gain weight", clinical.failure_to_gain_weight))
    else:
        crit.append(_muac_criterion(clinical))
        crit.append(_z_criterion("wflh_z", "Weight-for-length/height z", anthro.wflh,
                                 (R.WFLH_SEVERE_Z, R.WFLH_MODERATE_Z),
                                 skip_note="oedema was entered (D14)" if oedema else None))
        w = anthro.weight_kg
        if w is not None:
            below = w < R.INFANT_WEIGHT_NRU_KG
            crit.append(Criterion("weight_kg", "Weight", w, "below" if below else "ok", (R.INFANT_WEIGHT_NRU_KG,),
                                  R.INFANT_WEIGHT_NRU_KG, round(w - R.INFANT_WEIGHT_NRU_KG, 4), True, None,
                                  f"Weight {w:g} kg is {'below' if below else 'not below'} the "
                                  f"{R.INFANT_WEIGHT_NRU_KG:g} kg limit at 6 months or older."))
    crit += _context_criteria(clinical)

    ctx = context(anthro, clinical)
    rules = tuple(RuleRef(r.id, r.description, r.source, r.page, r.tag, worker_text(r.id, ctx))
                  for r in (R.RULES[i] for i in result.rules_fired))
    reasons = tuple((c, M.REASON_TEXT.get(c, c)) for c in result.reasons)
    notes: list[str] = []
    if "MAM.HIV_OTP" in result.rules_fired:
        notes.append("The optional HIV-positive input was used: rule MAM.HIV_OTP admits to OTP when appetite passed, "
                     "no complications and well and alert (CMAM 2016 Table 5 p.17).")
    elif clinical.hiv_positive and result.classification.value == "MAM":
        notes.append("The optional HIV-positive input was entered. OTP admission conditions were not all confirmed.")
    return ClassificationTrace(
        classification=result.classification.value, tier=result.tier.value, programme=result.programme,
        pathway="infant" if infant else "child", rules=rules, criteria=tuple(crit), reasons=reasons,
        warnings=tuple(result.warnings), referral_text=result.referral_text,
        rule_set_version=result.rule_set_version, audit_notes=tuple(notes))
