"""Full official titles for every source the engine cites.

Use these strings wherever a source is named in user-facing text, rule traces and generated documents, so a
reference is never an abbreviation alone. Titles, years and editions are the ones recorded in
`docs/references/register.md`; do not add publication details that are not recorded there.
"""
from __future__ import annotations

# Malawi Ministry of Health guidelines (register R3, R15).
CMAM_TITLE = "Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016"
CMAM_TITLE_EDITION = ("Malawi Guidelines for Community-Based Management of Acute Malnutrition (CMAM), "
                      "2nd Edition, Ministry of Health, 2016")
COIN_TITLE = "Care of the Infant and Newborn (COIN), Malawi, 2017"
COIN_MANUAL_TITLE = "Care of the Infant and Newborn (COIN), Malawi, 2017, Participants' Manual"

# Growth references (register R1, R4, R5, R14, R19, R20, R21).
WHO_STANDARDS_TITLE = "WHO Child Growth Standards, 2006"
FENTON_TITLE = "Fenton 2025 Preterm Growth Chart, 2025"
ASPEN_TITLE = "ASPEN Paediatric and Neonatal Nutrition Support Handbook, Third Edition, 2024"
WHO_GROWTH_MONITORING_TITLE = "Child Growth Monitoring: A Technical Guide for Healthcare Professionals, WHO Regional Office for the Eastern Mediterranean"

# Register id -> full citation. The id stays as a stable key; the citation is what readers see.
REGISTER_CITATIONS: dict[str, str] = {
    "R3": CMAM_TITLE_EDITION,
    "R15": COIN_MANUAL_TITLE,
    "R14": FENTON_TITLE,
    "R19": ASPEN_TITLE,
    "R21": WHO_GROWTH_MONITORING_TITLE,
}


def cite(register_id: str, locator: str = "") -> str:
    """Full citation for a register id, with an optional locator such as 'Table 5, p.16'."""
    base = REGISTER_CITATIONS.get(register_id, register_id)
    return f"{base}, {locator}" if locator else base
