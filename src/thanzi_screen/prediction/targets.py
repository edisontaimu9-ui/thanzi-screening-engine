"""Outcome labels, built from LATER visits of the same child. Never stored as dataset columns.

Targets (all relative to an index visit; horizon window default 28 to 180 days after it):
- future_wasting:   at any usable visit in the window, WHZ below -2, MUAC below 12.5 cm or oedema.
- future_sam:       at any usable visit in the window, WHZ below -3, MUAC below 11.5 cm or oedema.
- future_faltering: at the first usable visit in the window, WAZ has fallen by fall_sd or more since the index visit,
                    or the weight is lower by at least min_weight_loss_kg (0.1 kg).

Incident prediction: for wasting and SAM, an index visit that is already at the outcome is excluded (label None, reason
already_at_outcome), because predicting what is already true is not a forecast.

Missing follow-up is NOT a negative. No visit in the window, or no usable one, gives label None with a reason. These are
reported as censored so loss to follow-up can be examined, never silently counted as "stayed well".
The cut-offs are the CMAM Guidelines, Malawi, 2016 MUAC cut-offs and WHO z-score lines. The faltering definition and the
horizon are engineering choices to be agreed with clinical reviewers before real training.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..rules import rules_v2016 as R
from .measures import Measures, measures
from .records import Child

TARGETS = ("future_wasting", "future_sam", "future_faltering")


@dataclass(frozen=True)
class TargetConfig:
    horizon_min_days: int = 28
    horizon_max_days: int = 180
    fall_sd: float = 1.0
    min_weight_loss_kg: float = 0.1       # about the resolution of a clinic scale: smaller drops are not read as loss
    wasting_z: float = -2.0
    sam_z: float = -3.0


def _state(m: Measures, z_cut: float, muac_cut: float) -> bool | None:
    """True if at the outcome by any available indicator, False if none are, None if nothing is available."""
    if m.oedema:
        return True
    known = []
    if m.whz is not None:
        known.append(m.whz < z_cut)
    if m.muac_cm is not None:
        known.append(m.muac_cm < muac_cut)
    if not known:
        return None
    return any(known)


def label_targets(child: Child, index: int, cfg: TargetConfig | None = None) -> dict[str, dict]:
    """{target: {"label": 0|1|None, "reason": str|None}} for the observation at `index`."""
    cfg = cfg or TargetConfig()
    m0 = measures(child.sex, child.observations[index].visit)
    if not m0.usable:
        return {t: {"label": None, "reason": "index_not_usable"} for t in TARGETS}
    window, any_follow = [], False
    for o in child.observations[index + 1:]:
        gap = o.visit.age_days - m0.age_days
        if cfg.horizon_min_days <= gap <= cfg.horizon_max_days:
            any_follow = True
            m = measures(child.sex, o.visit)
            if m.usable:
                window.append(m)
    if not any_follow:
        none = {"label": None, "reason": "no_followup_in_window"}
        out = {t: dict(none) for t in TARGETS}
    elif not window:
        none = {"label": None, "reason": "followup_not_usable"}
        out = {t: dict(none) for t in TARGETS}
    else:
        out = {}
    for name, z_cut, muac_cut in (("future_wasting", cfg.wasting_z, R.MUAC_MODERATE_CM),
                                  ("future_sam", cfg.sam_z, R.MUAC_SEVERE_CM)):
        base = _state(m0, z_cut, muac_cut)
        if base is True:
            out[name] = {"label": None, "reason": "already_at_outcome"}
        elif base is None:
            out[name] = {"label": None, "reason": "index_status_unknown"}
        elif name not in out:
            states = [_state(m, z_cut, muac_cut) for m in window]
            if any(s is True for s in states):
                out[name] = {"label": 1, "reason": None}
            elif any(s is False for s in states):
                out[name] = {"label": 0, "reason": None}
            else:
                out[name] = {"label": None, "reason": "followup_status_unknown"}
    if "future_faltering" not in out:
        f = window[0]
        if m0.waz is None or f.waz is None:
            out["future_faltering"] = {"label": None, "reason": "waz_unavailable"}
        else:
            fell = (f.waz - m0.waz) <= -cfg.fall_sd or (m0.weight_kg - f.weight_kg) >= cfg.min_weight_loss_kg
            out["future_faltering"] = {"label": int(fell), "reason": None}
    return out
