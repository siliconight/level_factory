"""The Laser Tag map contract, checked before 900 seconds are spent (TDD 8, 24.3).

Laser Tag discovers spawns, enemies and the objective by node name. Absent them,
`validate_map()` fails, `run_evaluation` returns before a single firefight, and
the report reads `runs: 0, grade: "BROKEN"` — which the pipeline printed as a
readiness grade for months. Lot now emits the nodes itself; this module is the
staging-time net for a scene that arrives without them, plus the pre-flight check
that refuses the job early rather than spending the timeout to learn nothing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.staging.lt_hooks import (  # noqa: E402
    HOOK_ENEMY_SPAWNS, HOOK_OBJECTIVE, HOOK_PLAYER_SPAWN, REQUIRED_HOOKS,
    check_scene_hooks, cover_positions, enemy_positions, inject_lt_hooks,
    read_root_positions, scene_hooks)

WALK = '''[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://site.tscn" id="site"]

[node name="site_walk" type="Node3D"]
script = ExtResource("walk")
spawn_pos = Vector3(10, 1, -4)
objective_pos = Vector3(40, 0, -30)
extraction_pos = Vector3(-5, 0, -50)
site_title = "SITE"

[node name="Nav" type="NavigationRegion3D" parent="."]

[node name="Site" parent="./Nav" instance=ExtResource("site")]
'''


def test_root_positions_are_read_from_the_root_node_only():
    pos = read_root_positions(WALK)
    assert pos["spawn_pos"] == (10.0, 1.0, -4.0)
    assert pos["objective_pos"] == (40.0, 0.0, -30.0)
    assert pos["extraction_pos"] == (-5.0, 0.0, -50.0)


def test_a_vector3_further_down_the_file_cannot_move_the_spawn():
    """A child node's own `spawn_pos` belongs to that child. Reading the whole
    document would let an unrelated property relocate the player."""
    text = WALK + '\n[node name="Decoy" type="Node3D" parent="."]\nspawn_pos = Vector3(999, 999, 999)\n'
    assert read_root_positions(text)["spawn_pos"] == (10.0, 1.0, -4.0)


def test_a_scene_without_hooks_is_refused_before_the_run():
    bare = '[gd_scene format=3]\n\n[node name="x" type="Node3D"]\n'
    problems = check_scene_hooks(bare)
    assert problems and "BROKEN" in problems[0]


def test_a_scene_the_hooks_can_be_derived_from_passes_preflight():
    """Lot's walk scene carries the positions but not the nodes; staging fills
    them in, so this is a pass, not a failure."""
    assert check_scene_hooks(WALK) == []


def test_a_scene_that_already_declares_the_hooks_passes_and_is_untouched():
    staged, _ = inject_lt_hooks(WALK)
    assert check_scene_hooks(staged) == []
    again, report = inject_lt_hooks(staged)
    assert again == staged
    assert "already declares" in report["reason"]


def test_injection_satisfies_every_required_hook():
    out, report = inject_lt_hooks(WALK, enemy_count=6)
    assert set(REQUIRED_HOOKS) <= scene_hooks(out)
    assert report["enemy_count"] == 6
    assert HOOK_PLAYER_SPAWN in report["injected"]
    # the player spawn lands where the scene said the crew starts
    block = out[out.index(f'name="{HOOK_PLAYER_SPAWN}"'):]
    assert "10.0, 1.0, -4.0" in block.split("\n")[1]


def test_injected_nodes_precede_connection_sections():
    """Godot's .tscn grammar puts every node before the first [connection];
    appending at EOF produces a file the engine will not parse."""
    text = WALK + '\n[connection signal="pressed" from="Nav" to="." method="_x"]\n'
    out, _ = inject_lt_hooks(text)
    assert out.index(f'name="{HOOK_OBJECTIVE}"') < out.index("[connection ")


def test_enemies_are_spread_along_the_route_not_stacked():
    """Six enemies on one point is one encounter. The evaluation is only worth
    reading if the firefight is distributed along the player's actual path."""
    route = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 0.0, -40.0)]
    pts = enemy_positions(route, 6)
    assert len(pts) == 6
    assert len({(round(p[0], 1), round(p[2], 1)) for p in pts}) == 6
    # ...and inside the route's bounding box, not off in space
    assert all(-2.0 <= p[0] <= 32.0 for p in pts)


def test_enemy_sides_alternate_across_the_route_centre_line():
    route = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    pts = enemy_positions(route, 4, lateral=1.5)
    zs = [round(p[2], 3) for p in pts]
    assert all(abs(abs(z) - 1.5) < 1e-6 for z in zs)
    assert zs[0] == -zs[1]  # no two consecutive enemies share a side


def test_a_degenerate_route_still_produces_the_requested_count():
    """Spawn == objective is a bad level, but it must not crash staging."""
    pts = enemy_positions([(5.0, 0.0, 5.0), (5.0, 0.0, 5.0)], 3)
    assert len(pts) == 3


def test_cover_points_ring_the_objective():
    pts = cover_positions((10.0, 2.0, -10.0), radius=5.0)
    assert len(pts) == 4
    assert all(abs(p[1] - 2.0) < 1e-6 for p in pts)
    assert (15.0, 2.0, -10.0) in pts and (10.0, 2.0, -5.0) in pts


def test_a_missing_objective_is_reported_as_derived_never_as_real():
    """A fallback the report does not name is a fabricated fact."""
    text = WALK.replace("objective_pos = Vector3(40, 0, -30)\n", "")
    out, report = inject_lt_hooks(text)
    assert HOOK_OBJECTIVE in report["injected"]
    assert "objective_pos" in report["derived"]


def test_no_spawn_means_a_stated_noop_not_a_silent_one():
    """Staging that cannot meet the contract must say so; otherwise Godot is
    handed a scene guaranteed to come back with zero runs."""
    bare = '[gd_scene format=3]\n\n[node name="x" type="Node3D"]\n'
    out, report = inject_lt_hooks(bare)
    assert out == bare
    assert report["injected"] == []
    assert "no spawn_pos" in report["reason"]


def test_injected_names_are_legal_godot_node_names():
    from packages.staging.tscn_names import INVALID_NAME_CHARS, sanitize_node_names
    out, _ = inject_lt_hooks(WALK)
    resanitized, renames = sanitize_node_names(out)
    assert renames == [], "hook injection must not emit names Godot will rewrite"
    assert not any(c in HOOK_ENEMY_SPAWNS for c in INVALID_NAME_CHARS)
    assert resanitized == out
