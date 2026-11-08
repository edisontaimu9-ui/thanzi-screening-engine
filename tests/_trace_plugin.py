"""pytest plugin: record which tests make which CMAM rules fire (Phase 7, D94).

Used only by scripts/build_traceability.py and CI:  python -m pytest -p tests._trace_plugin
Active only when THANZI_TRACE_OUT names a file. It observes `ClassificationResult` construction and
changes no behaviour. A rule counts as tested when at least one test makes it appear in `rules_fired`.
"""
import json
import os
from collections import defaultdict

_current = {"id": None}
_fired = defaultdict(set)


def pytest_configure(config):
    if not os.environ.get("THANZI_TRACE_OUT"):
        return
    from thanzi_screen.rules.models import ClassificationResult
    original = ClassificationResult.__init__

    def observed(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if _current["id"]:
            for rule in self.rules_fired:
                _fired[rule].add(_current["id"])

    ClassificationResult.__init__ = observed


def pytest_runtest_setup(item):
    _current["id"] = item.nodeid


def pytest_runtest_teardown(item):
    _current["id"] = None


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("THANZI_TRACE_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"exitstatus": int(exitstatus), "fired": {k: sorted(v) for k, v in sorted(_fired.items())}}, fh, indent=1)
