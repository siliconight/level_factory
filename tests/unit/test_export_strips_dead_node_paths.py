"""A package must not assert a binding it does not carry (roadmap 101).

The export overwrites Dispatch's `mission.tscn` with its own portable entry
-- correctly -- and Dispatch's `gameplay_anchors.json` and
`runtime_ownership_requirements.json` go on addressing anchors into the tree
that was replaced. Measured on `LF_precinct_yard_001`: 17 node paths, zero of
whose node names exist in any shipped scene. `LF_bank_block_001` (cold 8001):
46 and 12. They are the first files an integrating team opens.

The fix is the item's third shape, done reversibly: a `node` that names
nothing in the package becomes `node_dispatch`. Position and stable id -- the
pattern `interactives.json` used and the reason it survived -- are untouched.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export  # noqa: E402


def _package(tmp_path):
    (tmp_path / "mission.tscn").write_text(
        '[gd_scene format=3]\n[node name="MissionRoot" type="Node3D"]\n'
        '[node name="Ground" type="StaticBody3D" parent="."]\n',
        encoding="utf-8")
    (tmp_path / "gameplay_anchors.json").write_text(json.dumps({
        "schema": "dispatch.gameplay_anchors.v0.2",
        "anchors": [
            {"id": "deli_counter:LOBBY", "pos": [1, 2, 3],
             "node": "Functional/GameplayAnchors/Objectives/deli_counter:LOBBY"},
            {"id": "site:ground", "pos": [0, 0, 0], "node": "Ground"},
        ]}), encoding="utf-8")
    (tmp_path / "runtime_ownership_requirements.json").write_text(json.dumps({
        "requirements": [{"node": "Presentation/Lights/L1",
                          "authoritative_owner": "server"}]}),
        encoding="utf-8")
    return tmp_path


def test_a_path_that_names_nothing_is_moved_aside(tmp_path):
    """THE POINT."""
    summary = export.strip_dead_node_paths(_package(tmp_path))
    ga = json.loads((tmp_path / "gameplay_anchors.json").read_text("utf-8"))
    lobby = ga["anchors"][0]
    assert "node" not in lobby
    assert lobby["node_dispatch"] == \
        "Functional/GameplayAnchors/Objectives/deli_counter:LOBBY"
    assert summary["moved_total"] == 2


def test_a_path_whose_leaf_ships_is_kept(tmp_path):
    """`Ground` exists in the scene, so that binding is true and stays."""
    export.strip_dead_node_paths(_package(tmp_path))
    ga = json.loads((tmp_path / "gameplay_anchors.json").read_text("utf-8"))
    assert ga["anchors"][1]["node"] == "Ground"
    assert "node_dispatch" not in ga["anchors"][1]


def test_position_and_id_are_untouched(tmp_path):
    """The data was never the problem; only the binding was."""
    export.strip_dead_node_paths(_package(tmp_path))
    ga = json.loads((tmp_path / "gameplay_anchors.json").read_text("utf-8"))
    assert ga["anchors"][0]["id"] == "deli_counter:LOBBY"
    assert ga["anchors"][0]["pos"] == [1, 2, 3]


def test_the_move_is_recorded_in_the_package(tmp_path):
    """A count in a log line is gone by the time anybody asks."""
    export.strip_dead_node_paths(_package(tmp_path))
    rec = json.loads((tmp_path / "handoff_bindings.json").read_text("utf-8"))
    assert rec["moved_total"] == 2
    assert rec["files"]["gameplay_anchors.json"]["moved"] == 1
    assert rec["files"]["runtime_ownership_requirements.json"]["moved"] == 1
    assert "Presentation/Lights/L1" in \
        rec["files"]["runtime_ownership_requirements.json"]["paths"]


def test_it_is_reversible(tmp_path):
    """Nothing is deleted: the original address is one rename away, for the
    day LF's entry grows the tree that would make it true."""
    export.strip_dead_node_paths(_package(tmp_path))
    ga = json.loads((tmp_path / "gameplay_anchors.json").read_text("utf-8"))
    restored = [dict(a, node=a.pop("node_dispatch")) if "node_dispatch" in a
                else a for a in ga["anchors"]]
    assert all("node" in a for a in restored)


def test_a_package_without_the_handoff_is_untouched(tmp_path):
    """`--art` without `--gameplay` ships no Dispatch files at all, which is
    every recent cold run. Nothing to move, nothing written."""
    (tmp_path / "mission.tscn").write_text('[node name="X" type="Node3D"]\n',
                                           encoding="utf-8")
    summary = export.strip_dead_node_paths(tmp_path)
    assert summary["moved_total"] == 0
    assert not (tmp_path / "handoff_bindings.json").exists()


def test_only_the_named_dispatch_files_are_touched(tmp_path):
    """Listed by name, not pattern. `site.site.gameplay.json` carries 473
    `node` fields on cold 9005 and every one of them is true; a pattern that
    reached it would strip bindings that resolve."""
    _package(tmp_path)
    (tmp_path / "site.site.gameplay.json").write_text(json.dumps(
        {"markers": [{"node": "Nowhere/AtAll", "id": "m"}]}), encoding="utf-8")
    export.strip_dead_node_paths(tmp_path)
    site = json.loads((tmp_path / "site.site.gameplay.json").read_text("utf-8"))
    assert site["markers"][0]["node"] == "Nowhere/AtAll"
