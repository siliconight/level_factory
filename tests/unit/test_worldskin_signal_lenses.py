"""A signal lights one lens at a time, every head in step (0.165.0).

The walker, 2026-10-09, walking club_block_014 (roadmap 219, note 9): "stop
lights are only bright for 1 color at a time, and if you have 2 here, they
need to be the same". Zoo's `traffic_signal` lights all three lenses and
leaves which one is lit to whoever runs the level; this import gives each
lens material a clock.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the SHAPE: Zoo's names, a cycle the windows tile with one lens
lit at every instant, one clock for every signal, a lit shader that keeps the
lightmap, and an unknown colour left alone and said. What the shader DOES is
measured in frames; see the 0.165.0 changelog.

Run:  python -m pytest tests/unit/test_worldskin_signal_lenses.py
"""
import re
from pathlib import Path

import pytest

from tests.siblings import sibling_repo

SCRIPT = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "zoo_worldskin.gd")


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def _shader(src: str) -> str:
    m = re.search(r'const SIGNAL_LENS_SHADER: String = """(.*?)"""', src, re.S)
    assert m, "no SIGNAL_LENS_SHADER block"
    return m.group(1)


def _windows(src: str) -> dict:
    """``{colour: (from_s, to_s)}`` off the GDScript's own table; a table this
    cannot read is a failure, not an empty answer."""
    m = re.search(r"^const SIGNAL_WINDOWS_S: Dictionary = \{(.*)\}$", src, re.M)
    assert m, "no SIGNAL_WINDOWS_S table"
    got = {c: (float(a), float(b)) for c, a, b in
           re.findall(r'"(\w+)": \[([\d.]+), ([\d.]+)\]', m.group(1))}
    assert got, m.group(0)
    return got


def _cycle(src: str) -> float:
    m = re.search(r"^const SIGNAL_CYCLE_S: float = ([\d.]+)$", src, re.M)
    assert m, "no SIGNAL_CYCLE_S"
    return float(m.group(1))


def test_the_pass_runs_for_every_glb_before_the_kit_branch():
    """A signal arrives in a street piece's GLB, which is not a kit tile."""
    post = _func(_src(), "_post_import")
    at = post.find("_signal_lenses(scene")
    assert at != -1
    assert at < post.find("is_kit") < post.find("return scene")


def test_the_names_are_zoo_s_when_zoo_is_beside_this_repo():
    src = _src()
    assert 'const SIGNAL_LENS_PREFIX: String = "M_TrafficSignal_Lens_"' in src
    zoo = sibling_repo("zoo", marker="zoo_keeper/recipes/traffic_signal.py")
    if zoo is None:
        pytest.skip("no Zoo with a traffic signal beside this repo")
    their = (zoo / "zoo_keeper" / "recipes" / "traffic_signal.py").read_text(encoding="utf-8")
    assert 'f"M_TrafficSignal_Lens_{name}"' in their
    m = re.search(r'for name, color, lens in zip\(\(([^)]*)\)', their)
    assert m, "the recipe's lens loop is not where this reads it"
    colours = set(re.findall(r'"(\w+)"', m.group(1)))
    assert colours == set(_windows(src)), (colours, sorted(_windows(src)))


def test_one_lens_is_lit_at_every_instant_of_the_cycle():
    """The windows tile [0, cycle) with no gap and no overlap, and a shared
    boundary is one number in both -- so the shader's step() lights exactly
    one lens at every t."""
    src = _src()
    cycle, wins = _cycle(src), _windows(src)
    edges = sorted(wins.values())
    assert edges[0][0] == 0.0 and edges[-1][1] == cycle, (edges, cycle)
    for (_a0, b0), (a1, _b1) in zip(edges, edges[1:]):
        assert b0 == a1, edges
    for t in [k * 0.25 for k in range(int(cycle * 4))]:
        lit = [c for c, (a, b) in wins.items() if a <= t < b]
        assert len(lit) == 1, (t, lit)


def test_the_amber_is_a_yellow_change_interval():
    """MUTCD's yellow change interval is 3 to 6 seconds."""
    a, b = _windows(_src())["Amber"]
    assert 3.0 <= b - a <= 6.0, (a, b)


def test_every_signal_keeps_one_clock():
    """No per-node term: every head at a junction faces the through road and
    must show the same lens; the shutters' and turning parts' hash is the
    opposite of what a signal needs."""
    sh = _shader(_src())
    assert "NODE_POSITION_WORLD" not in sh and "hash" not in sh
    assert "mod(TIME, cycle_s)" in sh


def test_the_lens_is_lit_glass_and_keeps_its_bake():
    """Not unshaded: the lightmap and the street's light reach the glass, and
    the lamp is gated by the window. The clock is in the material, so the
    model carries no second UV set and keeps its bake."""
    sh = _shader(_src())
    assert "unshaded" not in sh
    assert "ALBEDO = glass.rgb;" in sh
    assert "EMISSION = lamp.rgb * energy * on;" in sh
    assert "UV2" not in sh


def test_a_lens_it_cannot_read_is_left_alone_and_said():
    fn = _func(_src(), "_signal_lenses")
    assert fn.count("push_warning(") == 2 and fn.count("continue") >= 4
    mat = _func(_src(), "_signal_lens_material")
    assert "bm.emission_energy_multiplier" in mat and "SIGNAL_GLASS" in mat
