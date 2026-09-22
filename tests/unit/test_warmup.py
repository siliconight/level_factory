"""A package pays its shader compile bill at load, not in the first lap.

WHAT THESE PIN, and what each one cost to learn. Measured on cold run 9066's
package, 2026-09-21, Godot 4.7.stable, gl_compatibility, RTX 2060, a camera
following one six-leg route twice at 3 m/s with BOTH shader caches cleared
before the run:

    lap 1   mean 15.64 ms   2.43% over 16.7 ms   worst 8,564 ms
    lap 2   mean  7.16 ms   0.22% over 16.7 ms   worst    24 ms

* IT IS COMPILATION, AND THE INSTRUMENT THAT SETTLES IT IS OUTSIDE THE
  PROJECT. The renderer's three memory monitors and its resource count are
  flat across every multi-second frame; draw calls and object counts are the
  same on both laps. What moved the number was moving the DRIVER's program
  cache aside -- 172 ms with both caches warm, 376 ms with Godot's wiped,
  8,641 ms with the driver's wiped too. `PIPELINE_COMPILATIONS_*` read 0 on
  every frame of every one of those runs, which is what they do under GL
  Compatibility; they cannot settle this and were not asked to.

* DRAWING EVERY MATERIAL ONCE IS NOT ENOUGH, and this is the one that looks
  obviously sufficient. Every unique material on a quad at spawn took the
  worst frame from 8,564 ms to 5,151 ms; every unique mesh SURFACE, same.
  A GL Compatibility program is specialized on the lighting context of the
  draw, and the renderable-light set is chosen by distance to the camera --
  so the warm-up has to stand where the player will stand. Six headings at
  every light cluster reached 2,730 ms; adding a grid over the level's own
  extent reached 155 ms.

* AND THE STATION SET HAS A PLATEAU, swept in 0.101.0: above about 16
  stations lap 1's worst frame sits at 148-159 ms whatever the grid stride,
  and the cold load sits at 47.8-52.1 s. What still moves is the WARM launch,
  5.9 to 8.7 s, which is the one a player pays on every level after their
  first. The knobs below are the ones that move it, and each has to carry
  what it was measured at.

* THE GUARDS ARE THE SHIPPED ARTEFACT'S, NOT THE REPO'S. A warm-up that runs
  headless costs the QA walkers 252 frames for nothing, and one that runs in
  the editor sweeps the camera while somebody is using it. `audit` reads the
  script out of the PACKAGE, because the gap between what a step believes it
  wrote and what shipped is where 9065's occluders lived.

* WIRING IS IDEMPOTENT AND HONEST ABOUT load_steps. The export is
  re-runnable; two `Warmup` nodes is two sweeps for one level. And
  `mission.tscn` carries its entry script as a sub_resource with NO
  ext_resource block at all, so the branch that inserts the first one is the
  branch every real package takes.

* A PACKAGE THAT NAMES A SCRIPT IT DOES NOT SHIP MUST FAIL. That entry scene
  does not load, and a level that does not load is worse than one that
  stalls.

Run:  python -m pytest tests/unit/test_warmup.py
"""
import json
from pathlib import Path

import pytest

import packages.exporting.warmup as warmup_mod
from packages.exporting.warmup import (HOLDER_NODE, REPORT_NAME,
                                       REQUIRED_GUARDS, SCHEMA, SCRIPT_NAME,
                                       WARMUP_SCRIPT, WarmupError, audit,
                                       emit, script_text, wire_into_scene)

#: `mission.tscn` as `localize.write_entry_scene` writes it: a sub_resource
#: script, no ext_resource block, load_steps=2. Copied from cold run 9066's
#: shipped package rather than invented, so a change to the real template
#: shows up here as a failure instead of passing against a fiction.
ENTRY = '''[gd_scene load_steps=2 format=3]

[sub_resource type="GDScript" id="mission_entry"]
script/source = "extends Node3D

func _ready() -> void:
\tprint('scene instantiated ok')
"

[node name="Mission" type="Node3D"]
script = SubResource("mission_entry")
'''


def _pkg(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "mission.tscn").write_text(ENTRY, encoding="utf-8")
    return tmp_path


def test_the_repo_ships_a_script_and_it_carries_every_guard():
    """The source of truth exists and is not a stub.

    `script_text` refuses rather than shipping one without its guards,
    because a warm-up with no way off is one a recipient cannot A/B against
    the stall it is there to remove.
    """
    assert WARMUP_SCRIPT.is_file(), WARMUP_SCRIPT
    body = script_text()
    for guard in REQUIRED_GUARDS:
        assert guard in body, guard


def test_wiring_adds_one_node_and_one_ext_resource(tmp_path):
    pkg = _pkg(tmp_path)
    assert wire_into_scene(pkg / "mission.tscn") is True
    text = (pkg / "mission.tscn").read_text(encoding="utf-8")
    assert text.count(f'[node name="{HOLDER_NODE}" type="Node3D"') == 1
    assert text.count(f'path="res://{SCRIPT_NAME}"') == 1
    # The header has to stay first, or Godot does not read the file as a
    # scene at all.
    assert text.splitlines()[0].startswith("[gd_scene ")


def test_wiring_bumps_load_steps_for_the_resource_it_added(tmp_path):
    """A scene that lies about its own size is a defect somebody has to read.

    `mission.tscn` goes out at load_steps=2 for its one sub_resource; the
    ext_resource the warm-up adds is a second.
    """
    pkg = _pkg(tmp_path)
    assert "load_steps=2" in (pkg / "mission.tscn").read_text(encoding="utf-8")
    wire_into_scene(pkg / "mission.tscn")
    assert "load_steps=3" in (pkg / "mission.tscn").read_text(encoding="utf-8")


def test_wiring_is_idempotent(tmp_path):
    pkg = _pkg(tmp_path)
    assert wire_into_scene(pkg / "mission.tscn") is True
    first = (pkg / "mission.tscn").read_text(encoding="utf-8")
    assert wire_into_scene(pkg / "mission.tscn") is False
    assert (pkg / "mission.tscn").read_text(encoding="utf-8") == first


def test_wiring_refuses_a_file_that_is_not_a_scene(tmp_path):
    (tmp_path / "mission.tscn").write_text("not a scene\n", encoding="utf-8")
    with pytest.raises(WarmupError):
        wire_into_scene(tmp_path / "mission.tscn")


def test_emit_ships_the_script_the_scene_names(tmp_path):
    pkg = _pkg(tmp_path)
    report = emit(pkg)
    assert report["schema"] == SCHEMA
    assert (pkg / SCRIPT_NAME).is_file()
    assert (pkg / SCRIPT_NAME).read_bytes() == WARMUP_SCRIPT.read_bytes()
    assert report["warmup_nodes"] == 1
    assert report["script_shipped"] is True
    assert sorted(report["guards_present"]) == sorted(REQUIRED_GUARDS)
    written = json.loads((pkg / REPORT_NAME).read_text(encoding="utf-8"))
    assert written["schema"] == SCHEMA


def test_emit_twice_leaves_one_node(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    second = emit(pkg)
    assert second["wired"] is False
    assert second["warmup_nodes"] == 1


def test_audit_fails_when_the_scene_names_a_script_that_did_not_ship(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    (pkg / SCRIPT_NAME).unlink()
    with pytest.raises(WarmupError) as exc:
        audit(pkg)
    assert SCRIPT_NAME in str(exc.value)


def test_audit_fails_when_the_shipped_script_lost_a_guard(tmp_path):
    """The PACKAGE's script, not the repo's.

    An export that copied a stale or edited script ships a warm-up that runs
    headless in every QA walk, and nothing in the scene would show it.
    """
    pkg = _pkg(tmp_path)
    emit(pkg)
    body = (pkg / SCRIPT_NAME).read_text(encoding="utf-8")
    body = body.replace('DisplayServer.get_name() == "headless"', "false")
    (pkg / SCRIPT_NAME).write_text(body, encoding="utf-8")
    with pytest.raises(WarmupError) as exc:
        audit(pkg)
    assert "headless" in str(exc.value)


def test_audit_fails_on_two_warmups(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    text = (pkg / "mission.tscn").read_text(encoding="utf-8")
    (pkg / "mission.tscn").write_text(
        text + f'\n[node name="{HOLDER_NODE}" type="Node3D" parent="."]\n',
        encoding="utf-8")
    with pytest.raises(WarmupError):
        audit(pkg)


def test_audit_is_quiet_about_a_package_with_no_warmup_at_all(tmp_path):
    """Every package before 0.99.0. Consistent, and reported rather than
    raised -- the export decides what to do about it, not the auditor."""
    pkg = _pkg(tmp_path)
    verdict = audit(pkg)
    assert verdict["warmup_nodes"] == 0
    assert verdict["script_shipped"] is False


def test_the_export_ships_a_warmup(tmp_path):
    """THE ONE THAT FAILS ON 0.98.0 FOR THE REASON THAT MATTERS.

    Every test above can be satisfied by a module nothing calls. This asserts
    the export path itself names the step, so a warm-up that exists and is
    never wired -- which is precisely the shape of 0.98.0's occluder defect --
    fails here rather than in somebody's first lap.
    """
    import packages.exporting.export as export_mod
    source = Path(export_mod.__file__).read_text(encoding="utf-8")
    assert "warmup_emit" in source
    assert "warmup_audit" in source
    assert hasattr(export_mod, "ExportWarmupError")


#: A script with the shape `knobs` reads and nothing else: enough to be
#: emitted, not a copy of the real one. Written out rather than derived from
#: `WARMUP_SCRIPT`, so a test about what the report says cannot be satisfied
#: by the report and the script drifting together.
STUB = '''extends Node3D

signal warmup_finished(frames: int, msec: float)

@export var enabled: bool = true
@export var station_spacing_m: float = 7.5
@export var grid_spacing_m: float = 30.0
@export var max_stations: int = 33
@export var warm_light_clusters: bool = false
@export var cover_screen: bool = true

func _ready() -> void:
\tif not enabled:
\t\treturn
\tif Engine.is_editor_hint():
\t\treturn
\tif DisplayServer.get_name() == "headless":
\t\treturn
'''


def _use_stub(monkeypatch, tmp_path, text=STUB):
    """Point the module at a script of this test's own making."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "stub_warmup.gd"
    path.write_bytes(text.encode("utf-8"))
    monkeypatch.setattr(warmup_mod, "WARMUP_SCRIPT", path)
    return path


def test_the_report_reads_its_defaults_out_of_the_script(monkeypatch, tmp_path):
    """FAILS ON 0.100.0, and for the reason the knobs exist at all.

    That version's `warmup.json` named `station_spacing_m: 12.0` and
    `max_stations: 96` as literals in the emit call. Nothing compared them
    with the script, so a retuned script would have shipped a report
    describing the old numbers -- a recorded derivation that is not the
    derivation, which is worse than none because it looks checkable.
    """
    _use_stub(monkeypatch, tmp_path)
    pkg = _pkg(tmp_path / "pkg")
    report = emit(pkg)
    written = json.loads((pkg / REPORT_NAME).read_text(encoding="utf-8"))
    assert written["knobs"]["station_spacing_m"]["default"] == 7.5
    assert written["knobs"]["grid_spacing_m"]["default"] == 30.0
    assert written["knobs"]["max_stations"]["default"] == 33
    assert written["knobs"]["warm_light_clusters"]["default"] is False


def test_every_export_is_recorded_and_an_unrecorded_one_refuses(
        monkeypatch, tmp_path):
    """FAILS ON 0.100.0: it shipped four exports and described two.

    `cover_screen` and `enabled` were knobs a recipient could turn with
    nothing written down about either. A knob with no recorded derivation is
    one nobody can turn and be believed, so a new one has to be measured
    before it can be exported.
    """
    _use_stub(monkeypatch, tmp_path)
    assert set(warmup_mod.knobs(STUB)) == set(warmup_mod.MEASURED)

    grown = STUB + "@export var sweep_headings: int = 6\n"
    _use_stub(monkeypatch, tmp_path / "grown", grown)
    with pytest.raises(WarmupError) as exc:
        script_text()
    assert "sweep_headings" in str(exc.value)


def test_an_export_whose_default_is_not_a_literal_refuses(
        monkeypatch, tmp_path):
    """A default the report cannot state is a default the report must not
    invent. `station_spacing_m: float = _derive()` would have been written
    down as whatever the reader guessed."""
    bad = STUB.replace("@export var max_stations: int = 33",
                       "@export var max_stations: int = _cap()")
    _use_stub(monkeypatch, tmp_path, bad)
    with pytest.raises(WarmupError):
        script_text()


def test_audit_refuses_a_shipped_script_that_is_not_the_repos(tmp_path):
    """FAILS ON 0.100.0, and it is that version's own promise.

    `WarmupError` says "what shipped is not what this module writes" and
    `audit` could not tell: it looked for three substrings, so a script
    truncated after the guards, edited between emit and audit, or left over
    from an older export passed every check. That is the 9065 shape -- a step
    auditing its own intentions -- in the module written to avoid it.
    """
    pkg = _pkg(tmp_path)
    emit(pkg)
    body = (pkg / SCRIPT_NAME).read_text(encoding="utf-8")
    cut = body.index("func _process(")
    (pkg / SCRIPT_NAME).write_text(body[:cut], encoding="utf-8")
    # Every guard is still in it, which is what makes this the interesting
    # case rather than a trivial one.
    for guard in REQUIRED_GUARDS:
        assert guard in body[:cut], guard
    with pytest.raises(WarmupError) as exc:
        audit(pkg)
    assert "byte-for-byte" in str(exc.value)


def test_the_shipped_script_carries_the_grid_as_its_own_knob():
    """FAILS ON 0.100.0: one knob was moving two independent things.

    `station_spacing_m` was the light-cluster radius AND, doubled, the grid's
    stride, so neither could be priced without moving the other. Separated and
    measured on cold run 9066's package, the answer is lopsided: with the grid
    at 24 m, turning the light clusters off moved lap 1's worst frame 153 ->
    157 ms cold and not at all warm, while turning the GRID off moved it to
    1,788 ms. The grid does the work.
    """
    body = script_text()
    assert "@export var grid_spacing_m" in body
    assert "@export var warm_light_clusters" in body
    assert "station_spacing_m * 2.0" not in body
