"""Each building's compose names the spec it was built from, so its package carries its drawings (0.232.0, the
factory's roadmap 296).

Deli Counter 0.257.0's `build_package` draws a building into its package's `drawings/` when it is named the spec. The
library row reports the spec beside the build dir (`building_library.index`'s `spec`, never used to exclude), the
presentation adapter hands it to the driver (`--spec`), and the driver passes it on only where it can be answered
(`_drawing_kwargs`). Pure, on `test_fanout`'s stand-in library and the real planner, spec builder and adapter.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from packages.pipeline import building_library as bl
from test_fanout import ARCHETYPES, _brief, _compose_args, _flag, _library, _plan, _specs, _stages

ROOT = Path(__file__).resolve().parents[2]


def _with_specs(build: Path, ids) -> None:
    specs = build.parent / "specs"
    specs.mkdir(exist_ok=True)
    for aid in ids:
        (specs / (aid + ".json")).write_text(json.dumps({"name": aid}), encoding="utf-8")


def test_a_library_row_names_its_spec_where_deli_counter_has_one(tmp_path):
    build = _library(tmp_path / "build")
    _with_specs(build, ARCHETYPES[:3])
    rows = {r["id"]: r for r in bl.index(build)[0]}
    for aid in ARCHETYPES[:3]:
        assert rows[aid]["spec"] == str(tmp_path / "specs" / (aid + ".json"))
    for aid in ARCHETYPES[3:]:
        assert rows[aid]["spec"] == ""


def test_the_lot_is_drawn_from_the_same_draw_with_or_without_specs(tmp_path, monkeypatch):
    """The spec is reported, never used to exclude: the lot a seed picks is the same lot."""
    a = _specs(tmp_path / "a", _plan(_brief(_library(tmp_path / "a" / "build"))),
               _brief(_library(tmp_path / "a" / "build")), monkeypatch)
    build_b = _library(tmp_path / "b" / "build")
    _with_specs(build_b, ARCHETYPES)
    b = _specs(tmp_path / "b", _plan(_brief(build_b)), _brief(build_b), monkeypatch)
    ids = lambda specs: [[r["id"] for r in s.get("lot_archetypes") or []] for s in specs.values()]  # noqa: E731
    assert ids(a) == ids(b) and any(ids(a))


def test_each_building_s_compose_names_its_own_spec(tmp_path, monkeypatch):
    build = _library(tmp_path / "build")
    _with_specs(build, ARCHETYPES)
    brief = _brief(build)
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose = _stages(plan, "presentation_compose")[0]
    spec = specs[compose.job_id]
    args = _compose_args(spec, tmp_path)
    by_slots = {_flag(a, "--slots"): _flag(a, "--spec") for a in args}
    for row in spec["lot_archetypes"]:
        assert by_slots[row["slots"]] == str(tmp_path / "specs" / (row["id"] + ".json"))
    # the mission's own shell: the spec the Deli Counter job writes, lf_<mission>_<seed>
    seed = int(compose.candidate_id.rsplit("_", 1)[-1])
    assert spec["shell_spec"] == str(tmp_path / "repos" / "deli_counter" / "specs" /
                                     ("lf_%s_%d.json" % (brief.mission_id, seed)))
    assert _flag(args[0], "--spec") == spec["shell_spec"]


def _driver():
    path = ROOT / "assets" / "scripts" / "run_presentation_compose.py"
    s = importlib.util.spec_from_file_location("run_presentation_compose_under_test", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_the_driver_asks_for_drawings_only_where_they_can_be_answered(tmp_path):
    """A spec that is a file, and a composer that takes one: passed. A composer before Deli Counter 0.257.0, or a
    spec that is not there, or none: nothing passed, and the reason given -- a drawing is never worth a compose."""
    d = _driver()
    spec = tmp_path / "x.json"
    spec.write_text("{}", encoding="utf-8")

    def new(slots, gameplay, modules, out, *, theme, spec_path=None):
        return {}

    def old(slots, gameplay, modules, out, *, theme):
        return {}

    assert d._drawing_kwargs(new, str(spec)) == ({"spec_path": str(spec)}, "")
    kw, why = d._drawing_kwargs(old, str(spec))
    assert kw == {} and "0.257.0" in why
    kw, why = d._drawing_kwargs(new, str(tmp_path / "missing.json"))
    assert kw == {} and "no spec" in why
    assert d._drawing_kwargs(new, "") == ({}, "")


def test_an_empty_row_names_its_spec_too(tmp_path):
    """0.232.1: an Empty's row comes from `empty_rows`, not `index`, and cold run 9377 composed all 26 of its Empties
    with no spec. A row names its spec where Deli Counter has one, and an empty string where it has none."""
    build = tmp_path / "build"
    build.mkdir()
    for aid in ("gs_empty_rowhome_a", "gs_empty_rowhome_b"):
        for suf in (".glb", ".gameplay.json", ".slots.json"):
            (build / (aid + suf)).write_text("{}", encoding="utf-8")
        (build / (aid + ".validation.json")).write_text(json.dumps({"facade": True}), encoding="utf-8")
    _with_specs(build, ["gs_empty_rowhome_a"])
    rows = {r["id"]: r for r in bl.empty_rows(build)}
    assert rows["gs_empty_rowhome_a"]["spec"] == str(tmp_path / "specs" / "gs_empty_rowhome_a.json")
    assert rows["gs_empty_rowhome_b"]["spec"] == ""


def test_the_composed_roots_drawings_stay_out_with_its_scene(tmp_path):
    """0.232.1: cold run 9377's package carried the mission shell's drawings at its root, a building its varied lot
    does not stand. Where the root's scene pair stays out, its `drawings/` does too; a lot building's drawings, and
    every root file where the root ships, are left alone."""
    from packages.exporting import export as ex
    root = tmp_path / "presentation"
    (root / "drawings").mkdir(parents=True)
    (root / "lot" / "office" / "drawings").mkdir(parents=True)
    for rel in ("site.tscn", "site_base.glb", "zoo_worldskin.gd", "drawings/axonometric.svg",
                "drawings/axonometric.svg.import", "drawings/drawings.json", "lot/office/drawings/axonometric.svg"):
        (root / rel).write_text("x", encoding="utf-8")
    assert ex._root_left_out(root, False) == {"site.tscn", "site_base.glb", "drawings/axonometric.svg",
                                              "drawings/axonometric.svg.import", "drawings/drawings.json"}
    assert ex._root_left_out(root, True) == set()
