"""Evidence for each review reason (Phase 5). The reason codes come from `rules.review.review`; this adds
the value, cut-off and margin behind each one. It never adds or removes a reason."""
from __future__ import annotations

from dataclasses import dataclass

from ..rules import rules_v2016 as R
from ..rules.classify import IMPLAUSIBLE
from ..rules.review import MESSAGES, REVIEW_MUAC_MARGIN_CM, REVIEW_Z_MARGIN
from . import messages as M
from .trace import _band_muac, _band_z, nearest


@dataclass(frozen=True)
class ReviewReason:
    code: str
    message: str
    evidence: str
    values: dict


@dataclass(frozen=True)
class ReviewTrace:
    needed: bool
    reasons: tuple[ReviewReason, ...]
    source: str
    margins: dict


def build_review_trace(anthro, result, clinical, review_result) -> ReviewTrace:
    oedema = clinical.oedema.value != "none"
    muac = clinical.muac_cm
    z = anthro.wflh.z if anthro.wflh.status == "ok" and IMPLAUSIBLE not in anthro.wflh.flags and not oedema else None
    out: list[ReviewReason] = []
    for code in review_result.reasons:
        vals: dict = {}
        ev = M.REVIEW_EVIDENCE_LABEL[code]
        if code == "near_threshold_muac" and muac is not None:
            c, mg = nearest(muac, (R.MUAC_SEVERE_CM, R.MUAC_MODERATE_CM))
            vals = {"muac_cm": muac, "cutoff": c, "difference": mg, "review_margin": REVIEW_MUAC_MARGIN_CM}
            ev = f"MUAC {muac:g} cm is {abs(mg):g} cm {'above' if mg > 0 else 'below' if mg < 0 else 'on'} the {c:g} cm cut-off (review margin {REVIEW_MUAC_MARGIN_CM:g} cm)."
        elif code == "near_threshold_z" and z is not None:
            c, mg = nearest(z, (R.WFLH_SEVERE_Z, R.WFLH_MODERATE_Z))
            vals = {"wflh_z": round(z, 4), "cutoff": c, "difference": round(mg, 4), "review_margin": REVIEW_Z_MARGIN}
            ev = f"Weight-for-length/height z {z:.2f} is {abs(mg):.2f} from the {c:g} cut-off (review margin {REVIEW_Z_MARGIN:g})."
        elif code == "discordant_muac_vs_wflh" and muac is not None and z is not None:
            vals = {"muac_cm": muac, "muac_band": _band_muac(muac), "wflh_z": round(z, 4), "wflh_band": _band_z(z)}
            ev = f"MUAC {muac:g} cm is in the {_band_muac(muac)} band, weight-for-length/height z {z:.2f} is in the {_band_z(z)} band."
        elif code == "implausible_value":
            names = [n for n, i in (("weight-for-age", anthro.wfa), ("length/height-for-age", anthro.lhfa),
                                    ("weight-for-length/height", anthro.wflh)) if i.status == "ok" and IMPLAUSIBLE in i.flags]
            vals = {"implausible": names}
            ev = "Outside the WHO plausible range: " + ", ".join(names) + "."
        elif code == "weight_under_3kg_verify" and anthro.weight_kg is not None:
            vals = {"weight_kg": anthro.weight_kg, "limit_kg": R.INFANT_WEIGHT_NRU_KG}
            ev = f"Weight {anthro.weight_kg:g} kg is below {R.INFANT_WEIGHT_NRU_KG:g} kg at 6 months or older."
        elif code in ("unable_to_classify", "missing_assessment"):
            vals = {"classification_reasons": list(result.reasons)}
            ev = M.REVIEW_EVIDENCE_LABEL[code] + (" " + "; ".join(M.REASON_TEXT.get(r, r) for r in result.reasons) + "."
                                                  if result.reasons else "")
        out.append(ReviewReason(code, MESSAGES[code], ev, vals))
    return ReviewTrace(review_result.needed, tuple(out), review_result.source,
                       {"muac_cm": REVIEW_MUAC_MARGIN_CM, "z": REVIEW_Z_MARGIN})
