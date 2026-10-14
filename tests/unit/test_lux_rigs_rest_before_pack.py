"""Every animated Lux rig is at rest when the applied scene is packed (Level Factory 0.208.0, factory roadmap 247).

A failing or flickering fixture and a cycling stage light animate from their own clocks on every frame
`run_lux_apply.gd` awaits, and `pack()` saved whatever they had reached: across cold runs 9295 to 9300 eleven
lights' `light_energy` in `lux.applied.tscn` differed in every pair of runs (the factory's
docs/findings/roofprops_bytes/lux_energy_pairs.py). Lux 0.77.0's rigs answer `rest()`.

A SOURCE-SHAPE TEST, as `test_lux_preset_readback.py` is and for its reason: unit CI has no headless Godot. The
Godot proof is Lux's `tools/rig_rest_selftest.gd` and a cold run. What this holds is the order -- every rig rested
after the last frame the script awaits and before `pack()` -- and the guard, `has_method`, so a Lux without
`rest()` still packs.

FAILS ON 0.207.0, which rests nothing.

Run:  python -m pytest tests/unit/test_lux_rigs_rest_before_pack.py
"""
from pathlib import Path

import pytest

DRIVER = Path(__file__).resolve().parents[2] / "assets" / "godot" / "run_lux_apply.gd"


@pytest.fixture(scope="module")
def src() -> str:
    assert DRIVER.is_file(), f"driver missing at {DRIVER}"
    return DRIVER.read_text(encoding="utf-8")


def test_every_rig_rests_after_the_last_awaited_frame_and_before_the_pack(src):
    pack = src.index("applied.pack(scene)")
    rest = src.index('rig_node.call("rest")')
    last_await = src.rindex("await process_frame", 0, pack)
    assert last_await < rest < pack


def test_the_rest_goes_through_has_method_so_an_older_lux_still_packs(src):
    rest = src.index('rig_node.call("rest")')
    guard = src.rindex('if rig_node.has_method("rest"):', 0, rest)
    loop = src.rindex('for rig_node in get_nodes_in_group(&"lux_light_rig"):', 0, guard)
    assert loop < guard < rest


def test_the_job_log_says_how_many_rested(src):
    assert '"[lux] %d rig(s) at rest before the scene is packed" % rested' in src
