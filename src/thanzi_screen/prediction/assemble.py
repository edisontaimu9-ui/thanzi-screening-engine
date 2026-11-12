"""From children to training examples: features at each index visit, labels from later visits, split by child."""
from __future__ import annotations

from dataclasses import dataclass

from .features import build_features
from .preprocess import Preprocessor, UnseenMissingError, split_children
from .records import Child
from .targets import TARGETS, TargetConfig, label_targets

MIN_INDEX_MONTHS = 6.0


@dataclass(frozen=True)
class Example:
    child_id: str
    index_age_days: int
    split: str
    district: str | None          # fairness checks only
    period: str | None            # fairness checks only
    features: dict
    labels: dict                  # {target: 0 | 1 | None}
    reasons: dict                 # {target: reason code | None}


def build_examples(children: list[Child], target_cfg: TargetConfig | None = None, seed: int = 0,
                   min_index_months: float = MIN_INDEX_MONTHS) -> list[Example]:
    splits = split_children([c.child_id for c in children], seed)
    out = []
    for c in children:
        for i, o in enumerate(c.observations):
            if o.visit.age_days / 30.4375 < min_index_months:
                continue
            lab = label_targets(c, i, target_cfg)
            out.append(Example(c.child_id, o.visit.age_days, splits[c.child_id], c.district, o.period,
                               build_features(c, i), {t: lab[t]["label"] for t in TARGETS},
                               {t: lab[t]["reason"] for t in TARGETS}))
    return out


def label_summary(examples: list[Example]) -> dict:
    """Per target: positives, negatives, and why the rest are excluded. Censoring is reported, never hidden."""
    out = {}
    for t in TARGETS:
        pos = sum(e.labels[t] == 1 for e in examples)
        neg = sum(e.labels[t] == 0 for e in examples)
        reasons: dict[str, int] = {}
        for e in examples:
            if e.labels[t] is None:
                reasons[e.reasons[t]] = reasons.get(e.reasons[t], 0) + 1
        out[t] = {"positives": pos, "negatives": neg, "prevalence": round(pos / (pos + neg), 4) if pos + neg else None,
                  "excluded": dict(sorted(reasons.items()))}
    return out


def select(examples: list[Example], target: str, split: str) -> list[Example]:
    return [e for e in examples if e.split == split and e.labels[target] is not None]


def matrix(examples: list[Example], target: str, split: str, pre: Preprocessor, skipped: list | None = None):
    """(X, y, rows). A row with a gap the preprocessor has never seen in training is left out and appended to `skipped`."""
    X, y, kept = [], [], []
    for e in select(examples, target, split):
        try:
            X.append(pre.transform(e.features))
        except UnseenMissingError:
            if skipped is not None:
                skipped.append(e)
            continue
        y.append(e.labels[target])
        kept.append(e)
    return X, y, kept
