"""A ladder is rusted outside and clean inside, and keeps its contrast.

THE WALKER'S CALL, 2026-09-23, with two reference photographs: outdoor ladders
rusted, indoor ladders clean (`docs/SET_DRESSING_REFERENCES.md`).

WHY THIS IS NOT JUST "PUT METAL ON IT". `gb_ladder` is (1.00, 0.90, 0.55) --
luminance 0.897, the BRIGHTEST value on the site -- and its own comment in
`deli_counter.GREYBOX_PALETTE` says why: a ladder "is the smallest thing that
has to be found". Skinning one spends that signal. So the pass moves it rather
than spending it: rails take the darkest metal the building owns and rungs the
lightest, which is reference 2's actual read (matte near-black frame, bright
galvanised treads) on geometry Deli Counter already emits as separate meshes.

THE SOURCE IS `prop_`, MEASURED. On cold run 9070's package only 1 of 3
buildings owned metal in a kit family, while all 3 owned it in `prop_` (27, 21
and 41 modules). Selecting from a kit family would have repeated the
`STAIR_KIND = "concrete"` mistake this repo already records as REFUTED.

These run the real script through a real Godot import, for the reason
`test_worldskin_stairs.py` gives.

Skipped where no Godot is installed. `LF_GODOT` overrides, then `DC_GODOT`,
then `LOT_GODOT`, then the usual Windows install path, then PATH.

Run:  python -m pytest tests/unit/test_worldskin_ladders.py
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

#: The names Deli Counter emits (`deli_counter.py:2032`), with the `ext` mark
#: it writes from `Ladder.placement_mode`. `ladder<n>_plane-convcolonly` is the
#: climb-face collider; Godot's `-colonly` convention deletes its visual, so it
#: can never reach the pass -- the `col` test in `_is_visual_ladder` is a
#: second line over a convention the engine already enforces.
RAIL = "ladder0_rail_0_-1"
RUNG = "ladder0_rung_0_0"
EXT_RAIL = "ladder0ext_rail_0_-1"
EXT_RUNG = "ladder0ext_rung_0_0"
COLLIDER = "ladder0_plane-colonly"

#: Three real materials off cold run 9070's package, with their measured
#: baseColorFactors. The rusted skin's factor is (1, 1, 1) because its colour
#: lives entirely in `metal_rusted_street_albedo` -- which is exactly why it is
#: chosen by NAME and excluded from the darkest/lightest ranking.
DARK = ("M_Skin_metal_painted_delco_1997_040404", True, [0.015, 0.015, 0.016])
LIGHT = ("M_Skin_metal_bare_delco_1997_c7c9cc", True, [0.78, 0.79, 0.80])
RUST = ("M_Skin_metal_delco_1997", True, [1.0, 1.0, 1.0])
#: luminance 0.2126r + 0.7152g + 0.0722b -- 0.015 and 0.789
#: The luminance the pass PRINTS, which is of `albedo_color` as Godot 4.7's
#: glTF importer reports it: sRGB. The fixture writes the glTF's LINEAR
#: `baseColorFactor` (0.015..0.80), and the importer hands back its sRGB
#: encoding, so the dark rail reads 0.129, not 0.015. STAGED 2026-09-23 with
#: the linear figures, and this test failed on that and nothing else when it
#: was first run (2026-10-04): the rail and rung it picked were the right
#: ones, because the encoding preserves order. `LADDER_TINTLESS` (0.95) still
#: separates as written -- the brightest tinted metal, 0.789 linear, reads
#: about 0.90 -- so the pass needed no change.
DARK_LUM = "0.129"
LIGHT_LUM = "0.901"

_PROJECT = """\
config_version=5

[application]
config/name="worldskin ladder fixture"

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


def _project(tmp_path: Path, *, base_meshes, art=True, metals=None) -> Path:
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(
        WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", base_meshes, [("gb_ladder", False)])
    if art:
        mats = list(metals if metals is not None else (DARK, LIGHT, RUST))
        # A floor module too, so the slab and stair passes in the same import
        # find their own family and their log lines stay quiet.
        write_glb(proj / "art" / "zoo" / "floor_delco_1997_05_w1000_d700.glb",
                  [("tile", 0)], [("M_Skin_concrete_delco_1997", True)])
        write_glb(proj / "art" / "zoo" / "prop_bench_delco_1997_01_w180.glb",
                  [("part_%d" % i, i) for i in range(len(mats))], mats)
    return proj


def _import(proj: Path) -> str:
    out = subprocess.run(
        [_godot(), "--headless", "--path", str(proj), "--import"],
        capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def _ladder_line(log: str) -> str:
    lines = [ln for ln in log.splitlines()
             if ln.startswith("[worldskin] site_base.glb") and "ladders:" in ln]
    # An unrecognised shape FAILS rather than passing.
    assert len(lines) == 1, f"expected one ladder line, got {lines!r}\n{log}"
    return lines[0]


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
@godot_required
def test_the_rail_takes_the_darkest_metal_and_the_rung_the_lightest(tmp_path):
    """Reference 2's read, on geometry that already exists. FAILS BEFORE THIS
    PASS: nothing looked at a ladder, so both shipped in the greybox yellow."""
    proj = _project(tmp_path, base_meshes=[(RAIL, 0), (RUNG, 0)])
    line = _ladder_line(_import(proj))
    assert "2 surface(s) skinned on 2 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "rail %s (%s)" % (DARK[0], DARK_LUM) in line, line
    assert "rung %s (%s)" % (LIGHT[0], LIGHT_LUM) in line, line


@godot_required
def test_an_exterior_ladder_takes_the_rust(tmp_path):
    """`ladder<n>ext_*` -- the mark Deli Counter writes from placement_mode.
    The COUNT is asserted, not the note: a sentence would print either way."""
    proj = _project(tmp_path, base_meshes=[(EXT_RAIL, 0), (EXT_RUNG, 0)])
    line = _ladder_line(_import(proj))
    assert "(2 exterior)" in line, line
    assert "exterior %s" % RUST[0] in line, line


@godot_required
def test_interior_and_exterior_ladders_in_one_base_are_told_apart(tmp_path):
    proj = _project(tmp_path,
                    base_meshes=[(RAIL, 0), (RUNG, 0), (EXT_RAIL, 0)])
    line = _ladder_line(_import(proj))
    assert "3 surface(s) skinned on 3 mesh(es)" in line, line
    assert "(1 exterior)" in line, line


@godot_required
def test_the_climb_face_collider_is_not_skinned(tmp_path):
    proj = _project(tmp_path, base_meshes=[(RAIL, 0), (COLLIDER, 0)])
    line = _ladder_line(_import(proj))
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_base_with_no_ladder_is_a_no_op_that_says_which(tmp_path):
    proj = _project(tmp_path, base_meshes=[("slab_0_t0_0", 0)])
    line = _ladder_line(_import(proj))
    assert "no visual ladder in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


# ---------------------------------------------------------------------------
# and the loud failures
# ---------------------------------------------------------------------------
@godot_required
def test_no_art_beside_the_base_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(RAIL, 0)], art=False)
    log = _import(proj)
    line = _ladder_line(log)
    assert "NO art/zoo BESIDE THE BASE" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "NO art/zoo BESIDE THE BASE" in ln
               for ln in log.splitlines()), log


@godot_required
def test_one_tinted_metal_is_a_ladder_with_no_contrast_and_refuses(tmp_path):
    """A uniformly metal ladder is WORSE than the yellow it replaces: the
    yellow at least reads. Refusing beats reporting that as a success."""
    proj = _project(tmp_path, base_meshes=[(RAIL, 0), (RUNG, 0)],
                    metals=[("M_Skin_metal_bare_delco_1997_808080", True,
                             [0.5, 0.5, 0.5])])
    log = _import(proj)
    line = _ladder_line(log)
    assert "TINTED METAL" in line, line
    assert "2 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "TINTED METAL" in ln
               for ln in log.splitlines()), log


@godot_required
def test_a_building_with_no_rusted_skin_says_so_rather_than_pretending(tmp_path):
    """The rusted street steel is not in every building's packs. The exterior
    then falls back to the interior pair, and the note has to say which."""
    proj = _project(tmp_path, base_meshes=[(EXT_RAIL, 0), (EXT_RUNG, 0)],
                    metals=[DARK, LIGHT])
    line = _ladder_line(_import(proj))
    assert "(0 exterior)" in line, line
    assert "exterior ladders take the interior pair" in line, line
    assert "2 surface(s) skinned on 2 mesh(es)" in line, line


# ---------------------------------------------------------------------------
# the shape, for a machine with no Godot
# ---------------------------------------------------------------------------
def test_the_source_family_is_props_and_the_refutation_is_recorded():
    """Keep the refutation: selecting a ladder's metal from a KIT family would
    have refused on two buildings in three."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const LADDER_METAL_FAMILY: Array = ["prop_"]' in src
    assert "STAIR_KIND" in src
    assert "1 of 3 buildings owns metal in a kit family" in src


def test_the_yellow_it_replaces_is_recorded_as_a_signal_being_moved():
    """The palette bought that brightness deliberately. A reader who does not
    know it will 'tidy' the rung to match the rail."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert "BRIGHTEST value on the site" in src
    assert "MOVED RATHER THAN SPENT" in src
