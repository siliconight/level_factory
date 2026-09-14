"""Objects draw Zoo's vertex colour, and the clutter wears its skins (0.86.0).

MEASURED on walk 9052_rain by headless readback: 0 of 1,650 imported surfaces
carrying COLOR_0 had `vertex_color_use_as_albedo` set -- every car,
container, hydrant, chair and lamp drew its material flat, and the four
dressing meshes too. Separately, the clutter build ran without `--skins`, so
pebble and rubble shipped as a flat 0.56 linear grey (2.5x the sidewalk pack's
mean albedo) and read as white lumps; and when it did get skins, the extracted
`.res` referenced the scratch project's `.ctex` cache and loaded with no
texture at all. See the 0.86.0 changelog entry.

The GDScript halves are read as text -- the unit suite has no Godot -- so they
hold the shape the measurement depends on. The Python halves run.

Run:  python -m pytest tests/unit/test_vertex_colour_and_clutter_skins.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402
from packages.core.models import MissionBrief  # noqa: E402
from packages.pipeline.batch_planner import plan_batch, shared_pixelcoat_id  # noqa: E402
from packages.pipeline.planner import LAYER_ART, plan_mission  # noqa: E402

WORLDSKIN = ROOT / "assets" / "godot" / "zoo_worldskin.gd"
EXTRACT = ROOT / "assets" / "godot" / "extract_meshes.gd"
_SEL = "m1.candidate.seed_1997"


def _func(src, name):
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name}"
    return m.group(0)


def _const_list(src, name):
    m = re.search(r"^const %s: Array = \[(.*?)\]" % name, src, re.S | re.M)
    assert m, f"no const {name}"
    return re.findall(r'"([^"]+)"', m.group(1))


# --- zoo_worldskin.gd -------------------------------------------------------

def test_every_object_glb_runs_the_vertex_colour_pass_and_no_tile_does():
    post = _func(WORLDSKIN.read_text(encoding="utf-8"), "_post_import")
    call = post.find("_vertex_colour_albedo(scene)")
    assert call != -1
    guard = post.rfind("if ", 0, call)
    assert "not is_kit" in post[guard:call] and "not _is_tiled(base)" in post[guard:call]
    # before the non-kit branch returns early for props
    assert call < post.find("if not is_kit:")


def test_the_tiled_families_are_the_kit_plus_panels_and_edge_strips():
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert _const_list(src, "TILED_PREFIXES") == ["ceiling_", "floor_", "roof_"]
    assert _const_list(src, "TILED_SUFFIXES") == ["_dressing.glb"]
    tiled = _func(src, "_is_tiled")
    assert "TILED_PREFIXES" in tiled and "TILED_SUFFIXES" in tiled


def test_the_flag_goes_on_only_for_tinted_materials_with_colours_on_every_surface():
    src = WORLDSKIN.read_text(encoding="utf-8")
    body = _func(src, "_vertex_colour_albedo")
    assert "vertex_color_use_as_albedo = true" in body
    on = body.find("vertex_color_use_as_albedo = true")
    assert body.find('"missing"') < on and body.find('"tinted"') < on
    collect = _func(src, "_collect_vertex_colour")
    assert "Mesh.ARRAY_COLOR" in collect and '"missing"] = true' in collect
    tint = _func(src, "_has_tint")
    assert "VERTEX_WHITE" in tint
    # nothing else in the script touches the flag, so the kit keeps its look
    assert src.count("vertex_color_use_as_albedo = true") == 1


# --- extract_meshes.gd ------------------------------------------------------

def test_extracted_dressing_draws_its_vertex_colour():
    src = EXTRACT.read_text(encoding="utf-8")
    one = _func(src, "_extract_one")
    assert "_has_tint(arrays)" in one and "_prepare(" in one
    prep = _func(src, "_prepare")
    assert "if tinted:" in prep and "vertex_color_use_as_albedo = true" in prep
    assert "duplicate()" in prep, "the import cache's material is not edited"
    assert "VERTEX_WHITE" in _func(src, "_has_tint")


def test_every_texture_slot_is_embedded_so_the_bundle_carries_it():
    src = EXTRACT.read_text(encoding="utf-8")
    prep = _func(src, "_prepare")
    assert "range(BaseMaterial3D.TEXTURE_MAX)" in prep
    assert "mat.set_texture(slot" in prep
    embed = _func(src, "_embed")
    assert "ImageTexture.create_from_image(" in embed
    assert "generate_mipmaps(" in embed
    one = _func(src, "_extract_one")
    assert '"vertex_colour_surfaces"' in one and '"embedded_textures"' in one
    assert "FLAG_BUNDLE_RESOURCES" in one


# --- the clutter build gets the skin library -------------------------------

def _ctx(tmp_path):
    return {"work_dir": str(tmp_path / "work"),
            "repository": str(tmp_path / "repo"),
            "python_executable": "python", "blender_executable": "blender"}


def test_habitat_mode_passes_skins_with_their_theme(tmp_path):
    spec = {"mode": "habitat", "habitat": "pebble,weed_tuft",
            "theme": "delco_1997", "seed": 7, "skins_dir": str(tmp_path / "px")}
    build = ZooAdapter().plan_commands(spec, _ctx(tmp_path))[0].arguments
    assert build[build.index("--skins") + 1] == str(tmp_path / "px")
    assert build[build.index("--theme") + 1] == "delco_1997"


def test_habitat_mode_without_skins_is_unchanged(tmp_path):
    spec = {"mode": "habitat", "habitat": "pebble", "theme": "delco", "seed": 7}
    build = ZooAdapter().plan_commands(spec, _ctx(tmp_path))[0].arguments
    assert "--skins" not in build and "--theme" not in build


def test_the_skin_library_is_in_the_clutter_fingerprint(tmp_path):
    px = tmp_path / "px" / "gravel_delco_1997"
    px.mkdir(parents=True)
    (px / "pebble_gravel.pack.json").write_text("{}", encoding="utf-8")
    base = {"mode": "habitat", "habitat": "pebble", "theme": "delco_1997"}
    a = ZooAdapter().fingerprint_inputs(base, _ctx(tmp_path))
    b = ZooAdapter().fingerprint_inputs({**base, "skins_dir": str(tmp_path / "px")},
                                        _ctx(tmp_path))
    assert "skin_hashes" in b and a != b


def test_the_clutter_build_waits_for_the_pixelcoat_build():
    brief = MissionBrief(mission_id="m1", display_name="M1",
                         archetype="urban_bank", candidate_count=3)
    plan = plan_mission(brief, seed_base=1997, layers=frozenset({LAYER_ART}),
                        selected_candidate=_SEL)
    jobs = {j.stage_id: j for j in plan.graph.jobs()}
    assert jobs["pixelcoat_build"].job_id in jobs["zoo_clutter_build"].depends_on


def test_a_batch_repoints_the_clutter_build_at_the_shared_library():
    briefs = [MissionBrief(mission_id=f"m{i}", display_name=f"M{i}",
                           archetype="bank", candidate_count=3)
              for i in (1, 2)]
    sel = {b.mission_id: f"{b.mission_id}.candidate.seed_1997" for b in briefs}
    plan = plan_batch(briefs, batch={"batch_id": "b1", "seed_base": 1997},
                      selected_by_mission=sel, target="presentation")
    plan.graph.topological_order()   # no dangling pixelcoat_build edge
    clutter = [j for j in plan.graph.jobs() if j.stage_id == "zoo_clutter_build"]
    assert len(clutter) == 2
    assert all(shared_pixelcoat_id("b1") in j.depends_on for j in clutter)
