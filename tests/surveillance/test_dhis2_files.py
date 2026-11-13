"""The committed DHIS2 templates match the code, and the command-line export builds the same payload as the library."""
import json
import subprocess
import sys
from pathlib import Path

from thanzi_screen.surveillance import Dhis2Mapping, FacilityRow, OrgUnit, build_data_value_set

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "export_dhis2.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT)


def test_committed_templates_are_current():
    r = run("templates", "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_build_matches_the_library_and_skips_underscore_keys(tmp_path):
    org = [{"code": "MW", "name": "Malawi", "level": "national"}, {"code": "D1", "name": "Zomba", "level": "district", "parent": "MW"},
           {"code": "F1", "name": "Zomba Central Hospital", "level": "facility", "parent": "D1"}]
    rows = [{"org_unit": "F1", "period": "2026-10", "screened": 200, "sam": 12, "mam": 20, "unable": 1}]
    mapping = {"_note": "ignored", "elements": {"screened": "A1", "sam": "B1", "mam": "C1"}}
    (tmp_path / "req.json").write_text(json.dumps({"org_units": org, "rows": rows}))
    (tmp_path / "map.json").write_text(json.dumps(mapping))
    r = run("build", str(tmp_path / "req.json"), str(tmp_path / "map.json"), "-o", str(tmp_path / "out.json"))
    assert r.returncode == 0, r.stderr
    expected = build_data_value_set([OrgUnit(**u) for u in org], [FacilityRow(**x) for x in rows],
                                    Dhis2Mapping(elements=mapping["elements"]))["data_value_set"]
    assert json.loads((tmp_path / "out.json").read_text()) == expected and "dryRun=true" in r.stdout


def test_build_stops_on_an_incomplete_mapping(tmp_path):
    (tmp_path / "req.json").write_text(json.dumps({"org_units": [{"code": "MW", "name": "Malawi", "level": "national"}],
                                                   "rows": [{"org_unit": "MW", "period": "2026-10", "screened": 1, "sam": 0, "mam": 0}]}))
    (tmp_path / "map.json").write_text(json.dumps({"elements": {"screened": "A1"}}))
    r = run("build", str(tmp_path / "req.json"), str(tmp_path / "map.json"), "-o", str(tmp_path / "out.json"))
    assert r.returncode == 2 and not (tmp_path / "out.json").exists()
