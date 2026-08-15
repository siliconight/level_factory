"""art-unlit: the art pass without the render. Roadmap 47, stage 2.

These build real packages from fabricated job directories and read back what
landed. They prove WHICH FILES a mode copies and what the manifest then
claims -- not that Godot opens the result, which is stage 3.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.export import (  # noqa: E402
    EXPORT_MANIFEST_NAME, MODE_ART_UNLIT, MODE_PORTABLE, MODE_PURE_SHELL,
    UNLIT_MODES, ExportProfile, export_mission, ships_lux,
)
from packages.pipeline.planner import (  # noqa: E402
    LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT,
)

ALL_THREE = frozenset({LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT})


# ------------------------------------------------------------- the predicate

def test_art_unlit_ships_no_lux():
    assert not ships_lux(MODE_ART_UNLIT)


def test_pure_shell_ships_no_lux():
    assert not ships_lux(MODE_PURE_SHELL)


def test_portable_godot_does():
    assert ships_lux(MODE_PORTABLE)


def test_the_unlit_set_is_exactly_those_two():
    assert UNLIT_MODES == frozenset({MODE_PURE_SHELL, MODE_ART_UNLIT})


# ----------------------------------------------------------------- a package

def _mission(root):
    """A locked mission's job directories, with one file of each kind."""
    handoff = root / "handoff"
    handoff.mkdir(parents=True)
    (handoff / "mission_manifest.json").write_text("{}")
    (handoff / "site.tscn").write_text("[gd_scene]\n")
    # The handoff carries copies of Lux's outputs; the skip set is what keeps
    # them out of an unlit package.
    (handoff / "lux.applied.tscn").write_text("[gd_scene]\n")
    (handoff / "lux.quality.json").write_text("{}")

    lux = root / "lux_out"
    lux.mkdir(parents=True)
    (lux / "lux.applied.tscn").write_text("[gd_scene]\n")
    (lux / "lux.quality.json").write_text("{}")

    composed = root / "composed"
    composed.mkdir(parents=True)
    (composed / "wall.glb").write_bytes(b"glTF")
    (composed / "themed.material.tres").write_text("[gd_resource]\n")
    return handoff, lux, composed


def _export(root, mode, *, layers=ALL_THREE):
    """Build a package. Returns (result, export_dir).

    `export_mission` names its own directory from `export_build_dir_name`, so
    the caller passes an out_root and reads back where it landed rather than
    predicting the name.
    """
    handoff, lux, composed = _mission(root / mode)
    result = export_mission(
        mission_id="m1", out_root=root / mode / "exports",
        profile=ExportProfile(mode=mode),
        handoff_dir=handoff, presentation_dir=lux, composed_root=composed,
        source_dir=None, tool_versions={}, layers=layers,
    )
    return result, result.export_dir


def _files(out):
    return {p.name for p in out.rglob("*") if p.is_file()}


def _manifest(out):
    return json.loads((out / EXPORT_MANIFEST_NAME).read_text())


def test_art_unlit_keeps_the_art(tmp_path):
    """THE POINT. Everything Zoo/Pixelcoat/Patina built is still here."""
    _, out = _export(tmp_path, MODE_ART_UNLIT)
    names = _files(out)
    assert "wall.glb" in names
    assert "themed.material.tres" in names


def test_art_unlit_drops_the_render(tmp_path):
    _, out = _export(tmp_path, MODE_ART_UNLIT)
    names = _files(out)
    assert "lux.applied.tscn" not in names
    assert "lux.quality.json" not in names
    assert not (out / "presentation").exists()


def test_portable_godot_still_ships_both(tmp_path):
    """The mode that did not change, asserted so it cannot drift."""
    _, out = _export(tmp_path, MODE_PORTABLE)
    names = _files(out)
    assert "wall.glb" in names
    assert "lux.applied.tscn" in names


def test_pure_shell_drops_both(tmp_path):
    """art-unlit sits BETWEEN the two, and this is the far end."""
    _, out = _export(tmp_path, MODE_PURE_SHELL)
    names = _files(out)
    assert "lux.applied.tscn" not in names
    assert "wall.glb" not in names


# ------------------------------------------------------------- the manifest

def test_the_manifest_does_not_claim_the_dropped_layer(tmp_path):
    """0.34.0's failure with the sign reversed.

    The run produced the light layer, so `cmd_export` passes it in. The
    PACKAGE has no Lux output in it, and the manifest describes the package.
    """
    _, out = _export(tmp_path, MODE_ART_UNLIT)
    got = _manifest(out)["layers"]
    assert LAYER_LIGHT not in got
    assert LAYER_ART in got
    assert LAYER_GAMEPLAY in got


def test_a_lit_export_still_claims_it(tmp_path):
    _, out = _export(tmp_path, MODE_PORTABLE)
    assert LAYER_LIGHT in _manifest(out)["layers"]


def test_the_manifest_names_the_mode(tmp_path):
    _, out = _export(tmp_path, MODE_ART_UNLIT)
    assert _manifest(out)["profile"] == "art-unlit"


def test_the_archive_name_distinguishes_the_two_packages(tmp_path):
    """The A/B this mode exists for: two archives from ONE build, told apart
    by name rather than by the recipient remembering which is which."""
    lit, _ = _export(tmp_path, MODE_PORTABLE)
    unlit, _ = _export(tmp_path, MODE_ART_UNLIT)
    assert lit.archive_name != unlit.archive_name
    assert unlit.archive_name.endswith("_art-unlit.zip")
    assert lit.archive_name.endswith("_portable-godot.zip")


def test_both_packages_use_the_same_interior_folder(tmp_path):
    """So a recipient can swap one for the other without every res:// path in
    their project moving."""
    lit, _ = _export(tmp_path, MODE_PORTABLE)
    unlit, _ = _export(tmp_path, MODE_ART_UNLIT)
    assert lit.package_dir_name == unlit.package_dir_name


# ---------------------------------------------------------------- the entry

def test_the_unlit_entry_instances_the_themed_site(tmp_path):
    """write_entry_scene needed no change; its docstring did.

    No presentation/ means the elif fires and the entry names site.tscn --
    which after themed_site_assemble is the THEMED site, not the graybox.
    """
    _, out = _export(tmp_path, MODE_ART_UNLIT)
    entry = (out / "mission.tscn").read_text()
    assert "site.tscn" in entry
    assert "lux.applied.tscn" not in entry
