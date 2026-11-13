"""Model card for the exported prediction models. Standard library. Written from the results and the exported files, so every
number on the card is one the pipeline produced; nothing is typed in by hand.
"""
from __future__ import annotations

from .candidates import LABELS

MAX_LIST = 12


def _f(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def _pct(v, d=1):
    return "n/a" if v is None else f"{v * 100:.{d}f}%"


def _ci(p, d=3):
    return "n/a" if not p or p[0] is None else f"{p[0]:.{d}f} to {p[1]:.{d}f}"


def _target_section(t: str, r: dict, spec: dict | None, parity: float | None) -> list[str]:
    lines = [f"## {t}", ""]
    if r["status"] != "trained" or spec is None:
        reason = r.get("reason") or "no model was exported"
        return lines + [f"**Not exported.** {reason}", ""]
    sel = r["selection"]["selected"]
    m = r["test"]["models"][sel]
    tg = spec["target"]
    lines += [f"Model `{spec['version']}`, {LABELS[sel]} (`{spec['kind']}`). Target: {tg['name']}, the outcome within {tg['horizon_min_days']} to "
              f"{tg['horizon_max_days']} days after the index visit. {tg['definition']}", "",
              f"Selection: {r['selection']['reason']}.", ""]
    s = r["splits"]
    lines.append("Rows (events): " + ", ".join(f"{k} {v['rows']} ({v['events']})" for k, v in s.items()) + ". Children never span splits.")
    lines += ["", f"Test AUROC {_f(m['auroc'])} (95% child-level interval {_ci(m['auroc_ci'])}), AUPRC {_f(m['auprc'])} "
              f"(prevalence {_f(r['test']['prevalence'], 4)}), Brier {_f(m['brier'], 4)}. Calibration slope after Platt scaling "
              f"{_f(m['calibration_after']['slope'], 2)}, intercept {_f(m['calibration_after']['intercept'], 2)} (ideal 1 and 0).",
              f"Best single feature on the same rows: AUROC {_f(r['test']['models']['baseline']['auroc'])} "
              f"(`{r['params']['baseline']['feature']}`). The model must beat it to earn its complexity; the difference is "
              f"{_f(m.get('auroc_diff_vs_baseline', {}).get('diff'))} ({_ci(m.get('auroc_diff_vs_baseline', {}).get('ci'))})."
              if sel != "baseline" else "", ""]
    st = r["test"].get("strata")
    if st:
        c = st["cutoffs"]
        lines += ["### Risk strata (cut-offs fixed on validation children, rates observed on test children)", "",
                  f"`elevated` from calibrated probability {c['elevated']:.4f} (validation alert rate {st['alert_rates']['elevated']:.0%}); "
                  f"`high` from {c['high']:.4f} ({st['alert_rates']['high']:.0%}). Below `elevated` the model says nothing: it is never "
                  "reported as \"low risk\".", "",
                  "| Stratum | Children | Share | Events | Event rate | Share of all events |", "|---|---|---|---|---|---|"]
        for row in st["table"]:
            lines.append(f"| {row['stratum']} | {row['n']} | {_pct(row['share_of_children'])} | {row['events']} | "
                         f"{_pct(row['event_rate'])} | {_pct(row['share_of_all_events'])} |")
        lines += ["", "The alert rate depends on the children seen. In a different population the same cut-offs flag a different share, "
                  "so the alert rate must be monitored after any rollout.", ""]
    fb = r["followup_balance"]
    big = sorted(((k, v) for k, v in fb["features"].items() if v), key=lambda kv: -abs(kv[1]["std_diff"]))[:3]
    lines += [f"Loss to follow-up: {fb['lost_to_followup']} index visits with no visit in the window against {fb['labelled']} labelled. "
              "Largest standardised differences: " + (", ".join(f"{k} {v['std_diff']:+.2f}" for k, v in big) or "n/a")
              + ". A large difference in wealth, WHZ or MUAC would mean the labelled children are not a fair sample.", ""]
    sub = r["test"]["subgroups"]["tables"]
    lines += ["### Subgroups (test children, selected model, at the `high` cut-off)", ""]
    for name, rows in sub.items():
        lines += [f"**{name}**", "", "| Group | n | Events | AUROC | Sensitivity | PPV | Alert rate | Note |", "|---|---|---|---|---|---|---|---|"]
        for row in rows[:MAX_LIST]:
            lines.append(f"| {row['group']} | {row['n']} | {row['events']} | {_f(row['auroc'])} | {_pct(row['sensitivity'])} | "
                         f"{_pct(row['ppv'])} | {_pct(row['alert_rate'])} | {'small group: wide uncertainty' if row['small'] else ''} |")
        if len(rows) > MAX_LIST:
            lines.append(f"| ... {len(rows) - MAX_LIST} more groups in results.json | | | | | | | |")
        lines.append("")
    if parity is not None:
        lines += [f"Export check: the JSON model matches the training library to {parity:.1e} on validation rows (limit 1e-5).", ""]
    return lines


def render_model_card(results: dict, specs: dict, parities: dict | None = None, provenance: str = "simulated") -> str:
    parities = parities or {}
    lines = ["# Model card: under-five malnutrition prediction models", ""]
    if provenance == "simulated":
        lines += ["**SIMULATED DATA. NOT CLINICAL.** Every association was assumed by the simulator, so these numbers only show that the "
                  "pipeline works. They say nothing about Malawian children. The service refuses these files unless simulated models "
                  "are explicitly allowed, and `clinical_use` is false.", ""]
    else:
        lines += ["Trained on real data. Not for clinical use until the acceptance checks have passed and clinical sign-off is recorded "
                  "in the model file. The service refuses a model without them.", ""]
    paths = {(sp.get("pathway") or {}).get("name", "full") for sp in specs.values()}
    if paths - {"full"}:
        lines += ["**Pathway: " + ", ".join(sorted(paths)) + ".** Built from measurements only (this visit and earlier visits). Clinical history, feeding, "
                  "birth, maternal and household answers are not inputs, so leaving them empty never stops a score and they are never filled in. "
                  "A share of training rows had earlier visits withheld, so a first visit can be scored.", ""]
        for t, c in sorted((results.get("pathway_check") or {}).items()):
            lines.append(f"- {t}: test AUROC {c['no_earlier_visit']['auroc']} with no earlier visit ({c['no_earlier_visit']['n']} rows), "
                         f"{c['earlier_visit']['auroc']} with one ({c['earlier_visit']['n']} rows).")
        lines.append("")
    ds = results.get("dataset", {})
    lines += [f"Dataset SHA-256 `{str(ds.get('sha256', ''))[:16]}...`, {ds.get('rows', '?')} visits, {ds.get('children', '?')} children. "
              f"Same data and seed give identical files.", "",
              "## What the models do", "",
              "Each model estimates the chance that a child aged 6 to 59 months will reach one outcome (wasting, severe acute "
              "malnutrition, or weight faltering) in the 1 to 6 months after a visit. A model can only add a concern (\"closer follow-up "
              "suggested\"). It never changes a CMAM classification, tier, referral or warning, never says a child is low risk, and says "
              "nothing when it finds no extra concern. The CMAM classification is not an input. Age is checked, the number of missing inputs is "
              "limited to what training rows had, and a gap never seen in training is refused, not filled in.", "",
              "## What they do not do", "",
              "- They do not diagnose. They rank children by estimated chance and are advisory only.",
              "- They are not validated on real children. A model built on real data still needs acceptance thresholds set in advance.",
              "- Drivers say what contributed to a number, not what caused an outcome.",
              "- The 28 to 180 day horizon and the faltering definition are engineering choices that clinical reviewers must confirm.",
              "- Rare outcomes give low positive predictive value whatever the model.", ""]
    for t, r in results["targets"].items():
        lines += _target_section(t, r, specs.get(t), parities.get(t))
    lines += ["## Libraries", "", ", ".join(f"{k} {v}" for k, v in (results.get("libraries") or {}).items() if v) +
              ". Used on the development machine only; the service reads the JSON files and imports none of them.", ""]
    return "\n".join(x for x in lines if x is not None) + "\n"
