"""The price probe counts the scene as it is when it counts (0.144.3).

`perf_stations.gd` walked the scene once, at load, and read that list after
seventy frames of rendering. county_hospital_001's warm-up frees its own nodes
in that time; `is` on a freed instance is a script error, the probe's
coroutine died, and it idled until its 600 s watchdog with nothing measured --
twice, on cold run 9173's package, while the level ran 300 frames in 2.8 s.

The probe cannot run here (no Godot in the suite), so this pins the order in
its source: the tree is walked again after the last frame the probe waits on
and before the mesh count and the light census read it.

Run:  python -m pytest tests/unit/test_perf_rewalk.py -q
"""
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "tools" / "perf_stations.gd"


def test_the_tree_is_walked_again_between_the_last_wait_and_the_count():
    src = PROBE.read_text(encoding="utf-8")
    last_wait = src.index("var drew := false")       # the draw-call check
    count = src.index("var n_mesh: int = 0")
    census = src.index("_light_census(nodes, cap)")
    between = src[last_wait:count]
    assert "_walk(scene, nodes)" in between, (
        "the mesh count reads the list walked at load, after frames in which "
        "a level can free its own nodes")
    assert last_wait < count < census
    # and no frame passes between the fresh walk and the census that reads it
    assert "await" not in src[count:census]
