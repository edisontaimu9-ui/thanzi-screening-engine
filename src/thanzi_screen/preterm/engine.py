"""Preterm nutrition screening & referral engine.
Data: Fenton 2025 (CC BY-NC-ND 4.0, unmodified). Rules: COIN 2017 (Malawi) + Fenton guidance."""
from __future__ import annotations
import bisect, json, math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DIR = Path(__file__).parent
LMS = json.loads((_DIR / "fenton2025_lms.json").read_text())
R = json.loads((_DIR / "preterm_rules.json").read_text())
SEX = {"f": "girls", "female": "girls", "girl": "girls", "girls": "girls",
       "m": "boys", "male": "boys", "boy": "boys", "boys": "boys"}
LEVELS = ["routine", "follow_up", "refer", "urgent_refer"]


def z_score(x: float, L: float, M: float, S: float) -> float:
    return math.log(x / M) / S if abs(L) < 1e-9 else ((x / M) ** L - 1) / (L * S)


def percentile(z: float) -> float:
    return 100 * 0.5 * (1 + math.erf(z / math.sqrt(2)))


@lru_cache(maxsize=None)
def _table(sex: str, measure: str):
    rows = LMS["daily"][SEX[sex.lower()]][measure]
    return [r[0] for r in rows], rows


def lms_at(sex: str, measure: str, pma: float):
    """Linear interpolation on the daily table; None if outside Fenton range."""
    ages, rows = _table(sex, measure)
    if pma < ages[0] or pma > ages[-1]:
        return None
    i = max(1, bisect.bisect_left(ages, pma))
    a, b = rows[i - 1], rows[i]
    f = (pma - a[0]) / ((b[0] - a[0]) or 1)
    return tuple(a[k] + f * (b[k] - a[k]) for k in (1, 2, 3))


def z_for(sex: str, measure: str, pma: float, value: float) -> Optional[dict]:
    l = lms_at(sex, measure, pma)
    if l is None:
        return None
    zv = z_score(value, *l)
    return {"z": round(zv, 2), "percentile": round(percentile(zv), 1)}


@dataclass
class PretermInput:
    sex: str
    ga_weeks: float                  # gestational age at birth, decimal weeks
    birth_weight_g: float
    age_days: int                    # chronological age
    weight_g: Optional[float] = None
    length_cm: Optional[float] = None
    hc_cm: Optional[float] = None
    sick: bool = False
    cannot_feed: bool = False
    apnoea_7d: bool = False
    temp_unstable: bool = False
    gaining_days: Optional[int] = None   # consecutive days of weight gain
    aspirate_pct: Optional[float] = None
    birth_length_cm: Optional[float] = None
    birth_hc_cm: Optional[float] = None
    # danger signs (urgent triggers)
    bilious_vomiting: bool = False
    convulsions: bool = False
    apnoea_now: bool = False
    cyanosis: bool = False
    hypoglycaemia_uncorrected: bool = False
    abdominal_distension: bool = False
    blood_in_stool: bool = False
    feed_intolerance: bool = False
    dehydrated: bool = False
    lethargic: bool = False


def birth_class(bw: float) -> str:
    for c in R["birth_weight_class"]:
        if bw < c["max_g_exclusive"]:
            return c["id"]
    return "NORMAL"


def kmc_category(g: float) -> str:
    k = R["kmc"]
    return ("facility" if g < k["facility_below_g"] else "ambulatory" if g <= k["ambulatory_g"][1]
            else "community_continuous" if g <= k["continuous_at_or_below_g"] else "community")


def feed_plan(bw: float, ga: float, age_days: int, weight_g: float) -> dict:
    f = R["fluid_ml_per_kg_day"]
    hours = 2 if (bw < 1500 or ga < 32) else 3
    if age_days <= 1: mlkg = f["1"]
    elif age_days == 2: mlkg = f["2"]
    elif age_days == 3: mlkg = f["3"]
    elif age_days < 7: mlkg = f["4"]
    else: mlkg = f["7_lbw_sga"] if bw < 2500 else f["4"]
    band = "A" if (bw < 1500 or ga < 32) else "B" if (bw <= 1800 or ga <= 34) else "C"
    early = age_days <= 3
    route = {"A": "tube" if early else "tube_or_cup",
             "B": "tube_or_cup" if early else "breast_else_cup",
             "C": "breast_else_cup" if early else "breast"}[band]
    total = mlkg * weight_g / 1000
    return {"feed_every_hours": hours, "ml_per_kg_day": mlkg, "total_ml_day": round(total),
            "ml_per_feed": round(total / (24 / hours)), "route": route,
            "express_and_put_to_breast": bw > 1500 and ga >= 32}


def screen(i: PretermInput) -> dict:
    ga_cfg, rep = R["growth_assessment"], []
    pma = i.ga_weeks + i.age_days / 7
    w = i.weight_g if i.weight_g is not None else i.birth_weight_g
    out = {"pma_weeks": round(pma, 2), "classification": {"birth_weight": birth_class(i.birth_weight_g)},
           "measurements": {}}
    bz = z_for(i.sex, "weight", i.ga_weeks, i.birth_weight_g)
    if bz:
        c = R["birth_size_for_ga"]
        out["classification"]["birth_size"] = ("SGA" if bz["z"] < c["sga_below_z"]
                                               else "LGA" if bz["z"] > c["lga_above_z"] else "AGA")
        out["measurements"]["birth_weight"] = bz
    for val, m in ((i.weight_g, "weight"), (i.length_cm, "length"), (i.hc_cm, "hc")):
        if val is not None:
            out["measurements"][m] = z_for(i.sex, m, pma, val) or "outside_fenton_range"
    out["feeding"] = feed_plan(i.birth_weight_g, i.ga_weeks, i.age_days, w)
    out["kmc"] = kmc_category(w)

    level, reasons, actions = 0, [], []
    def up(l, why=None, act=None):
        nonlocal level
        level = max(level, LEVELS.index(l))
        if why: reasons.append(why)
        if act: actions.append(act)

    if out["classification"]["birth_weight"] != "NORMAL":
        up("follow_up", act=f"Weekly review until {R['followup']['weekly_until_kg']} kg")
    if i.sick: up("refer", "sick LBW/preterm neonate: hospitalise")
    if i.cannot_feed: up("refer", "cannot feed from breast or cup")
    if i.gaining_days is not None and i.gaining_days < 3 and i.age_days > 14: up("refer", "not gaining weight")
    if i.apnoea_7d: up("refer", "apnoea in last 7 days")
    if i.temp_unstable: up("refer", "unstable temperature")
    if i.aspirate_pct is not None and i.aspirate_pct > R["tube_feed_aspirate_review_pct"]:
        up("refer", "gastric aspirate >25% of last feed")
    if w < R["home_management_min_g"]: up("follow_up", "<1800 g: not suitable for unsupervised home care")
    if out["kmc"] == "facility": up("follow_up", act="Facility KMC (<1500 g)")

    # growth trajectory vs birth z (never a single point); weight, length, head circumference
    t = ga_cfg["z_decline_tiers"]
    if i.age_days > ga_cfg["min_age_days"]:
        births = {"weight": bz, "length": z_for(i.sex, "length", i.ga_weeks, i.birth_length_cm) if i.birth_length_cm else None,
                  "hc": z_for(i.sex, "hc", i.ga_weeks, i.birth_hc_cm) if i.birth_hc_cm else None}
        growth, faltering = {}, []
        for m, b0 in births.items():
            cur = out["measurements"].get(m)
            if not b0 or not isinstance(cur, dict):
                continue
            decline = round(b0["z"] - cur["z"], 2)
            growth[m] = {"z_change": -decline}
            if m == "hc":
                tier = ("severe" if decline > ga_cfg["hc_decline"]["refer_above"]
                        else "flag" if decline > ga_cfg["hc_decline"]["follow_up_above"] else None)
            else:
                tier = ("severe" if decline >= t["severe"] else "moderate" if decline > t["moderate"]
                        else "mild" if decline >= t["mild"] else None)
            if tier:
                growth[m]["tier"] = tier
                faltering.append((m, tier, decline))
        if growth: out["growth"] = growth
        feeding_trouble = i.cannot_feed or (i.gaining_days is not None and i.gaining_days < 3)
        for m, tier, d in faltering:
            lvl = "refer" if tier in ("moderate", "severe") else "follow_up"
            up(lvl, f"{m} z fell {d} ({tier}): faltering growth - optimise nutrition, look for causes")
        if len(faltering) >= 2 or (faltering and feeding_trouble):
            up("refer", "faltering growth with another concern: refer for nutrition review")
    # urgent: danger signs only - growth alone is never urgent
    urgent = [lbl for ok, lbl in [
        (i.bilious_vomiting, "bilious vomiting"), (i.convulsions, "convulsions"),
        (i.apnoea_now, "apnoea now"), (i.cyanosis, "cyanosis"),
        (i.hypoglycaemia_uncorrected, "hypoglycaemia not correcting"),
        (i.abdominal_distension and (i.blood_in_stool or i.feed_intolerance), "abdominal distension with blood in stool/feed intolerance"),
        (i.cannot_feed and (i.dehydrated or i.lethargic), "cannot feed and dehydrated/lethargic")] if ok]
    if urgent:
        for why in urgent: up("urgent_refer", why)
        actions.extend(R["urgent_triggers"]["stabilise_before_transfer"])
    if pma >= ga_cfg["fenton_max_pma_weeks"]:
        out["handover"] = "Use corrected age with the under-5 (WHO) engine"
    s = R["supplements"]
    out["supplements"] = ([f"Iron {s['iron_mg_per_kg_day'][0]}-{s['iron_mg_per_kg_day'][1]} mg/kg/day "
                           f"({w/1000*2:.1f}-{w/1000*4:.1f} mg/day) if on full feeds"] if i.age_days >= 14 else []) + \
                          [f"Multivitamin {s['multivitamin_ml_day'][0]}-{s['multivitamin_ml_day'][1]} ml/day once on full feeds"]
    out["referral"] = {"level": LEVELS[level], "reasons": reasons, "actions": actions,
                       "note": "No single percentile diagnoses faltering growth (Fenton)."}
    return out


def features(i: PretermInput) -> dict:
    """Flat numeric feature row for ML pipelines (NaN where unavailable)."""
    r, nan = screen(i), float("nan")
    m = r["measurements"]
    g = lambda k, f: m[k][f] if isinstance(m.get(k), dict) else nan
    return {"pma_weeks": r["pma_weeks"], "ga_weeks": i.ga_weeks, "age_days": i.age_days,
            "birth_weight_g": i.birth_weight_g, "weight_g": i.weight_g if i.weight_g is not None else nan,
            "z_birth_weight": g("birth_weight", "z"), "z_weight": g("weight", "z"),
            "z_length": g("length", "z"), "z_hc": g("hc", "z"),
            "dz_weight": r.get("growth", {}).get("weight", {}).get("z_change", nan),
            "dz_length": r.get("growth", {}).get("length", {}).get("z_change", nan),
            "dz_hc": r.get("growth", {}).get("hc", {}).get("z_change", nan),
            "ml_per_kg_day": r["feeding"]["ml_per_kg_day"],
            "is_sga": float(r["classification"].get("birth_size") == "SGA"),
            "rule_level": float(LEVELS.index(r["referral"]["level"]))}
