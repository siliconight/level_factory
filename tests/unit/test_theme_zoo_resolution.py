"""The pre-flight's Zoo answer matches Zoo's own (roadmap 128's sibling).

`themes.zoo_style_for` MIRRORS `zoo_keeper/core/dna.py::theme_style`, because
Level Factory reads tool checkouts and does not run them. A mirrored rule is a
number typed twice, and this repo has spent a session finding out what those
cost -- so the mirror is pinned to the original over the shipped species
corpus, and this test fails when they disagree.

WHY IT EXISTS AT ALL. Zoo 0.57.0 taught its theme path the fallback its prompt
path always had, taking `delco_1997` from 0 of 56 species to 56 of 56 without
a single new style authored for it. `themes.py` went on counting raw style
KEYS, so cold run 9004's pre-flight reported "no species carry a 'delco_1997'
style (56 scanned) -- the kit falls back to flat colour" about a kit that
resolves it everywhere. Under-reporting a closed gap is how one gets closed
twice.

    python -m pytest tests/unit/test_theme_zoo_resolution.py -q
"""
import json
import sys

import pytest

from packages.tools import themes
from tests.siblings import not_found, sibling_repo

# A SEARCH, not a count of parents. `parents[3]` holds the sibling checkouts
# from a checkout and is `scratchpad` from a worktree, where every test below
# skipped (0.94.0). The species directory is the marker because that is what
# these read; a `zoo/` with something else in it is not this zoo.
_SPECIES_REL = "zoo_keeper/genome/species"
_ZOO = sibling_repo("zoo", marker=_SPECIES_REL)
_SPECIES = (_ZOO / _SPECIES_REL) if _ZOO else None

#: Names worth asking of both. The first is the one that caused this; the rest
#: cover each branch of the rule and the cases that must NOT resolve.
_THEMES = ["delco_1997", "delco", "1990s", "rockay", "center_city",
           "industrial_flats", "delco_2020", "rockay_1997", "nonesuch",
           "nonesuch_1997", "", "_1997", "delco_99"]


def _zoo_theme_style():
    """Zoo's own implementation, or a skip when the checkout is not beside us."""
    if _SPECIES is None:
        pytest.skip(not_found("zoo", marker=_SPECIES_REL))
    if str(_ZOO) not in sys.path:
        sys.path.insert(0, str(_ZOO))
    try:
        from zoo_keeper.core.dna import theme_style
    except ImportError as exc:                       # pragma: no cover
        pytest.skip(f"zoo's dna module not importable: {exc}")
    return theme_style


def _genomes():
    out = []
    for path in sorted(_SPECIES.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def test_the_mirror_agrees_with_zoo_on_every_species_and_theme():
    """THE GUARD. Not the delco_1997 answer -- the rule, over the whole corpus,
    so a change to either side that the other does not follow is a red test
    rather than a silently wrong pre-flight."""
    theme_style = _zoo_theme_style()
    genomes = _genomes()
    assert len(genomes) >= 50, len(genomes)
    disagreements = []
    for genome in genomes:
        styles = genome.get("styles") or {}
        counts = {name: 1 for name in styles}
        for theme in _THEMES:
            theirs = theme_style(genome, theme)
            mine = themes.zoo_style_for(theme, counts)
            if (theirs[0] if theirs else None) != mine:
                disagreements.append(
                    (genome.get("species"), theme,
                     theirs[0] if theirs else None, mine))
    assert disagreements == [], disagreements[:8]


def test_the_corpus_actually_exercises_the_fallback():
    """A comparison where both sides always answer None proves nothing."""
    theme_style = _zoo_theme_style()
    genomes = _genomes()
    fell_back = 0
    for genome in genomes:
        styles = genome.get("styles") or {}
        if "delco_1997" in styles:
            continue
        got = theme_style(genome, "delco_1997")
        if got is not None and got[0] != "delco_1997":
            fell_back += 1
    assert fell_back >= 50, fell_back


def test_the_preflight_counts_resolution_not_spelling():
    """The reading that was wrong: 0 species carry the name, 56 resolve it."""
    if _SPECIES is None:
        pytest.skip(not_found("zoo", marker=_SPECIES_REL))
    zoo = themes.resolve("delco_1997", {"zoo": str(_ZOO)})["zoo"]
    assert zoo["species_with_style"] == 0, "no species spells delco_1997"
    assert zoo["species_with_resolved_style"] == zoo["species_scanned"] > 0


def test_a_theme_nothing_answers_still_reports_zero():
    if _SPECIES is None:
        pytest.skip(not_found("zoo", marker=_SPECIES_REL))
    zoo = themes.resolve("nonesuch", {"zoo": str(_ZOO)})["zoo"]
    assert zoo["species_with_resolved_style"] == 0
    lines = " ".join(themes.summary_lines(themes.resolve(
        "nonesuch", {"zoo": str(_ZOO)})))
    assert "no species resolve" in lines and "flat colour" in lines
