"""The perf-station runner's refusals.

Every test here is a case where the runner MUST say "cannot measure" rather
than print a verdict. They exist because the harness's first run produced a
confident wrong answer twice over:

  * it measured a package that had never been imported, so no GLB loaded,
    only the four dressing MultiMeshes drew, and 4 draw calls at all 29
    stations came out as "every station inside budget";
  * that same run's watchdog had fired, so the verdict was also delivered
    over a TRUNCATED report.

`CLAUDE.md`: read one real instance of an artefact before writing the code
that reads it, and make an unrecognised shape FAIL rather than pass.

THE STUB WRITES THE REPORT, it is not pre-seeded, because the runner deletes
a stale `perf_stations.json` before launching. That deletion is correct and
is the only thing standing between a failed run and a verdict read off the
previous run's numbers -- so the tests have to go through it rather than
around it. An earlier version of this file pre-seeded the file, every case
died on "the probe wrote no report", and one of them PASSED anyway because
it was only asserting the exit code.
"""
import json
import subprocess
import sys
from pathlib import Path

# INSIDE THE REPO, not counted up out of it. `parents[3]` would be the
# factory root, which is correct from a checkout sitting beside its siblings
# and wrong from a git worktree -- `test_sibling_locator.py` guards against
# exactly that arithmetic and caught this file.
_REPO = Path(__file__).resolve().parents[2]
RUNNER = _REPO / "tools" / "perf_stations_run.py"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CANNOT = 2

ROW = {
    "station": "player_start_0", "type": "player_start",
    "pos": [0.0, 1.6, 0.0],
    "worst_heading": {"yaw": 0.0, "ms_p95": 4.0, "ms_worst": 5.0,
                      "gpu_ms": 1.0, "render_cpu_ms": 2.0,
                      "draws": 100, "primitives": 1000, "objects": 10},
    "mean_p95_over_headings": 4.0, "headings": [],
    "light_census": {"cap": 8, "meshes": 10, "over_cap": 0, "worst": 2,
                     "worst_mesh": "x"},
}


def _run(pkg, *extra):
    return subprocess.run(
        [sys.executable, str(RUNNER), str(pkg), *extra],
        capture_output=True, text=True)


def _pkg(tmp_path, anchors=True, project=True, imported=True):
    p = tmp_path / "pkg"
    p.mkdir()
    if project:
        (p / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    if anchors:
        (p / "gameplay_anchors.json").write_text(
            json.dumps({"schema": "dispatch.gameplay_anchors.v0.2",
                        "anchors": []}), encoding="utf-8")
    if imported:
        (p / ".godot").mkdir()
    return p


def _stub_godot(tmp_path, pkg, doc):
    """A stand-in for Godot that writes `doc` as the report and exits."""
    src = tmp_path / "report_src.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    dst = pkg / "perf_stations.json"
    if sys.platform == "win32":
        s = tmp_path / "godot.cmd"
        body = '@echo off\r\ncopy /y "{0}" "{1}" >nul\r\nexit /b 0\r\n'.format(
            src, dst)
    else:
        s = tmp_path / "godot.sh"
        body = "#!/bin/sh\ncp '{0}' '{1}'\nexit 0\n".format(src, dst)
    s.write_text(body, encoding="utf-8")
    if sys.platform != "win32":
        s.chmod(0o755)
    return s


# --- refusals before anything is launched --------------------------------

def test_no_project_cannot_measure(tmp_path):
    out = _run(_pkg(tmp_path, project=False))
    assert out.returncode == EXIT_CANNOT
    assert "no project.godot" in out.stdout


def test_no_anchors_cannot_measure(tmp_path):
    """Stations come from the package. One that carries none cannot be
    measured, and must not read as a level with no problems."""
    out = _run(_pkg(tmp_path, anchors=False))
    assert out.returncode == EXIT_CANNOT
    assert "gameplay_anchors" in out.stdout


def test_missing_godot_cannot_measure(tmp_path):
    out = _run(_pkg(tmp_path), "--godot", str(tmp_path / "nope.exe"))
    assert out.returncode == EXIT_CANNOT
    assert "no Godot binary" in out.stdout


# --- refusals on the report's shape, which is where run 1 went wrong -----

def test_unrecognised_schema_fails_rather_than_passes(tmp_path):
    pkg = _pkg(tmp_path)
    doc = {"schema": "something.else.v9", "complete": True, "rows": [ROW]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)))
    assert out.returncode == EXIT_CANNOT
    assert "schema" in out.stdout


def test_incomplete_report_is_not_a_pass(tmp_path):
    """The watchdog writes what it has so the numbers are not lost. A caller
    reading those as a finished run is the defect this guards."""
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": False,
           "rows": [ROW]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)))
    assert out.returncode == EXIT_CANNOT
    assert "did not finish" in out.stdout


def test_no_rows_is_not_a_pass(tmp_path):
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "rows": []}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)))
    assert out.returncode == EXIT_CANNOT
    assert "no station rows" in out.stdout


# --- and the two real verdicts -------------------------------------------

def test_over_budget_is_findings_not_failure(tmp_path):
    """EXIT_FINDINGS is 1 and is not a failure -- the same split the rest of
    Level Factory uses, where only BLOCKED is fatal."""
    pkg = _pkg(tmp_path)
    row = json.loads(json.dumps(ROW))
    row["worst_heading"]["draws"] = 9000
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "rows": [row]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)),
               "--draws", "2000")
    assert out.returncode == EXIT_FINDINGS
    assert "PERF_STATION_OVER_BUDGET" in out.stdout


def test_within_budget_is_clean(tmp_path):
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "rows": [ROW]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)),
               "--draws", "2000", "--ms", "11")
    assert out.returncode == EXIT_OK
    assert "every station inside budget" in out.stdout


def test_the_budget_can_actually_fail_the_same_row(tmp_path):
    """THE CONTROL. Every test above could pass with a runner that always
    said the same thing; this one asserts the verdict MOVES on identical
    input when only the budget changes. A gate that cannot fail is
    indistinguishable from one that passed."""
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "rows": [ROW]}
    stub = str(_stub_godot(tmp_path, pkg, doc))
    lenient = _run(pkg, "--godot", stub, "--draws", "2000", "--ms", "11")
    strict = _run(pkg, "--godot", stub, "--draws", "50", "--ms", "1")
    assert lenient.returncode == EXIT_OK
    assert strict.returncode == EXIT_FINDINGS


def test_the_meshes_over_the_light_cap_are_named(tmp_path):
    """0.125.0: cold run 9125 moved one light, the over-cap count went 43 ->
    44, and the report could not say which mesh crossed. The probe now lists
    them by node path; the runner names the worst. An older report, which
    has no list, still reads."""
    pkg = _pkg(tmp_path)
    row = dict(ROW, light_census=dict(ROW["light_census"], over_cap=2, worst=11,
                                      over_list=[{"mesh": "/root/Site/b2/Prop_Panel", "lights": 11},
                                                 {"mesh": "/root/Site/b0/Floor_3", "lights": 9}],
                                      over_list_truncated=False))
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True, "rows": [row]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)), "--draws", "2000", "--ms", "11")
    assert "/root/Site/b2/Prop_Panel" in out.stdout and "/root/Site/b0/Floor_3" in out.stdout
    (tmp_path / "old").mkdir()
    pkg2 = _pkg(tmp_path / "old")
    doc2 = {"schema": "level_factory.perf_stations.v1", "complete": True, "rows": [ROW]}
    out2 = _run(pkg2, "--godot", str(_stub_godot(tmp_path / "old", pkg2, doc2)), "--draws", "2000", "--ms", "11")
    assert out2.returncode == EXIT_OK
