"""The greybox flight takes a pack the building owns, and says so when it cannot.

ROADMAP 144, WALKED TWICE. LF 0.72.0 wrote the pass and measured it on a
hospital; the walker photographed the same yellow flight again on cold run
9061's `card_shop_a01`, between skinned brick walls, at world (-49.0, 1.6,
-0.2). The pass had not regressed -- it had never been able to answer for that
building. `STAIR_KIND = "concrete"` asks a building for a finish it may not
own, and a card shop's kit is brick, glass facade, drywall and wood panel. The
log said so, four times, into a file nobody reads:

    lot/pharmacy_a01      concrete found in wall_delco_1997_01_w200.glb, and no
                          stair mesh in that base at all -- a correct no-op
                          printed in the same words as a failure
    lot/strip_retail_a02  the same
    site_base.glb (root)  "no art/zoo beside the base" -- an export leftover no
                          scene references, carrying 18 instanced flight meshes
    lot/card_shop_a01     "no imported kit module wearing concrete under
                          art/zoo", 18 flight meshes left in `gb_stair`

So the pack is chosen by FAMILY (`floor_*`, because a tread is a floor) and a
miss is `push_error`, not `print`. These run the real script through a real
Godot import over a generated package, because the defect was invisible to
every source-shape test that could have been written: the GDScript was correct
and the building did not answer it. Each case below fails on 0.91.0.

Skipped where no Godot is installed. `LF_GODOT` overrides, then `DC_GODOT`,
then `LOT_GODOT`, then the usual Windows install path, then PATH.

Run:  python -m pytest tests/unit/test_worldskin_stairs.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_import_fixture import write_glb  # noqa: E402

WORLDSKIN = ROOT / "assets" / "godot" / "zoo_worldskin.gd"

#: The two names the base really carries, from cold run 9061's
#: `card_shop_a01/site_base.glb`: 18 `stair0_*` flight meshes on `gb_stair`
#: and 6 `stair_guard_*` on `gb_prop`, plus `stair0col_*-convcolonly` and
#: `stair0ramp_*` collision. Guards are named here so the exclusion is tested
#: rather than assumed.
FLIGHT = "stair0_0_0"
FLIGHT_2 = "stair0_discharge_0"
GUARD = "stair_guard_rail_1"
COLLISION = "stair0col_under_0_1-convcolonly"
RAMP = "stair0ramp_0"

_PROJECT = """\
config_version=5

[application]
config/name="worldskin stair fixture"

[rendering]
renderer/rendering_method="gl_compatibility"

[importer_defaults]

scene={
"import_script/path": "res://zoo_worldskin.gd"
}
"""


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(
    _godot() is None, reason="no Godot binary; this test imports a real package")


def _project(tmp_path: Path, *, base_meshes, art=True, art_modules=None) -> Path:
    """A one-building package: a base beside `art/zoo/`, exactly the layout
    `_skin_stairs` resolves from `get_source_file().get_base_dir()`."""
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(
        WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", base_meshes,
              [("gb_stair", False), ("gb_prop", False)])
    if art:
        for name in (art_modules if art_modules is not None
                     else ("floor_delco_1997_05_w1000_d700.glb",)):
            write_glb(proj / "art" / "zoo" / name, [("tile", 0)],
                      [("M_Skin_concrete_delco_1997", True)])
    return proj


def _import(proj: Path) -> str:
    out = subprocess.run(
        [_godot(), "--headless", "--path", str(proj), "--import"],
        capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def _stair_line(log: str) -> str:
    lines = [ln for ln in log.splitlines()
             if ln.startswith("[worldskin] site_base.glb") and "stairs:" in ln]
    # An unrecognised shape FAILS rather than passing: a missing line means the
    # pass did not run, which is not the same as a pass that skinned nothing.
    assert len(lines) == 1, f"expected one stair line, got {lines!r}\n{log}"
    return lines[0]


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
@godot_required
def test_the_flight_takes_the_floor_family(tmp_path):
    """FAILS ON 0.91.0: `floor_` is not in `KIT_PREFIXES`, so the old pass
    never looked at a floor module, and this building owns no concrete wall."""
    proj = _project(tmp_path, base_meshes=[(FLIGHT, 0), (FLIGHT_2, 0)])
    line = _stair_line(_import(proj))
    assert "2 flight surface(s) skinned on 2 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "flight from floor_delco_1997_05_w1000_d700.glb" in line, line


@godot_required
def test_collision_and_ramp_meshes_are_not_skinned(tmp_path):
    proj = _project(tmp_path,
                    base_meshes=[(FLIGHT, 0), (COLLISION, 0), (RAMP, 0)])
    line = _stair_line(_import(proj))
    assert "1 flight surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_guard_mesh_is_counted_and_left_alone(tmp_path):
    """The themed scene fills those slots itself -- `card_shop_a01/site.tscn`
    instances brick on the sides and wood on the rails -- and in every base
    measured the guard meshes are not even instanced. One that IS instanced is
    a slot the composer did not fill, and saying so beats hiding it."""
    proj = _project(tmp_path, base_meshes=[(FLIGHT, 0), (GUARD, 1)])
    line = _stair_line(_import(proj))
    assert "1 flight surface(s) skinned on 1 mesh(es)" in line, line
    assert "1 stair_guard_* mesh(es) INSTANCED" in line, line


@godot_required
def test_a_base_with_no_flight_is_a_no_op_that_says_which(tmp_path):
    """FAILS ON 0.91.0: pharmacy_a01 and strip_retail_a02 printed `0 stair
    surface(s) skinned` -- the same sentence as card_shop_a01's real failure,
    which is how the failure stayed invisible for five days."""
    proj = _project(tmp_path, base_meshes=[("slab_0", 0)])
    line = _stair_line(_import(proj))
    assert "no flight mesh in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


# ---------------------------------------------------------------------------
# and the loud failure, which is the half that was missing
# ---------------------------------------------------------------------------
@godot_required
def test_no_art_beside_the_base_is_an_error_not_a_note(tmp_path):
    """FAILS ON 0.91.0: it printed `stairs left alone` and returned. This is
    the root `site_base.glb` of every varied-lot export."""
    proj = _project(tmp_path, base_meshes=[(FLIGHT, 0), (FLIGHT_2, 0)],
                    art=False)
    log = _import(proj)
    line = _stair_line(log)
    assert "2 mesh(es) left flat" in line, line
    assert "NO art/zoo BESIDE THE BASE" in line, line
    assert "0 flight surface(s) skinned" in line, line
    assert any("ERROR" in ln and "NO art/zoo BESIDE THE BASE" in ln
               for ln in log.splitlines()), log


@godot_required
def test_an_art_directory_with_no_family_module_is_an_error(tmp_path):
    """A pack directory that answers nothing this pass asked for. The point of
    the rule is that it cannot be satisfied by silence."""
    proj = _project(tmp_path, base_meshes=[(FLIGHT, 0)],
                    art_modules=("prop_chair_delco_1997_07_w50_d50_h90.glb",))
    log = _import(proj)
    line = _stair_line(log)
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "NO MODULE UNDER art/zoo" in ln
               for ln in log.splitlines()), log


@godot_required
def test_an_untextured_module_is_not_a_pack(tmp_path):
    """`_kit_material` requires an albedo texture. A floor module whose
    material is a flat colour is a greybox fallback, and dressing a stair in
    one would swap Deli Counter's yellow for somebody else's grey and report
    it as a success."""
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(
        WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", [(FLIGHT, 0)], [("gb_stair", False)])
    write_glb(proj / "art" / "zoo" / "floor_delco_1997_05_w1000_d700.glb",
              [("tile", 0)], [("M_Skin_concrete_delco_1997", False)])
    line = _stair_line(_import(proj))
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line


# ---------------------------------------------------------------------------
# the shape, for a machine with no Godot
# ---------------------------------------------------------------------------
def test_the_concrete_kind_lookup_is_gone_and_its_refutation_is_kept():
    """A retracted finding is cheaper to keep than to rediscover."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert "const STAIR_KIND" not in src
    assert "REFUTED" in src
    assert 'const STAIR_FLIGHT_FAMILY: Array = ["floor_"]' in src


def test_the_census_and_the_assignment_share_one_definition():
    """Two spellings of "a visual stair mesh" is the shape that hides a blind
    window either side of a threshold; there is one `_is_visual_stair`."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert src.count("func _is_visual_stair") == 1
    assert src.count("_is_visual_stair(") == 2  # the definition and one caller
