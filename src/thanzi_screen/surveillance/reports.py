"""Aggregated surveillance reports: facility, district and national (Phase 10). Advisory, standard library only, stateless.

Input is counts per facility per month that the caller has already grouped, plus the list of org units (national, districts,
facilities) so reporting completeness can be shown. No child record, identifier or date of birth is accepted. Each level is
summed from the facility counts, so the levels always agree. District hotspot status comes from `hotspots.assess` (one rule,
one place). Small-cell suppression follows the hotspot rule and adds secondary suppression, so a hidden cell cannot be
recovered by subtracting the visible ones from a total. Thresholds are placeholders until the Ministry confirms them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .hotspots import CONFIG as HOTSPOT_CONFIG
from .hotspots import DISTRICT_RE, PERIOD_RE, Row, SurveillanceInputError, assess, wilson

CONFIG_PATH = Path(__file__).with_name("report_config.json")
CONFIG: dict = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
CONFIG_VERSION: str = CONFIG["version"]

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,49}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-.,()/&]{0,99}$")
NATIONAL, DISTRICT, FACILITY = "national", "district", "facility"
LEVELS = (NATIONAL, DISTRICT, FACILITY)
STATUS_ORDER = ("hotspot", "watch", "not_flagged", "insufficient_data", "no_data")
ADVISORY = ("These figures describe children who were screened at the reporting facilities, not the whole population. "
            "Hotspot flags support planning and never change an individual child's classification or referral.")
LIMITS = [
    "Screening attendees are not a random sample. Prevalence among them is not population prevalence.",
    "Thresholds are placeholders, not Malawi figures. Confirm before use.",
    "A facility that did not report is not_reported. That is not zero cases and not low risk.",
    "Counts of 1 to 4 SAM or MAM are withheld, with secondary suppression so a hidden count cannot be worked out by subtraction.",
]


@dataclass(frozen=True)
class OrgUnit:
    code: str
    name: str
    level: str
    parent: str | None = None


@dataclass(frozen=True)
class FacilityRow:
    org_unit: str
    period: str
    screened: int
    sam: int
    mam: int
    unable: int = 0


@dataclass(frozen=True)
class Prepared:
    units: dict[str, OrgUnit]
    rows: list[FacilityRow]
    period: str


def _err(code: str, message: str) -> SurveillanceInputError:
    return SurveillanceInputError(code, message)


def prepare(org_units: list[OrgUnit], rows: list[FacilityRow], period: str | None = None) -> Prepared:
    """Validate the hierarchy and the rows and pick the report period. Messages never contain submitted values."""
    if not org_units:
        raise _err("no_org_units", "At least one org unit is needed.")
    if len(org_units) > CONFIG["max_org_units"]:
        raise _err("too_many_org_units", "Too many org units in one request.")
    if not rows:
        raise _err("no_rows", "At least one row is needed.")
    if len(rows) > CONFIG["max_rows"]:
        raise _err("too_many_rows", "Too many rows in one request.")
    if period is not None and not PERIOD_RE.match(period):
        raise _err("invalid_period", "A period must be YYYY-MM.")

    units: dict[str, OrgUnit] = {}
    seen_codes: set[str] = set()
    for u in org_units:
        if not CODE_RE.match(u.code):
            raise _err("invalid_org_unit_code", "An org unit code has an invalid format.")
        if u.level not in LEVELS:
            raise _err("invalid_level", "An org unit level must be national, district or facility.")
        if not (DISTRICT_RE.match(u.name) if u.level == DISTRICT else NAME_RE.match(u.name)) or not u.name.strip():
            raise _err("invalid_org_unit_name", "An org unit name has an invalid format.")
        if u.code.lower() in seen_codes:
            raise _err("duplicate_org_unit", "Each org unit code may appear once.")
        seen_codes.add(u.code.lower())
        units[u.code] = u
    nationals = [u for u in units.values() if u.level == NATIONAL]
    if len(nationals) != 1 or nationals[0].parent is not None:
        raise _err("invalid_hierarchy", "There must be exactly one national org unit and it has no parent.")
    want_parent = {DISTRICT: NATIONAL, FACILITY: DISTRICT}
    for u in units.values():
        if u.level != NATIONAL and (u.parent not in units or units[u.parent].level != want_parent[u.level]):
            raise _err("invalid_hierarchy", "Every district sits under the national unit and every facility under a district.")
    district_names = [u.name.strip().lower() for u in units.values() if u.level == DISTRICT]
    if len(district_names) != len(set(district_names)):
        raise _err("duplicate_district_name", "District names must be different from each other.")

    seen: set[tuple[str, str]] = set()
    for r in rows:
        if r.org_unit not in units:
            raise _err("unknown_org_unit", "A row names an org unit that is not in org_units.")
        if units[r.org_unit].level != FACILITY:
            raise _err("not_a_facility", "Rows are counts for facilities. Districts and the national total are summed from them.")
        if not PERIOD_RE.match(r.period):
            raise _err("invalid_period", "A period must be YYYY-MM.")
        if min(r.screened, r.sam, r.mam, r.unable) < 0 or r.screened > 10_000_000:
            raise _err("invalid_count", "Counts must be whole numbers from 0 to 10,000,000.")
        if r.sam + r.mam + r.unable > r.screened:
            raise _err("inconsistent_counts", "sam + mam + unable cannot exceed screened.")
        if (r.org_unit, r.period) in seen:
            raise _err("duplicate_row", "Each facility and period may appear once.")
        seen.add((r.org_unit, r.period))

    chosen = period or max(r.period for r in rows)
    if not any(r.period == chosen for r in rows):
        raise _err("no_rows_for_period", "No row is for the requested period.")
    return Prepared(units, [r for r in rows if r.period <= chosen], chosen)


# ---- one unit of the report ----
def _blank(u: OrgUnit) -> dict:
    return {"org_unit": u.code, "name": u.name.strip(), "level": u.level, "parent": u.parent, "data_status": "not_reported",
            "facilities_expected": None, "facilities_reported": None, "reporting_rate": None,
            "screened": None, "sam": None, "mam": None, "gam_cases": None, "unable": None,
            "prevalence": None, "ci_low": None, "ci_high": None,
            "hotspot_status": None, "trend": None, "reference_rate": None, "reference_kind": None,
            "data_quality_review": False, "counts_suppressed": False, "reasons": []}


def _fill(out: dict, screened: int, sam: int, mam: int, unable: int) -> None:
    cfg = HOTSPOT_CONFIG
    out.update(screened=screened, sam=sam, mam=mam, gam_cases=sam + mam, unable=unable)
    if screened < cfg["min_screened"]:
        out["data_status"] = "insufficient_data"          # counts stay, the rate is not shown: never read as low risk
        out["reasons"].append("fewer_than_min_screened")
        return
    out["data_status"] = "ok"
    lo, hi = wilson(sam + mam, screened, cfg["confidence_z"])
    out.update(prevalence=round((sam + mam) / screened, 4), ci_low=round(lo, 4), ci_high=round(hi, 4))
    if unable / screened >= cfg["unable_share_review"]:
        out["data_quality_review"] = True
        out["reasons"].append("high_share_unable_to_classify")


def _small(v: int | None) -> bool:
    return v is not None and 0 < v < HOTSPOT_CONFIG["suppress_cells_below"]


def _hidden(u: dict) -> bool:
    """Counts already withheld, or due to be withheld because SAM or MAM is 1 to 4."""
    return u["counts_suppressed"] or (u["data_status"] != "not_reported" and (_small(u["sam"]) or _small(u["mam"])))


def _suppress(u: dict, reason: str) -> None:
    if u["counts_suppressed"]:
        return
    for k in ("sam", "mam", "gam_cases", "prevalence", "ci_low", "ci_high"):
        u[k] = None
    u["counts_suppressed"] = True
    u["reasons"].append(reason)


def _protect(children: list[dict], parent: dict) -> None:
    """Small-cell suppression for one group of children under one parent, with secondary suppression.

    One hidden child under a shown parent could be recovered as parent minus visible siblings, so the smallest visible sibling
    with cases is hidden too. If no sibling has cases, the parent is hidden instead. Two or more hidden children cannot be
    separated by subtraction. Order matters: this runs bottom-up, facilities under districts, then districts under national.
    """
    reported = [c for c in children if c["data_status"] != "not_reported"]
    hidden = [c for c in reported if _hidden(c)]
    secondary: list[dict] = []
    hide_parent = False
    if len(hidden) == 1 and not _hidden(parent):
        visible = [c for c in reported if c is not hidden[0] and not _hidden(c) and (c["gam_cases"] or 0) > 0]
        if visible:
            secondary.append(min(visible, key=lambda c: (c["gam_cases"], c["org_unit"])))
        else:
            hide_parent = True
    for c in hidden:
        _suppress(c, "small_cell_suppressed")
    for c in secondary:
        _suppress(c, "secondary_suppression")
    if hide_parent:
        _suppress(parent, "secondary_suppression")


def build_report(org_units: list[OrgUnit], rows: list[FacilityRow], period: str | None = None,
                 reference_rate: float | None = None) -> dict:
    """The report for one month: every facility, every district (with hotspot status) and the national total. Pure function."""
    p = prepare(org_units, rows, period)
    units, chosen = p.units, p.period
    current = {r.org_unit: r for r in p.rows if r.period == chosen}

    facilities = {c: _blank(u) for c, u in units.items() if u.level == FACILITY}
    for code, out in facilities.items():
        r = current.get(code)
        if r is not None:
            _fill(out, r.screened, r.sam, r.mam, r.unable)

    districts: dict[str, dict] = {}
    for dcode, du in units.items():
        if du.level != DISTRICT:
            continue
        out = _blank(du)
        kids = [c for c, f in facilities.items() if f["parent"] == dcode]
        got = [current[c] for c in kids if c in current]
        out.update(facilities_expected=len(kids), facilities_reported=len(got),
                   reporting_rate=round(len(got) / len(kids), 4) if kids else None)
        if got:
            _fill(out, sum(r.screened for r in got), sum(r.sam for r in got), sum(r.mam for r in got), sum(r.unable for r in got))
        else:
            out["reasons"].append("no_facility_reported")
        districts[dcode] = out

    nat_unit = next(u for u in units.values() if u.level == NATIONAL)
    national = _blank(nat_unit)
    all_got = list(current.values())
    national.update(facilities_expected=len(facilities), facilities_reported=len(all_got),
                    reporting_rate=round(len(all_got) / len(facilities), 4) if facilities else None)
    if all_got:
        _fill(national, sum(r.screened for r in all_got), sum(r.sam for r in all_got), sum(r.mam for r in all_got),
              sum(r.unable for r in all_got))

    # Hotspot status per district: the one rule in hotspots.assess, on district sums for every month up to the report month.
    by_district_period: dict[tuple[str, str], list[int]] = {}
    for r in p.rows:
        name = units[units[r.org_unit].parent].name.strip()
        t = by_district_period.setdefault((name, r.period), [0, 0, 0, 0])
        for i, v in enumerate((r.screened, r.sam, r.mam, r.unable)):
            t[i] += v
    verdict = {a["district"]: a for a in assess([Row(n, per, *t) for (n, per), t in by_district_period.items()],
                                                reference_rate)["areas"]}
    for out in districts.values():
        a = verdict.get(out["name"])
        if a is None:
            out["hotspot_status"] = "no_data"
            continue
        out.update(hotspot_status=a["status"], trend=a["trend"], reference_rate=a["reference_rate"],
                   reference_kind=a["reference_kind"])
        out["data_quality_review"] = out["data_quality_review"] or a["data_quality_review"]
        if a["status"] in ("hotspot", "watch"):
            out["reasons"] += [x for x in a["reasons"] if x not in out["reasons"] and x != "small_cell_suppressed"]

    # Small-cell suppression, bottom-up. The statuses above were computed first and reveal only a threshold, never a count.
    for dcode, d in districts.items():
        _protect([f for f in facilities.values() if f["parent"] == dcode], d)
        if _hidden(d):
            _suppress(d, "small_cell_suppressed")
    _protect(list(districts.values()), national)
    if _hidden(national):
        _suppress(national, "small_cell_suppressed")

    order = {s: i for i, s in enumerate(STATUS_ORDER)}
    district_list = sorted(districts.values(), key=lambda d: (order[d["hotspot_status"]], d["name"].lower()))
    name_of = {c: u.name.strip().lower() for c, u in units.items()}
    facility_list = sorted(facilities.values(), key=lambda f: (name_of[f["parent"]], f["name"].lower(), f["org_unit"]))
    summary = {s: sum(1 for d in district_list if d["hotspot_status"] == s) for s in STATUS_ORDER}
    return {"period": chosen, "report_version": CONFIG_VERSION, "config_version": HOTSPOT_CONFIG["version"],
            "national": national, "districts": district_list, "facilities": facility_list,
            "summary": {"districts": summary, "facilities_expected": national["facilities_expected"],
                        "facilities_reported": national["facilities_reported"], "reporting_rate": national["reporting_rate"]},
            "min_screened": HOTSPOT_CONFIG["min_screened"], "advisory": ADVISORY, "limits": LIMITS}
