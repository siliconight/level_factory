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
import sys
from pathlib import Path

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
