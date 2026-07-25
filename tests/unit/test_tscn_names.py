"""A staged .tscn must use names Godot can actually keep (TDD 24.7).

Godot rewrites `. : @ / " %` in a node name to `_` at load time, silently. A
scene that writes `name="b0/LADDER_0_climb"` and then `parent="b0/LADDER_0_climb"`
loses the child: the node becomes `b0_LADDER_0_climb`, the parent string is
parsed as the *path* `b0` -> `LADDER_0_climb`, nothing matches, and the child is
dropped. Lot did exactly this for every ladder, so every climb volume shipped
without its CollisionShape3D and nothing could climb it — while the scene loaded,
the build passed, and no surface said a word.

The fix lives in Lot (names are legal at write time). This module is Level
Factory's net for the same defect arriving from any other generator.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.staging.tscn_names import (  # noqa: E402
    INVALID_NAME_CHARS, sanitize_node_names, validate_node_name)

LADDER = '''[gd_scene load_steps=2 format=3]

[sub_resource type="BoxShape3D" id="Box_0"]
size = Vector3(1.3, 4.6, 1.3)

[node name="site_walk" type="Node3D"]

[node name="b0/LADDER_0_climb" type="Area3D" parent="." groups=["ladder"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 3, -4)

[node name="shape" type="CollisionShape3D" parent="b0/LADDER_0_climb"]
shape = SubResource("Box_0")
'''


def test_godots_own_rule_is_the_rule_we_apply():
    for ch in INVALID_NAME_CHARS:
        assert validate_node_name(f"a{ch}b") == "a_b"
    assert validate_node_name("b0/LADDER_0_climb") == "b0_LADDER_0_climb"
    assert validate_node_name("Player") == "Player"


def test_the_ladder_child_survives_the_rewrite():
    """The whole point: after sanitizing, the CollisionShape3D's parent names a
    node that exists."""
    out, renames = sanitize_node_names(LADDER)
    assert 'name="b0_LADDER_0_climb"' in out
    assert 'parent="b0_LADDER_0_climb"' in out
    assert "b0/LADDER_0" not in out
    assert renames == [("b0/LADDER_0_climb", "b0_LADDER_0_climb")]
    # parent must still be declared before the child that references it
    assert out.index('name="b0_LADDER_0_climb"') < out.index('parent="b0_LADDER_0_climb"')


def test_repairs_are_reported_not_silent():
    """A quiet fix is the same failure mode as the bug: the operator learns
    nothing. `renames` is what staging.notes.json prints."""
    _, renames = sanitize_node_names(LADDER)
    assert renames, "a rewrite that reports nothing cannot be reviewed"
    for original, safe in renames:
        assert original != safe
        assert not any(c in safe for c in INVALID_NAME_CHARS)


def test_legal_scenes_are_left_byte_identical():
    clean = ('[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\n\n'
             '[node name="Child" type="Node3D" parent="."]\n')
    out, renames = sanitize_node_names(clean)
    assert out == clean
    assert renames == []


def test_nested_paths_are_rewritten_at_every_level():
    text = ('[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\n\n'
            '[node name="a.b" type="Node3D" parent="."]\n\n'
            '[node name="c:d" type="Node3D" parent="a.b"]\n\n'
            '[node name="leaf" type="Node3D" parent="a.b/c:d"]\n')
    out, _ = sanitize_node_names(text)
    assert 'parent="a_b"' in out
    assert 'parent="a_b/c_d"' in out
    assert "a.b" not in out and "c:d" not in out


def test_the_dot_slash_prefix_form_is_preserved():
    """Lot writes `parent="./Nav"`; the leading `./` is syntax, not a name."""
    text = ('[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\n\n'
            '[node name="Nav" type="NavigationRegion3D" parent="."]\n\n'
            '[node name="x/y" type="Node3D" parent="./Nav"]\n\n'
            '[node name="deep" type="Node3D" parent="./Nav/x/y"]\n')
    out, _ = sanitize_node_names(text)
    assert 'parent="./Nav"' in out
    assert 'name="x_y"' in out
    assert 'parent="./Nav/x_y"' in out


def test_connection_and_editable_paths_follow_the_rename():
    text = ('[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\n\n'
            '[node name="a/b" type="Button" parent="."]\n\n'
            '[editable path="a/b"]\n'
            '[connection signal="pressed" from="a/b" to="." method="_on"]\n')
    out, _ = sanitize_node_names(text)
    assert 'path="a_b"' in out
    assert 'from="a_b"' in out


def test_no_emitted_name_can_contain_an_invalid_character():
    """The invariant, stated once: whatever comes in, what goes out is legal."""
    import re
    out, _ = sanitize_node_names(LADDER)
    for name in re.findall(r'^\[node name="([^"]*)"', out, re.M):
        assert not any(c in name for c in INVALID_NAME_CHARS), name
