"""Heights by cause: the urban wall stands its lowest blocks across from the action and rises with distance from it
(Level Factory 0.204.0, factory roadmap 241).

The comps (the factory root's `docs/reference/URBAN_MIDRISE_COMPS.md`): "the tallest stand furthest away", the
skyline stepping up with distance. Roadmap 241 wrote the rule down -- heights by cause, taller away from the
action, never by jitter. 0.203.0 dealt the wall's blocks off a shuffled bag and their heights fell where the deal
put them: cold run 9291's seed_9104 stood 5, 7, 5, 10, 8, 6, 4, 12, 6 and 8 storeys from west to east.

MEASURED, before this file's thresholds were written (`patches/lf_heights_by_cause/` in the factory root): over
the 120 walls below, the rank correlation of a block's distance from the action with its height read -0.69 to
+0.77, median +0.03, dealt alone, and +0.58 to +0.92, median +0.82, drawn by cause.
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import write_glb  # noqa: E402

from packages.pipeline import empties, site_variation, street_line  # noqa: E402

#: The factory's six wide mid-rises as `street_line.shell_extents` reads them (x0, x1, y0, y1), 15 to 24 m wide
#: and 15 m deep, and each one's top as `street_line.shell_top` reads it off the built shells.
EXT = {"a": (-7.5, 7.5, -7.5, 7.5), "b": (-9.0, 9.0, -7.5, 7.5), "c": (-10.5, 10.5, -7.5, 7.5),
       "d": (-8.25, 8.25, -7.5, 7.5), "e": (-12.0, 12.0, -7.5, 7.5), "f": (-9.75, 9.75, -7.5, 7.5)}
TOP = {"a": 16.5, "b": 19.8, "c": 22.7, "d": 26.2, "e": 32.5, "f": 38.7}
ROWS = [{"id": k} for k in EXT]
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}
WALLS = [(seed, action) for seed in range(1, 41) for action in (0.0, -40.0, 55.0)]


def _wall(seed, action=None, heights=None, continuous=True):
    placed, _ = empties.terrace(ROWS, EXT, site_variation.stream(seed), [THROUGH], 180.0,
                                continuous=continuous, action=action, heights=heights)
    return placed


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):                       # ties share their mean rank
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0
        i = j + 1
    return ranks


def _rho(xs, ys):
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return cov / ((sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5)


def test_the_wall_rises_with_distance_from_the_action():
    rhos = []
    for seed, action in WALLS:
        placed = _wall(seed, action, TOP)
        rho = _rho([abs(p["at"][0] - action) for p in placed], [TOP[p["archetype"]] for p in placed])
        assert rho >= 0.5, (seed, action, [(round(p["at"][0], 1), p["archetype"]) for p in placed])
        rhos.append(rho)
    assert statistics.median(rhos) >= 0.75, statistics.median(rhos)


def test_every_design_still_stands_and_no_two_neighbours_are_alike():
    for seed, action in WALLS:
        placed = _wall(seed, action, TOP)
        assert {p["archetype"] for p in placed} == set(EXT), (seed, action)
        for a, b in zip(placed, placed[1:]):
            touching = abs((a["at"][0] + a["size_x"] / 2.0) - (b["at"][0] - b["size_x"] / 2.0)) < 1e-6
            assert not (touching and a["archetype"] == b["archetype"]), (seed, action, a, b)


def test_the_strip_and_an_urban_wall_without_both_are_dealt_as_before():
    for seed in range(1, 41):
        assert _wall(seed, 0.0, TOP, continuous=False) == _wall(seed, continuous=False)
        assert _wall(seed, None, TOP) == _wall(seed) == _wall(seed, 0.0, None)


def test_shell_top_reads_the_hulls(tmp_path):
    """glTF metres (x, height, z): two walls 3.1 m tall and a parapet to 3.6 m."""
    hulls = [("ext_col_0_S_seg0-convcolonly", (0.0, 1.55, 6.0), (6.0, 3.1, 0.3)),
             ("ext_col_0_N_seg0-convcolonly", (0.0, 1.55, -6.0), (6.0, 3.1, 0.3)),
             ("parapet_S-convcolonly", (0.0, 3.35, 6.0), (6.0, 0.5, 0.3))]
    assert abs(street_line.shell_top(write_glb(tmp_path / "block.glb", hulls)) - 3.6) < 1e-6
