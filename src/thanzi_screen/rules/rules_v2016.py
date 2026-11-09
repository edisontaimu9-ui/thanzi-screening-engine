"""Rule registry for Malawi CMAM 2016 (2nd Ed.). Page numbers are printed page numbers."""
from __future__ import annotations

from dataclasses import dataclass

RULE_SET_VERSION = "rules_v2016"
DISCLAIMER = "Decision support only. Not a diagnosis. A trained clinician makes the final decision."
PLACEHOLDER = "[PLACEHOLDER: official referral wording pending extraction from CMAM 2016.] "

# Thresholds (R3 Table 4 p.14, Table 5 pp.16-17; D5)
MUAC_SEVERE_CM = 11.5
MUAC_MODERATE_CM = 12.5
WFLH_SEVERE_Z = -3.0
WFLH_MODERATE_Z = -2.0   # ASSUMPTION A1: z = -2.00 is not moderate (WHO convention, z < -2)
INFANT_WFL_MIN_LENGTH_CM = 45.0
INFANT_WFA_REFER_Z = -3.0
INFANT_WEIGHT_NRU_KG = 3.0  # Table 5 p.16: infant >6 months weighing <3.0 kg (I7, D29)
CHILD_PATHWAY_MIN_MONTHS = 6.0  # D-Q5: exactly 6 months is the child pathway

DOCUMENTED, ASSUMPTION, RECOMMENDATION = "DOCUMENTED", "ASSUMPTION", "RECOMMENDATION"


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    source: str
    page: str
    tag: str


def _r(id, description, page, tag=DOCUMENTED, source="R3"):
    return id, Rule(id, description, source, page, tag)


RULES: dict[str, Rule] = dict([
    _r("SAM.MUAC", "MUAC <11.5 cm (6-59 months): severe", "Table 4 p.14; Table 5 p.16"),
    _r("SAM.WFLH", "WFL/H z <-3: severe", "Table 5 pp.16-17"),
    _r("SAM.OEDEMA", "Bilateral pitting oedema (any grade) qualifies as SAM", "Table 5 pp.16-17"),
    _r("MAM.MUAC", "MUAC 11.5 to <12.5 cm: moderate", "Table 5 p.17"),
    _r("MAM.WFLH", "WFL/H z -3 to -2: moderate (-2.00 itself is not moderate: WHO convention z < -2)", "Table 5 p.17", ASSUMPTION),
    _r("NRU.OEDEMA3", "Oedema +++: inpatient", "Table 5 p.16"),
    _r("NRU.MARASMIC_KWASHIORKOR", "Any oedema with severe wasting: inpatient", "Table 5 p.16"),
    _r("NRU.DANGER_SIGNS", "Oedema +/++ or severe wasting with a danger sign: inpatient", "Table 5 p.16"),
    _r("NRU.COMPLICATIONS", "Oedema +/++ or severe wasting with a medical complication: inpatient", "Table 5 p.16"),
    _r("NRU.APPETITE_FAILED", "Appetite test failed (anorexia is a danger sign) in SAM: inpatient", "Table 5 p.16; s.1.8 p.11"),
    _r("OTP.ELIGIBLE", "SAM, oedema at most ++, appetite passed, no complications, well and alert: OTP", "Table 5 p.17"),
    _r("SAM.ASSESS", "SAM with essential information missing: urgent assessment OTP vs inpatient", "Table 5 pp.16-17", RECOMMENDATION),
    _r("MAM.HIV_OTP", "HIV-positive child with MAM, appetite passed, no complications, well and alert: admit to OTP", "Table 5 p.17"),
    _r("MAM.SFP", "Moderate wasting: SFP / further assessment", "Table 5 p.17"),
    _r("LOW.NONE", "No CMAM criterion met on valid measurements", "n/a (engine default)", RECOMMENDATION),
    _r("INF.WFL", "Infant <6 months: WFL z <-3 (length >=45 cm)", "Table 5 p.16"),
    _r("INF.OEDEMA", "Infant <6 months: any bilateral pitting oedema", "Table 5 p.16"),
    _r("INF.VISIBLE_WASTING", "Infant <6 months: visible severe wasting", "Table 5 p.16"),
    _r("INF.TOO_WEAK", "Infant <6 months: too weak to suckle effectively", "Table 5 p.16"),
    _r("INF.NO_GAIN", "Infant <6 months: failure to gain weight (refer to NRU)", "Table 5 p.16 footnote"),
    _r("INF.WEIGHT_LT3KG", "Infant at or above 6 months weighing <3.0 kg: inpatient (printed as '> 6 months'; applied from 6.0 months)", "Table 5 p.16"),
    _r("INF.WFA_CLINICIAN", "Infant <6 months with WFA z <-3: refer to clinician for further assessment; tier mapping to MAM is an assumption", "Table 5 p.16 footnote", ASSUMPTION),
    _r("DATA.IMPLAUSIBLE_IGNORED", "Implausible-flagged z-score not used", "engine policy", RECOMMENDATION),
])

REFERRAL = {
    "SAM_INPATIENT": PLACEHOLDER + "Urgent referral to the Nutrition Rehabilitation Unit (NRU, inpatient care).",
    "SAM_OTP": PLACEHOLDER + "Urgent referral to the Outpatient Therapeutic Programme (OTP).",
    "SAM_ASSESS": PLACEHOLDER + "Urgent clinical assessment: determine OTP versus inpatient (NRU) care.",
    "MAM": PLACEHOLDER + "Refer for further assessment and the Supplementary Feeding Programme (SFP).",
    "MAM_HIV_OTP": PLACEHOLDER + "HIV-positive child with moderate acute malnutrition: refer for admission to OTP.",
    "LOW_RISK": PLACEHOLDER + "Nutrition counselling and routine growth monitoring.",
    "UNABLE_TO_CLASSIFY": "Recheck measurements or complete the missing assessments. Unable to classify.",
}
