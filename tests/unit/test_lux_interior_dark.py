"""Interiors read dark by default, and the light budget counts what Lux built.

Lux 0.38.0 derives one interior ReflectionProbe per room (`bake_room_ambient`,
from the `room_box_local` Deli Counter writes on a room's ceiling anchors) and
0.37.0 bakes a club's lights (`bake_club`); until 0.87.0 the driver called
neither, and the `[rendering]` cap was a count of `type="OmniLight3D"` in
scene text -- which item 56 measured at 136 against 272 lights running.

The driver half is a SOURCE-SHAPE test, for the reason
`test_lux_preset_readback.py` gives: unit CI has no headless Godot. The
hardware evidence is the walk-copy frames in the 0.87.0 changelog entry. The
budget half is real: `package_light_budget` reads the driver's census out of
`lux.quality.json` and takes the larger number, and every branch of "cannot
find the field" is pinned to contribute nothing rather than zero.

Every test here fails on 0.86.1.

Run:  python -m pytest tests/unit/test_lux_interior_dark.py
"""
import json
from pathlib import Path

import pytest

from packages.core.godot_project import (ENGINE_DEFAULT_RENDERABLE_LIGHTS,
                                         LIGHTS_IN_TREE_KEY, QUALITY_RECORD,
                                         count_package_lights,
                                         lights_reported_by_lux,
                                         package_light_budget,
                                         rendering_block)
from packages.exporting.export import _write_project_godot
from packages.preview.walk_preview import _PROJECT

DRIVER = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "run_lux_apply.gd")

_SCENE = '[gd_scene format=3]\n[node name="R" type="Node3D"]\n'
_LIGHT = '[node name="L{i}" type="OmniLight3D" parent="."]\n'


@pytest.fixture(scope="module")
def driver() -> str:
    assert DRIVER.is_file(), f"driver missing at {DRIVER}"
    return DRIVER.read_text(encoding="utf-8")


# --- the driver bakes the rooms and the club, and owns what it baked -------

def test_the_driver_bakes_the_room_probes(driver):
    assert "bake_room_ambient" in driver


def test_the_driver_bakes_the_club_when_the_manifest_carries_one(driver):
    assert "bake_club" in driver
    # The club types are read off the loader, never spelled in the driver:
    # a fifth type Lux adds must be baked the day it lands.
    assert 'get("CLUB_TYPES")' in driver
    assert '"club_wash"' not in driver


@pytest.mark.parametrize("container", ["LuxRoomAmbient", "LuxClub"])
def test_the_driver_owns_the_new_containers_or_pack_drops_them(driver, container):
    """pack() silently drops unowned nodes -- the rule the fixture rigs, the
    daylight rigs and the rain colliders already follow in the same file."""
    assert f'get_node_or_null(NodePath("{container}"))' in driver


@pytest.mark.parametrize("key", [
    '"room_probes"', '"room_probe_rooms"', '"room_probe_rooms_without_box"',
    '"room_probe_msg"', '"club_lights"', '"club_anchors_in_manifest"',
    '"club_refused"', '"club_msg"', f'"{LIGHTS_IN_TREE_KEY}"'])
def test_the_quality_record_reports_the_rooms_the_club_and_the_census(driver, key):
    assert key in driver, key


def test_the_census_is_taken_after_every_bake_and_before_pack(driver):
    """The number the cap is written from must see the club and the room
    bake's neighbours, and must be taken from the tree pack() will save."""
    census = driver.index("var lights_in_tree := _count_lights(scene)")
    assert driver.index("bake_room_ambient(lights_path, scene)") < census
    assert driver.index("bake_club(lights_path, scene)") < census
    assert census < driver.index("applied.pack(scene)")


@pytest.mark.parametrize("code", ["LUX_NO_ROOM_PROBES", "LUX_CLUB_REFUSED"])
def test_rooms_without_probes_and_refused_club_anchors_are_findings(driver, code):
    assert code in driver


# --- is there a lamp where the light comes from (0.90.0) -------------------


def test_the_driver_measures_club_lights_against_zoos_hardware(driver):
    """Walked 2026-09-16 on cold run 9060: "awesome lighting in the strip
    club, but it doesn't look like that light is coming out of any viewable
    light fixtures". Nothing in the pipeline could see it -- the fixture gate
    only looks at emitter markers, and the club set deliberately has none."""
    assert "_collect_hardware" in driver
    assert "_box_distance" in driver
    assert "LUX_CLUB_LIGHT_WITHOUT_HARDWARE" in driver


def test_the_hardware_types_are_read_off_the_loader_not_spelled_here(driver):
    """The same rule `CLUB_TYPES` follows, for the same reason: a third type
    Zoo grows hardware for must be checked the day it lands, and a list
    copied into this file is a schema guess that cannot fail."""
    assert 'get("CLUB_HARDWARE_TYPES")' in driver
    assert 'get("CLUB_HARDWARE_PREFIX")' in driver
    assert '"stage_light"' not in driver
    # ...and an older Lux that does not carry them says so rather than passing
    assert "Lux < 0.40.0" in driver


@pytest.mark.parametrize("key", [
    '"club_hardware_checked"', '"club_hardware_worst_m"',
    '"club_without_hardware"', '"club_hardware_msg"'])
def test_the_quality_record_reports_the_hardware_measurement(driver, key):
    assert key in driver, key


def test_the_tolerance_is_a_named_constant_with_a_derivation(driver):
    """Zoo mounts a club fixture with its lit lens ON the anchor, so the
    right answer is 0 and this is float noise -- not an allowance, and not
    the fixture gate's 0.25 m, which answers a different question."""
    assert "CLUB_HARDWARE_TOLERANCE_M" in driver
    assert "0.05" in driver


def test_an_older_lux_is_named_not_defaulted(driver):
    assert "Lux < 0.38.0" in driver
    assert "Lux < 0.37.0" in driver


# --- the light budget reads the driver's census ----------------------------

def _package(root: Path, lights: int, census=None, where="presentation"):
    (root / where).mkdir(parents=True, exist_ok=True)
    (root / where / "lit.tscn").write_text(
        _SCENE + "".join(_LIGHT.format(i=i) for i in range(lights)),
        encoding="utf-8")
    if census is not None:
        (root / where / QUALITY_RECORD).write_text(
            census if isinstance(census, str) else json.dumps(census),
            encoding="utf-8")
    return root


def _cap(text: str):
    for line in text.splitlines():
        if line.startswith("limits/opengl/max_renderable_lights="):
            return int(line.split("=", 1)[1])
    return None


def test_the_census_raises_the_cap_above_the_text_count(tmp_path):
    _package(tmp_path, 40, {LIGHTS_IN_TREE_KEY: 57})
    assert count_package_lights(tmp_path) == 40
    assert lights_reported_by_lux(tmp_path) == 57
    assert package_light_budget(tmp_path) == 57


def test_a_census_below_the_text_count_never_lowers_it(tmp_path):
    """The text count is still the only number that sees lights arriving by
    paths the driver never ran (Lot's own scene)."""
    _package(tmp_path, 40, {LIGHTS_IN_TREE_KEY: 12})
    assert package_light_budget(tmp_path) == 40


def test_no_record_means_the_text_count_stands_alone(tmp_path):
    _package(tmp_path, 40)
    assert lights_reported_by_lux(tmp_path) is None
    assert package_light_budget(tmp_path) == 40


@pytest.mark.parametrize("record", [
    "{not json",
    json.dumps({"fixture_lights": 83, "daylight_lights": 15}),   # pre-0.87.0 driver
    json.dumps({LIGHTS_IN_TREE_KEY: "98"}),
    json.dumps({LIGHTS_IN_TREE_KEY: True}),
    json.dumps([1, 2, 3]),
])
def test_a_record_without_the_field_contributes_nothing_not_zero(tmp_path, record):
    """A checker that cannot find the field it wants has learned nothing:
    None, never 0 -- so the text count is not silently compared against a
    zero and left standing as if the census had agreed with it."""
    _package(tmp_path, 40, record)
    assert lights_reported_by_lux(tmp_path) is None
    assert package_light_budget(tmp_path) == 40


def test_two_records_contribute_their_largest(tmp_path):
    _package(tmp_path, 10, {LIGHTS_IN_TREE_KEY: 50}, where="presentation")
    _package(tmp_path, 10, {LIGHTS_IN_TREE_KEY: 61}, where="other")
    assert lights_reported_by_lux(tmp_path) == 61
    assert package_light_budget(tmp_path) == 61


def test_the_export_writes_the_census_into_the_cap(tmp_path):
    n = ENGINE_DEFAULT_RENDERABLE_LIGHTS + 5
    _package(tmp_path, 8, {LIGHTS_IN_TREE_KEY: n})
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    assert _cap((tmp_path / "project.godot").read_text(encoding="utf-8")) == n


def test_the_preview_writes_the_same_cap_as_the_export(tmp_path):
    n = ENGINE_DEFAULT_RENDERABLE_LIGHTS + 5
    _package(tmp_path, 8, {LIGHTS_IN_TREE_KEY: n})
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    exported = _cap((tmp_path / "project.godot").read_text(encoding="utf-8"))
    preview = _cap(_PROJECT.format(name="m", level="mission.tscn",
                                   rendering=rendering_block(package_light_budget(tmp_path))))
    assert exported == preview == n


def test_a_census_under_the_engine_default_still_writes_no_cap(tmp_path):
    _package(tmp_path, 8, {LIGHTS_IN_TREE_KEY: ENGINE_DEFAULT_RENDERABLE_LIGHTS})
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    assert "max_renderable_lights" not in (tmp_path / "project.godot").read_text(encoding="utf-8")
