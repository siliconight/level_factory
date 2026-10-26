"""A door's hardware keeps its own UVs on a kit module (0.242.0).

Zoo 1.127.0 paints a door's knob and plate (`<root>_LeafHardware`) the stoop
railing's black iron so that on a front the two are one material and one mesh.
They were not: the knob arrives in a `doorway_` kit module, which `_apply`
world-projects, and the railing in a `prop_`, which it leaves alone, and the
Empties' per-side merge keys on `uv1_scale` and both triplanar flags -- cold
run 9392's `blocker_0` carried the iron twice on its street side (the
factory's `docs/cold_runs/cold_9392/meshes_blocker0_9392.out.txt`). A mesh
named for one of `AUTHORED_UV_PARTS` is never projected, and the report
counts it.

These run the real script through a real Godot import over a generated
module, as `test_worldskin_lit_faces.py` does. Skipped where no Godot is
installed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_import_fixture import write_glb  # noqa: E402
from tests.siblings import sibling_repo  # noqa: E402

WORLDSKIN = ROOT / "assets" / "godot" / "zoo_worldskin.gd"

_PROJECT = """\
config_version=5

[application]
config/name="worldskin hardware fixture"

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
    _godot() is None, reason="no Godot binary; this test imports a real module")

MODULE = "doorway_delco_1997_01_w100_mbrick_orange_enavy_o1d20e5.glb"


def _import(tmp_path: Path, meshes, materials) -> str:
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / MODULE, meshes, materials, spread_uv=True)
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--import"],
                         capture_output=True, text=True, timeout=300)
    log = out.stdout + out.stderr
    lines = [ln for ln in log.splitlines()
             if ln.startswith(f"[worldskin] {MODULE}") and "world-projected" in ln]
    # an unrecognised shape FAILS: a missing line means the pass did not run
    assert len(lines) == 1, f"expected one report line, got {lines!r}\n{log}"
    return lines[0]


def _counts(line: str) -> tuple:
    projected = int(re.search(r"(\d+) material\(s\) world-projected", line).group(1))
    m = re.search(r"(\d+) hardware part\(s\) left on their own UVs", line)
    assert m, f"no hardware count in the report: {line}"
    return projected, int(m.group(1))


@godot_required
def test_the_knob_keeps_its_uvs_and_the_leaf_is_still_projected(tmp_path):
    """FAILS ON 0.241.0: both world-projected, and no hardware count."""
    line = _import(tmp_path, [("Doorway_Leaf", 0), ("Doorway_LeafHardware", 1)],
                   [("M_Skin_wood_panel_delco_1997", True), ("M_Skin_metal_painted_delco_1997_0f0f11", True)])
    assert _counts(line) == (1, 1), line


@godot_required
def test_a_doorway_with_no_hardware_is_projected_as_before(tmp_path):
    """The control: a leaf alone is world-projected exactly as it was."""
    line = _import(tmp_path, [("Doorway_Leaf", 0)], [("M_Skin_wood_panel_delco_1997", True)])
    assert _counts(line) == (1, 0), line


def test_the_part_is_zoo_s_knob():
    """One name, two readers: the node Zoo builds a door's hardware as is the
    one this leaves on its UVs. Renamed on one side and not the other, the knob
    is projected again and the front is two meshes of one iron."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const AUTHORED_UV_PARTS: Array = ["_LeafHardware"]' in src
    arch = "zoo_keeper/recipes/_arch.py"
    zoo = sibling_repo("zoo", marker=arch)
    if zoo is not None:
        assert 'f"{root}_LeafHardware"' in (zoo / arch).read_text(encoding="utf-8")
