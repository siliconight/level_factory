"""A theme that does not resolve is caught BEFORE the graybox leg runs.

Roadmap item 72. `cold_7002` put three candidates through Deli Counter in
Blender, then Lot, Laser Tag and walktest -- tens of minutes -- and then
`pixelcoat_build` exited 1 in two seconds on a missing
`profiles/themes/delco_1997.json`. `doctor` passed. `plan` printed a
twelve-job DAG without mentioning the theme.

The missing profile is a content gap. The absence of the check was the defect,
and these tests pin the check rather than the content.
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.pixelcoat import PixelcoatAdapter  # noqa: E402
from packages.tools import themes  # noqa: E402


def _factory(tmp_path, installed=("delco", "rockay"), styles=("default", "delco")):
    pc = tmp_path / "pixelcoat" / "profiles" / "themes"
    pc.mkdir(parents=True)
    for t in installed:
        (pc / f"{t}.json").write_text("{}", encoding="utf-8")
    sp = tmp_path / "zoo" / "zoo_keeper" / "genome" / "species"
    sp.mkdir(parents=True)
    for i in range(4):
        (sp / f"sp{i}.json").write_text(
            json.dumps({"species": f"sp{i}", "styles": {s: {} for s in styles}}),
            encoding="utf-8")
    return {"pixelcoat": str(tmp_path / "pixelcoat"), "zoo": str(tmp_path / "zoo")}


def test_the_cold_7002_theme_does_not_resolve(tmp_path):
    res = themes.resolve("delco_1997", _factory(tmp_path))
    assert res["ok"] is False
    assert res["pixelcoat"]["path"].endswith("delco_1997.json")


def test_the_theme_that_fixed_it_does(tmp_path):
    assert themes.resolve("delco", _factory(tmp_path))["ok"] is True


def test_the_report_names_the_path_and_what_is_installed(tmp_path):
    lines = themes.summary_lines(themes.resolve("delco_1997", _factory(tmp_path)))
    joined = " ".join(lines)
    assert "NO PIXELCOAT PROFILE" in joined
    assert "delco_1997.json" in joined
    assert "delco, rockay" in joined, "a reader needs to see delco next to delco_1997"


def test_partial_zoo_coverage_is_a_fraction_not_a_boolean(tmp_path):
    """`3 of 48 species` and `48 of 48` are different answers.

    The verb moved from CARRY to RESOLVE when Zoo 0.57.0 taught its theme path
    a fallback: a species reaches `delco_1997` through the `delco` or `1990s`
    style it already has, so counting the ones that spell the name reported a
    closed gap as open. The fraction is the point either way.
    """
    repos = _factory(tmp_path, styles=("default", "delco"))
    sp = Path(repos["zoo"]) / "zoo_keeper" / "genome" / "species"
    (sp / "sp0.json").write_text(
        json.dumps({"species": "sp0", "styles": {"default": {}, "delco": {},
                                                 "rockay": {}}}), encoding="utf-8")
    counts, scanned = themes.zoo_styles(repos["zoo"])
    assert (counts["delco"], counts["rockay"], scanned) == (4, 1, 4)
    assert "1 of 4 species resolve 'rockay'" in " ".join(
        themes.summary_lines(themes.resolve("rockay", repos)))


def test_an_unparseable_species_is_skipped_not_guessed(tmp_path):
    repos = _factory(tmp_path)
    (Path(repos["zoo"]) / "zoo_keeper" / "genome" / "species" / "bad.json").write_text(
        "{ not json", encoding="utf-8")
    _counts, scanned = themes.zoo_styles(repos["zoo"])
    assert scanned == 4


def test_unconfigured_repositories_do_not_claim_a_verdict(tmp_path):
    res = themes.resolve("delco", {})
    assert res["ok"] is False
    assert "cannot check" in " ".join(themes.summary_lines(res))


def test_the_adapter_refuses_a_theme_with_no_profile(tmp_path):
    """Defence in depth: if a run reaches dispatch anyway, the failure is an
    input-validation error naming the file, not a bare `exit=1` from the tool."""
    repos = _factory(tmp_path)
    problems = PixelcoatAdapter().validate_configuration(
        {"theme": "delco_1997"}, {"repository": repos["pixelcoat"]})
    assert len(problems) == 1
    assert "delco_1997" in problems[0] and "installed: delco, rockay" in problems[0]


def test_the_adapter_still_accepts_a_theme_that_exists(tmp_path):
    repos = _factory(tmp_path)
    assert PixelcoatAdapter().validate_configuration(
        {"theme": "delco"}, {"repository": repos["pixelcoat"]}) == []


def test_the_adapter_does_not_invent_a_verdict_without_a_repository(tmp_path):
    """No repository means the question cannot be asked, which is not the same
    as answering no."""
    assert PixelcoatAdapter().validate_configuration({"theme": "anything"}, {}) == []


# --------------------------------------------------------------------------- #
# ...and a theme that DOES resolve, whose shells ask for a kind it cannot skin
# --------------------------------------------------------------------------- #
#
# Cold run 9061. Pixelcoat 0.44.0 shipped `wood_panel_delco` and
# `slatwall_retail` and mapped them in a new `card_shop` theme only. The
# mission ran on `delco_1997`, whose profile was present and correct -- so the
# check above passed, every gate passed, and the package shipped with
# `lot/card_shop_a01/site.tscn` instancing 21 modules whose stems end
# `_mwood_panel` or `_mslatwall` and not one of them textured. Measured in the
# shipped walk copy: of the 11 kinds its GLBs carry, those two are the only
# ones whose kind-named material has no `baseColorTexture`.
#
# Roadmap 72 asked "does the theme exist". This asks "can it dress what is
# being built", which is the question the run was actually relying on.

_DELCO_1997_0_44_0 = {
    # the 37 kinds `profiles/themes/delco_1997.json` mapped at Pixelcoat
    # 0.44.0, verbatim -- the file this pre-flight would have read on the day
    # 9061 ran. wood_panel and slatwall are absent, which is the defect.
    "asphalt", "brick", "canvas", "carbon", "carpet", "carpet_club",
    "ceiling_tile", "cloth", "concrete", "dirt", "drywall", "foliage",
    "glass", "glass_facade", "gravel", "laminate", "leather", "metal",
    "metal_bare", "metal_painted", "paint_block", "paper", "plaster",
    "plastic", "road_paint", "rubber", "shingle", "sidewalk", "siding",
    "stone", "tar", "tile", "vegetation", "velvet", "wallpaper_club",
    "wood", "wood_stained",
}

#: What `card_shop_a01.slots.json` asks for, counted off the real manifest in
#: `deli_counter/build`: 189 slots, 16 distinct kinds, 19 slots `wood_panel`
#: and 2 `slatwall`. Those 21 are exactly the `_mwood_panel` / `_mslatwall`
#: modules 9061's scene instanced, so the manifest and the scene agree.
_CARD_SHOP_KINDS = [
    "brick", "glass_facade", "wood_panel", "drywall", "tile", "ceiling_tile",
    "concrete", "plaster", "carpet", "metal", "wood", "plastic", "leather",
    "slatwall", "metal_painted", "cloth",
]


def _pixelcoat_with(tmp_path, theme: str, kinds) -> str:
    d = tmp_path / "pixelcoat" / "profiles" / "themes"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{theme}.json").write_text(
        json.dumps({"theme": theme,
                    "materials": {k: f"{k}_grammar" for k in sorted(kinds)}}),
        encoding="utf-8")
    return str(tmp_path / "pixelcoat")


def _shell(tmp_path, shell_id: str, kinds) -> tuple[str, str]:
    """A `<id>.slots.json` of the shape Deli Counter actually writes."""
    lib = tmp_path / "dcbuild"
    lib.mkdir(parents=True, exist_ok=True)
    path = lib / f"{shell_id}.slots.json"
    path.write_text(json.dumps({
        "slot_manifest_version": 1, "building_id": shell_id,
        "theme": "greybox", "module_library": "art/zoo",
        "slots": [{"slot_id": f"s{i}", "role": "wall", "material": k}
                  for i, k in enumerate(kinds)]}), encoding="utf-8")
    return shell_id, str(path)


def test_the_9061_package_is_refused_before_it_is_built(tmp_path):
    """RED against Level Factory 0.91.0's delco_1997, which is the point.

    Both kinds are named, and the shell that asks for them is named, because a
    refusal that says only "something did not resolve" sends the reader back
    to the tree to find out what.
    """
    repo = _pixelcoat_with(tmp_path, "delco_1997", _DELCO_1997_0_44_0)
    res = themes.resolve("delco_1997", {"pixelcoat": repo},
                         shells=[_shell(tmp_path, "card_shop_a01",
                                        _CARD_SHOP_KINDS)])
    assert res["pixelcoat"]["ok"] is True, "the profile exists; that was never the gap"
    assert res["ok"] is False
    assert sorted(res["kinds"]["missing"]) == ["slatwall", "wood_panel"]
    joined = " ".join(themes.summary_lines(res))
    assert "NO 'wood_panel' PACK in theme 'delco_1997'" in joined
    assert "NO 'slatwall' PACK" in joined
    assert "card_shop_a01" in joined


def test_the_same_shell_passes_once_the_theme_maps_the_two_kinds(tmp_path):
    repo = _pixelcoat_with(tmp_path, "delco_1997",
                           _DELCO_1997_0_44_0 | {"wood_panel", "slatwall"})
    res = themes.resolve("delco_1997", {"pixelcoat": repo},
                         shells=[_shell(tmp_path, "card_shop_a01",
                                        _CARD_SHOP_KINDS)])
    assert res["ok"] is True
    assert res["kinds"]["checked"] is True and res["kinds"]["missing"] == {}
    assert "all 16 asked for by 1 shell(s) resolve" in " ".join(
        themes.summary_lines(res))


def test_a_shell_that_asks_for_nothing_recognisable_fails_rather_than_passes(tmp_path):
    """A checker that cannot find the field it wants has learned nothing.

    A manifest with no `slots` list used to be indistinguishable from a shell
    whose every kind resolved -- `or []` and an empty loop -- which is the
    exact shape that printed "closure verdict clean" over 21 unresolved
    resources.
    """
    repo = _pixelcoat_with(tmp_path, "delco_1997", _DELCO_1997_0_44_0)
    lib = tmp_path / "dcbuild"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "weird_a01.slots.json").write_text(
        json.dumps({"slot_manifest_version": 9, "building_id": "weird_a01",
                    "surfaces": []}), encoding="utf-8")
    good = _shell(tmp_path, "ok_a01", ["brick", "wood"])
    res = themes.resolve("delco_1997", {"pixelcoat": repo},
                         shells=[good, ("weird_a01",
                                        str(lib / "weird_a01.slots.json"))])
    assert res["ok"] is False
    assert any("no 'slots' list" in u for u in res["kinds"]["unreadable"])
    assert "UNREADABLE SHELL" in " ".join(themes.summary_lines(res))


def test_a_missing_manifest_is_reported_and_not_skipped(tmp_path):
    repo = _pixelcoat_with(tmp_path, "delco_1997", _DELCO_1997_0_44_0)
    res = themes.resolve("delco_1997", {"pixelcoat": repo},
                         shells=[("gone_a01", str(tmp_path / "gone.slots.json")),
                                 _shell(tmp_path, "ok_a01", ["brick"])])
    assert res["ok"] is False
    assert res["kinds"]["unreadable"] and "gone_a01" in res["kinds"]["unreadable"][0]


def test_no_shells_means_the_question_was_not_asked_not_that_it_passed(tmp_path):
    """The single-shell path: Deli Counter builds that shell during the run,
    so at pre-flight there is no manifest. `checked` says so out loud, and the
    report says `not checked` rather than claiming coverage."""
    repo = _pixelcoat_with(tmp_path, "delco_1997", _DELCO_1997_0_44_0)
    res = themes.resolve("delco_1997", {"pixelcoat": repo})
    assert res["ok"] is True
    assert res["kinds"]["checked"] is False
    assert "not checked" in " ".join(themes.summary_lines(res))


def _dc_build():
    """The nearest `deli_counter/build` at or above this file, or None.

    The same search 0.91.0 gave `test_dc_preset_registry`, for the same reason:
    a single `parents[N]` is correct for a checkout beside Deli Counter and
    silently wrong for the WORKTREE this work is done in, and the test that
    skipped there was the one holding the gate.
    """
    env = os.environ.get("LF_DC_ROOT")
    roots = [Path(env), Path(env) / "deli_counter"] if env else []
    roots += [p / "deli_counter" for p in Path(__file__).resolve().parents]
    for r in roots:
        if (r / "build").is_dir():
            return r / "build"
    return None


def test_the_wiring_hands_the_preflight_the_shells_the_run_will_place():
    """The derivation is only worth anything if something calls it.

    `_shells_for_theme_check` is the only path from a brief to the manifests
    `kind_coverage` reads, and a pre-flight wired to nothing is a check that
    cannot fail. Asserted against the real library and cold run 9061's own
    brief: `card_shop` anchored, 3 buildings, and `card_shop_a01` in the draw
    with a `.slots.json` that exists.
    """
    build = _dc_build()
    if build is None:
        pytest.skip("Deli Counter build library not found above %s "
                    "(set LF_DC_ROOT)" % Path(__file__).resolve().parent)
    import apps.cli.commands as cmds
    from packages.core.models import MissionBrief
    brief = MissionBrief(mission_id="card_block_001", display_name="c",
                         archetype="card_shop", building_count=3,
                         theme="delco_1997", candidate_count=3,
                         lot_library=str(build))
    plan = SimpleNamespace(candidate_ids=["card_block_001_9061"])
    shells = cmds._shells_for_theme_check(brief, plan)
    assert shells, "the pre-flight was handed no shells for a 3-building brief"
    ids = [s[0] for s in shells]
    assert "card_shop_a01" in ids, ids
    for _aid, path in shells:
        assert Path(path).is_file(), path
    kinds, unreadable = themes.shell_kinds(shells)
    assert not unreadable, unreadable
    assert "wood_panel" in kinds and "card_shop_a01" in kinds["wood_panel"]


def test_no_plan_means_no_shells_rather_than_the_whole_library():
    import apps.cli.commands as cmds
    from packages.core.models import MissionBrief
    brief = MissionBrief(mission_id="m", display_name="m", archetype="bank",
                         building_count=3, theme="delco_1997",
                         candidate_count=1, lot_library=None)
    assert cmds._shells_for_theme_check(brief, None) == []
    assert cmds._shells_for_theme_check(
        brief, SimpleNamespace(candidate_ids=["m_1"])) == []


def test_an_unparseable_theme_profile_does_not_read_as_a_theme_with_no_kinds(tmp_path):
    """None and set() are different answers. If a broken profile returned an
    empty kind set, EVERY kind would report missing and the reader would go
    looking for 16 grammars instead of one bad JSON file."""
    d = tmp_path / "pixelcoat" / "profiles" / "themes"
    d.mkdir(parents=True)
    (d / "delco_1997.json").write_text("{ not json", encoding="utf-8")
    assert themes.theme_kinds(str(tmp_path / "pixelcoat"), "delco_1997") is None
    cov = themes.kind_coverage(str(tmp_path / "pixelcoat"), "delco_1997",
                               [_shell(tmp_path, "ok_a01", ["brick"])])
    assert cov["checked"] is False and cov["missing"] == {}
