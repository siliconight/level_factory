"""A layout that cannot express itself at this building count must say so.

FOUND BY A SWEEP, not by reading the code. Three briefs identical but for
`site_shape`, at one seed base so the building selection was constant, two
candidates each so the experiment carried its own control:

    row vs L           0.2052 / 0.1773   of the site diagonal
    row vs courtyard   0.2052 / 0.1773   the same numbers
    L vs courtyard     0.0000 / 0.0000
    between seeds      0.0710 - 0.0735   (the control)

`courtyard` produced a plan IDENTICAL to `L`. Not because the parameter is
inert -- against a row both sit 2.4-2.9x the control -- but because the brief
asked for three buildings. A courtyard's walk turns three times and three
buildings afford two steps, so the third direction never appears and the walk
IS an L's. `_steps` returns the same list for both at 2 and 3, and they
diverge at 4.

THE DEFECT IS NOT THE DEGENERACY. It is unavoidable: you cannot walk three
sides of a square with two steps. The defect was that nothing said so --
`shape_of` reported `courtyard`, the geometry was an L, and the spec recorded
the first. That is the same wrong-but-plausible record this module already
fixed once for unknown spellings (roadmap 100), so it is answered the same
way: report which, and let the build continue.
"""
import pytest

from packages.pipeline import site_variation as sv


def test_courtyard_and_L_are_the_same_walk_at_three_buildings():
    """The measurement the sweep took, as an assertion. If this ever fails,
    `_steps` has changed and the sweep's numbers no longer describe it."""
    assert sv._steps("courtyard", 3) == sv._steps("L", 3)
    assert sv._steps("courtyard", 2) == sv._steps("L", 2)


def test_they_diverge_once_there_are_enough_buildings_to_turn_three_times():
    assert sv._steps("courtyard", 4) != sv._steps("L", 4)
    assert sv._steps("courtyard", 5) != sv._steps("L", 5)


@pytest.mark.parametrize("shape,count,expected", [
    ("courtyard", 2, False), ("courtyard", 3, False),
    ("courtyard", 4, True), ("courtyard", 9, True),
    ("L", 2, False), ("L", 3, True), ("L", 6, True),
    # a row turns zero times, so it is expressible at any count including one
    ("row", 1, True), ("row", 2, True),
])
def test_shape_expressible(shape, count, expected):
    assert sv.shape_expressible(shape, count) is expected


@pytest.mark.parametrize("shape,count,expected", [
    ("courtyard", 3, "L"),      # two steps: along, across -- an L
    ("courtyard", 2, "row"),    # one step: no turn at all
    ("L", 2, "row"),
    ("courtyard", 4, None),
    ("L", 3, None),
    ("row", 5, None),
])
def test_degenerates_to_names_the_shape_you_actually_get(shape, count, expected):
    assert sv.degenerates_to(shape, count) == expected


def test_it_compares_against_the_walk_rather_than_a_turn_count():
    """`_TURNS` orders the shapes; it does not decide the answer. The answer
    comes from `_steps`, the function the builder actually uses -- so a change
    to a walk is caught here instead of silently disagreeing with a table."""
    for n in range(1, 8):
        for shape in sv.SHAPES:
            simpler = sv.degenerates_to(shape, n)
            if simpler is not None:
                assert sv._steps(shape, n) == sv._steps(simpler, n), (
                    "%s at %d claims to degenerate to %s, but their walks "
                    "differ" % (shape, n, simpler))


def test_a_row_never_degenerates():
    """It turns zero times, so there is nothing simpler for it to become. If
    this fails, `_TURNS` has gained an entry below row and the vocabulary has
    a shape nobody declared."""
    for n in range(1, 10):
        assert sv.degenerates_to("row", n) is None
        assert sv.shape_expressible("row", n) is True
