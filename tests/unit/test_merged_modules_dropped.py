"""The kit modules only merged slots instanced, out of the package (0.210.0, factory roadmap 249).

`merge_empties` folds an Empty's sided slots into `lot/<id>/merged/` and removes the slot children that instanced
`lot/<id>/art/zoo/*.glb`; the modules stayed, and the light bake imported every one for a lightmap. Measured on
cold run 9304's package: 286 module GLBs in its Empties named by no scene, 315 of the bake's 632 model imports.
`drop_merged_modules` removes, from each Empty the merge report merged, the modules no file of the package names.

Built on a package folder written here, so every case is exact. FAILS ON 0.209.0: there is no
`drop_merged_modules`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import merge_empties as M  # noqa: E402


def _write(root: Path, rel: str, text: str = "x") -> Path:
    """Bytes as given: a text-mode write turns each newline into two on Windows, and a size is asserted below."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))
    return p


def _module(root: Path, lot: str, name: str, cache: bool = True) -> None:
    _write(root, "lot/%s/art/zoo/%s" % (lot, name), "glb " * 100)
    _write(root, "lot/%s/art/zoo/%s.import" % (lot, name),
           '[remap]\nimporter="scene"\n[deps]\nsource_file="res://lot/%s/art/zoo/%s"\n' % (lot, name))
    if cache:
        _write(root, "lot/%s/art/zoo/%s.unwrap_cache" % (lot, name), "u" * 50)


def _package(root: Path) -> dict:
    """Two merged Empties and one Empty the merge did not take, as an export leaves them after the merge."""
    for lot in ("gs_a", "gs_b", "gs_c"):
        for name in ("wall_x.glb", "window_y.glb"):
            _module(root, lot, name)
    _module(root, "gs_a", "prop_awning.glb", cache=False)        # instanced by its scene: kept
    _module(root, "gs_a", "window_named_by_script.glb")           # named by a script: kept
    _module(root, "gs_b", "wall_named_elsewhere.glb")             # named by another lot's scene: kept
    _write(root, "lot/gs_a/art/zoo/_tex/brick_albedo.png", "png")
    _write(root, "lot/gs_a/site.tscn",
           '[ext_resource type="ArrayMesh" path="res://lot/gs_a/merged/S_0.res" id="1"]\n'
           '[ext_resource type="PackedScene" path="res://lot/gs_a/art/zoo/prop_awning.glb" id="2"]\n')
    _write(root, "lot/gs_b/site.tscn", '[ext_resource type="ArrayMesh" path="res://lot/gs_b/merged/N_0.res" id="1"]\n')
    _write(root, "lot/deli/site.tscn",
           '[ext_resource type="PackedScene" path="res://lot/gs_b/art/zoo/wall_named_elsewhere.glb" id="1"]\n')
    _write(root, "lot/gs_a/zoo_worldskin.gd", 'const KEEP := "window_named_by_script.glb"\n')
    _write(root, "cover/prop_cruiser.glb", "glb")                 # outside every art/zoo: never touched
    _write(root, "cover/prop_cruiser.glb.import", "[remap]\n")
    # the package's own lists of its files name everything, and load nothing
    _write(root, "light_bake.json", '{"imports": {"baked": ["lot/gs_a/art/zoo/wall_x.glb"]}}')
    _write(root, "portable_resource_manifest.json", '{"files": ["lot/gs_b/art/zoo/window_y.glb"]}')
    # the import cache is not the package
    _write(root, ".godot/imported/scan.tscn", 'path="res://lot/gs_a/art/zoo/window_y.glb"')
    return {"schema": M.SCHEMA, "ok": True, "error": None, "scenes": [
        {"scene": "res://lot/gs_a/site.tscn", "meshes_in": 9, "surfaces_in": 9, "merged": 2, "unwrapped": 2,
         "colliders": 3, "error": None},
        {"scene": "res://lot/gs_b/site.tscn", "meshes_in": 9, "surfaces_in": 9, "merged": 2, "unwrapped": 2,
         "colliders": 3, "error": None},
    ]}


def test_a_merged_empty_s_unnamed_modules_go_with_their_sidecars(tmp_path):
    report = _package(tmp_path)
    got = M.drop_merged_modules(tmp_path, report)
    assert sorted(got["dropped"]) == ["lot/gs_a/art/zoo/wall_x.glb", "lot/gs_a/art/zoo/window_y.glb",
                                      "lot/gs_b/art/zoo/wall_x.glb", "lot/gs_b/art/zoo/window_y.glb"]
    for rel in got["dropped"]:
        for suffix in ("", ".import", ".unwrap_cache"):
            assert not (tmp_path / (rel + suffix)).exists(), rel + suffix
    assert got["bytes"] == 4 * (400 + 50) + sum(
        len(('[remap]\nimporter="scene"\n[deps]\nsource_file="res://%s"\n' % r).encode()) for r in got["dropped"])
    assert got["kept"] == 3


def test_what_a_file_names_stays(tmp_path):
    M.drop_merged_modules(tmp_path, _package(tmp_path))
    for rel in ("lot/gs_a/art/zoo/prop_awning.glb", "lot/gs_a/art/zoo/window_named_by_script.glb",
                "lot/gs_b/art/zoo/wall_named_elsewhere.glb", "lot/gs_a/art/zoo/_tex/brick_albedo.png",
                "cover/prop_cruiser.glb"):
        assert (tmp_path / rel).is_file(), rel


def test_an_empty_the_merge_did_not_take_keeps_every_module(tmp_path):
    M.drop_merged_modules(tmp_path, _package(tmp_path))
    for name in ("wall_x.glb", "window_y.glb"):
        assert (tmp_path / "lot/gs_c/art/zoo" / name).is_file(), name


def test_a_failed_row_or_no_merge_drops_nothing(tmp_path):
    report = _package(tmp_path)
    report["scenes"][0]["error"] = "no side to merge"
    report["scenes"][1]["merged"] = 0
    assert M.drop_merged_modules(tmp_path, report) == {"dropped": [], "bytes": 0, "kept": 0}
    assert M.drop_merged_modules(tmp_path, {"schema": M.SCHEMA, "ok": True, "scenes": []})["dropped"] == []


def test_the_export_drops_them_after_the_merge_and_before_the_bake():
    src = (Path(M.__file__).resolve().parent / "export.py").read_text(encoding="utf-8")
    mrg = src.index("_merge_empties(export_dir, godot_executable)")
    drop = src.index("drop_merged_modules(export_dir, mreport)")
    bake = src.index("_bake_lights(export_dir, godot_executable")
    assert mrg < drop < bake
