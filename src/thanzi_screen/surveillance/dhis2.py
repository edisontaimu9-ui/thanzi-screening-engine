"""DHIS2 export of facility counts (Phase 10). Standard library only, stateless.

Builds a `dataValueSets` payload (POST /api/dataValueSets) from the same facility counts as the report. Only the facility
level is exported: DHIS2 rolls facilities up to districts and the national level itself, so exporting district totals as well
would count every child twice. Rates are not exported: define them in DHIS2 as indicators (numerator SAM + MAM, denominator
screened). The mapping (which DHIS2 data element and org unit each count goes to) is supplied by the caller and is never guessed.
A count that is not mapped stops the export. Nothing here talks to DHIS2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hotspots import CONFIG as HOTSPOT_CONFIG
from .hotspots import SurveillanceInputError
from .reports import CODE_RE, CONFIG, CONFIG_VERSION, FacilityRow, OrgUnit, prepare

UID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{10}$")
SCHEMES = ("CODE", "UID")
# What the engine exports, and what each element should be in DHIS2 (integer, zero or positive, summed up the hierarchy).
ELEMENTS: dict[str, dict] = {
    "screened": {"required": True, "name": "Under-5 children screened",
                 "description": "Children under five screened for acute malnutrition in the month."},
    "sam": {"required": True, "name": "Under-5 screened classified SAM",
            "description": "Of those screened, classified SAM (SAM_OTP, SAM_INPATIENT or SAM_ASSESS)."},
    "mam": {"required": True, "name": "Under-5 screened classified MAM",
            "description": "Of those screened, classified MAM."},
    "unable": {"required": False, "name": "Under-5 screened, unable to classify",
               "description": "Of those screened, UNABLE_TO_CLASSIFY. Used for a data-quality indicator."},
}
ADVISORY = ("Counts for loading into DHIS2. Run the import with dryRun=true first and check the summary. "
            "Screening counts describe children who were screened, not the whole population.")


@dataclass(frozen=True)
class Dhis2Mapping:
    elements: dict[str, str]
    data_set: str | None = None
    data_element_id_scheme: str = "CODE"
    org_unit_id_scheme: str = "CODE"
    org_units: dict[str, str] = field(default_factory=dict)


def _err(code: str, message: str) -> SurveillanceInputError:
    return SurveillanceInputError(code, message)


def _id_ok(value: str, scheme: str) -> bool:
    return bool((UID_RE if scheme == "UID" else CODE_RE).match(value))


def validate_mapping(m: Dhis2Mapping) -> None:
    for s in (m.data_element_id_scheme, m.org_unit_id_scheme):
        if s not in SCHEMES:
            raise _err("invalid_mapping", "An id scheme must be CODE or UID.")
    if set(m.elements) - set(ELEMENTS):
        raise _err("invalid_mapping", "The mapping names a count the engine does not export.")
    if any(k not in m.elements for k, v in ELEMENTS.items() if v["required"]):
        raise _err("mapping_incomplete", "The mapping must give a data element for screened, sam and mam.")
    if any(not _id_ok(v, m.data_element_id_scheme) for v in m.elements.values()):
        raise _err("invalid_mapping", "A data element id does not fit the chosen id scheme.")
    if len(set(m.elements.values())) != len(m.elements):
        raise _err("invalid_mapping", "Two counts cannot share one data element.")
    if m.data_set is not None and not _id_ok(m.data_set, m.data_element_id_scheme):
        raise _err("invalid_mapping", "The data set id does not fit the chosen id scheme.")
    if len(m.org_units) > CONFIG["max_org_units"]:
        raise _err("invalid_mapping", "Too many org unit mappings.")
    if any(not CODE_RE.match(k) or not _id_ok(v, m.org_unit_id_scheme) for k, v in m.org_units.items()):
        raise _err("invalid_mapping", "An org unit mapping has an invalid format.")


def _target(code: str, m: Dhis2Mapping) -> str:
    """The DHIS2 id of a facility. With the CODE scheme the engine code is used unless the mapping overrides it."""
    if code in m.org_units:
        return m.org_units[code]
    if m.org_unit_id_scheme == "UID":
        raise _err("mapping_incomplete", "Every exported facility needs an org unit mapping when the scheme is UID.")
    return code


def build_data_value_set(org_units: list[OrgUnit], rows: list[FacilityRow], mapping: Dhis2Mapping,
                         period: str | None = None) -> dict:
    """The facility counts of one month as a DHIS2 data value set. Pure function."""
    p = prepare(org_units, rows, period)
    validate_mapping(mapping)
    cfg = HOTSPOT_CONFIG
    drop_small = CONFIG["dhis2_export_suppresses_small_cells"]
    values: list[dict] = []
    targets: set[str] = set()
    facilities = withheld = 0
    for r in sorted((r for r in p.rows if r.period == p.period), key=lambda r: r.org_unit):
        org = _target(r.org_unit, mapping)
        if org in targets:
            raise _err("invalid_mapping", "Two facilities map to the same DHIS2 org unit.")
        targets.add(org)
        small = any(0 < v < cfg["suppress_cells_below"] for v in (r.sam, r.mam))
        hide = drop_small and small
        counts = {"screened": r.screened, "sam": r.sam, "mam": r.mam, "unable": r.unable}
        for key, element in mapping.elements.items():
            if hide and key in ("sam", "mam"):
                continue
            values.append({"dataElement": element, "orgUnit": org, "value": str(counts[key])})
        facilities += 1
        withheld += 1 if hide else 0
    payload: dict = {"period": p.period.replace("-", ""), "dataValues": values}
    if mapping.data_set:
        payload = {"dataSet": mapping.data_set, **payload}
    return {
        "data_value_set": payload,
        "import_parameters": {"dataElementIdScheme": mapping.data_element_id_scheme,
                              "orgUnitIdScheme": mapping.org_unit_id_scheme, "importStrategy": "CREATE_AND_UPDATE",
                              "dryRun": "true"},
        "summary": {"period": p.period, "facilities_exported": facilities, "values": len(values),
                    "facilities_with_withheld_counts": withheld,
                    "facilities_not_reported": sum(1 for u in p.units.values() if u.level == "facility") - facilities,
                    "small_counts_withheld": bool(drop_small)},
        "report_version": CONFIG_VERSION, "advisory": ADVISORY,
    }


def mapping_template(org_units: list[OrgUnit] | None = None) -> dict:
    """A blank mapping for the DHIS2 administrators to fill in. Placeholders are not valid ids on purpose."""
    return {
        "_note": "Fill in the data element ids (CODE or UID) and set the id schemes. Leave org_units empty when the engine codes "
                 "are the DHIS2 org unit codes. Remove the keys that start with an underscore before use.",
        "data_set": None, "data_element_id_scheme": "CODE", "org_unit_id_scheme": "CODE",
        "elements": {k: f"<{k}-data-element>" for k in ELEMENTS},
        "org_units": {},
        "_elements_guide": {k: {"required": v["required"], "suggested_name": v["name"], "description": v["description"],
                                "value_type": "INTEGER_ZERO_OR_POSITIVE", "aggregation": "SUM"} for k, v in ELEMENTS.items()},
        "_indicators_to_define_in_dhis2": {"gam_prevalence": "numerator sam + mam, denominator screened",
                                           "unable_share": "numerator unable, denominator screened"},
    }
