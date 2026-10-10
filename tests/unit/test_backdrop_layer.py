"""The backdrop beyond the plate's edge, shipped (0.174.0, roadmap 228 step E): the drawn
site's `backdrop` list and the site kit's modules become `<site>_backdrop.tscn`, one MultiMesh
a module a side, which the entry scene instances beside the level."""
import json
import math
from pathlib import Path

from packages.exporting import backdrop_layer
from packages.exporting.dressing_scene import check_manifest, orders_by_asset
from packages.exporting.localize import LocalizeReport, write_entry_scene
from tests.unit.glb_fixture import stub_glb


def _drawn(kit_dir, n_per_side=3, with_kit=True):
    pieces = []
    sides = {"N": (0.0, 60.0, 0.0), "S": (0.0, -60.0, 180.0), "E": (110.0, 0.0, 270.0), "W": (-110.0, 0.0, 90.0)}
    dims = ([6.0, 10.0, 9.5], [5.5, 10.0, 8.0])
    for side, (x, y, yaw) in sides.items():
        for k in range(n_per_side):
            w, d, h = dims[k % 2]
            pieces.append({"name": f"Backdrop_{side}_0_{k}", "species": "backdrop_rowhome",
                           "at": [x + 8.0 * k, y], "yaw": yaw, "dims": [w, d, h],
                           "side": side, "band": 0, "source": "site_backdrop"})
    pieces.append({"name": "Backdrop_Tower", "species": "water_tower", "at": [-40.0, 140.0],
                   "yaw": 0.0, "dims": [14.0, 14.0, 40.0], "side": "N", "band": -1,
                   "source": "site_backdrop"})
    spec = {"name": "site", "backdrop": pieces}
    if with_kit:
        spec["cover_modules"] = {"dir": str(kit_dir), "theme": "delco_1997", "style": 1}
    return spec


STEMS = ("prop_backdrop_rowhome_delco_1997_01_w600_d1000_h950",
         "prop_backdrop_rowhome_delco_1997_01_w550_d1000_h800",
         "prop_water_tower_delco_1997_01_w1400_d1400_h4000")


def _kit(tmp_path, stems=STEMS):
    kit = tmp_path / "kit"
    kit.mkdir(exist_ok=True)
    for s in stems:
        # a real minimal GLB: the extraction copies each with its dependencies,
        # which means reading it
        stub_glb(kit / f"{s}.glb", s)
    return kit


def test_the_module_stem_is_spelt_as_lot_and_zoo_spell_it():
    assert backdrop_layer.module_stem("chain_link_fence", [14.9, 0.0603, 1.83], "delco_1997") \
        == "prop_chain_link_fence_delco_1997_01_w1490_d6_h183"
    assert backdrop_layer.module_stem("water_tower", [14, 14, 40], "delco", 2) \
        == "prop_water_tower_delco_02_w1400_d1400_h4000"


def test_the_manifest_is_one_order_a_piece_a_module_a_side_with_no_collision(tmp_path):
    man = backdrop_layer.manifest_from_drawn(_drawn(_kit(tmp_path)))
    assert check_manifest(man) == []
    assert len(man["orders"]) == 13
    grouped = orders_by_asset(man)
    # two rowhome modules on four sides, and the tower on its one
    assert len(grouped) == 2 * 4 + 1
    assert all(o["collision_policy"] == "none" for o in man["orders"])
    north = [o for o in man["orders"] if o["side"] == "N" and o["species"] == "backdrop_rowhome"]
    assert north[0]["asset_id"].endswith("__N") and north[0]["module"] == STEMS[0]
    # a Zoo module stands on -h/2, so the order's position is its centre
    assert north[0]["pos"] == [0.0, 60.0, 9.5 / 2]
    west = next(o for o in man["orders"] if o["side"] == "W")
    assert abs(west["yaw"] - math.radians(90.0)) < 1e-12
    assert man["kit_dir"] == str(tmp_path / "kit") and man["site_id"] == "site"


def test_a_spec_with_no_kit_or_no_backdrop_orders_nothing(tmp_path):
    assert backdrop_layer.manifest_from_drawn(_drawn(_kit(tmp_path), with_kit=False))["orders"] == []
    assert backdrop_layer.manifest_from_drawn({"name": "site"})["orders"] == []


def test_without_godot_the_layer_is_reported_not_shipped(tmp_path):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    drawn = tmp_path / "site.site.drawn.json"
    drawn.write_text(json.dumps(_drawn(_kit(tmp_path))), encoding="utf-8")
    report = backdrop_layer.ship_backdrop(export_dir, drawn, None, scratch_root=tmp_path)
    assert report["shipped"] is False
    assert any("godot" in r for r in report["reasons"]), report
    assert not list(export_dir.glob("*_backdrop.tscn"))
    written = json.loads((export_dir / "backdrop_layer.json").read_text(encoding="utf-8"))
    assert written["shipped"] is False and "extraction" not in written


def test_a_missing_module_in_the_kit_is_said_and_nothing_ships(tmp_path):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    kit = _kit(tmp_path, STEMS[:2])          # no tower built
    drawn = tmp_path / "site.site.drawn.json"
    drawn.write_text(json.dumps(_drawn(kit)), encoding="utf-8")
    report = backdrop_layer.ship_backdrop(export_dir, drawn, "godot", scratch_root=tmp_path)
    assert report["shipped"] is False
    assert report["missing_modules"] == [STEMS[2]]
    assert any("no built GLB" in r for r in report["reasons"])


def test_a_missing_drawn_spec_is_said_in_the_package(tmp_path):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    report = backdrop_layer.ship_backdrop(export_dir, None, None)
    assert report["shipped"] is False
    assert (export_dir / "backdrop_layer.json").is_file()


def test_with_the_meshes_extracted_the_scene_is_a_multimesh_a_module_a_side(tmp_path, monkeypatch):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    kit = _kit(tmp_path)
    drawn = tmp_path / "site.site.drawn.json"
    drawn.write_text(json.dumps(_drawn(kit)), encoding="utf-8")

    def fake_extract(glbs, scratch, godot):
        scratch = Path(scratch)
        (scratch / "dressing").mkdir(parents=True, exist_ok=True)
        out = {"extracted": {}, "failed": {}}
        for stem in glbs:
            (scratch / "dressing" / f"{stem}.res").write_bytes(b"RSRC")
            out["extracted"][stem] = {"path": f"res://dressing/{stem}.res", "surfaces": 1,
                                      "vertices": 24, "parts": 1}
        return out

    monkeypatch.setattr(backdrop_layer, "extract_meshes", fake_extract)
    report = backdrop_layer.ship_backdrop(export_dir, drawn, "godot", scratch_root=tmp_path)
    assert report["shipped"] is True, report
    assert report["scene"] == "site_backdrop.tscn"
    assert report["instances"] == 13 and report["modules"] == sorted(STEMS)
    # nine MultiMeshes: two modules on four sides and the tower on one
    assert report["meshes"] == 9 and report["draw_calls"] == 9
    assert report["by_side"] == {"N": 3, "S": 3, "E": 3, "W": 3} and report["towers"] == 1
    text = (export_dir / "site_backdrop.tscn").read_text(encoding="utf-8")
    assert text.count("MultiMeshInstance3D") == 9
    assert sorted(p.name for p in (export_dir / "backdrop").iterdir()) == [f"{s}.res" for s in sorted(STEMS)]
    # the four sides of a module share one extracted mesh
    paths = {a: p for a, p in report["mesh_paths"].items() if STEMS[0] in a}
    assert len(paths) == 4 and len(set(paths.values())) == 1
    assert set(paths.values()) == {f"res://backdrop/{STEMS[0]}.res"}
    written = json.loads((export_dir / "backdrop_layer.json").read_text(encoding="utf-8"))
    assert written["shipped"] is True and "res://" not in json.dumps(written.get("extracted"))
    assert not (tmp_path / "pkg.backdrop_extract").exists()


def test_the_entry_scene_instances_the_backdrop_beside_the_level(tmp_path):
    (tmp_path / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (tmp_path / "site_backdrop.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    report = LocalizeReport()
    write_entry_scene(tmp_path, report)
    assert report.entry_instances == ["site.tscn", "site_backdrop.tscn"]
    assert "res://site_backdrop.tscn" in (tmp_path / "mission.tscn").read_text(encoding="utf-8")
