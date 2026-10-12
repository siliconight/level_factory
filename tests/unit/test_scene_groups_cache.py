"""The light bake's editor is given the scene groups cache it would build first (0.191.0).

A Godot 4.7 editor opened on a project with no `.godot/scene_groups_cache.cfg` starts by reading
every scene's groups: cold run 9256's bake editor loaded each of the package's 482 models before
it could ask for the bake scene (the factory's docs/findings/grader_speed/bake_phases_probe.py).
Given the cache, it asked at 13.1 s instead of 32.4 and took 68.0 s instead of 88.0. The export
writes the cache from the scenes' own text before the bake copies its work directory.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import light_bake as L  # noqa: E402

#: What a bake editor wrote, verbatim: the work copy's `.godot/scene_groups_cache.cfg` from cold
#: run 9255's mission re-exported on 0.190.0 (the factory's editor_texture_probe.py keeps that
#: copy), after the editor had read all 22 of the package's scenes -- 9256's scenes too.
EDITOR_CACHE = (
    '[res://lot/deli_a01/site.tscn]\n\ngroups=[&"ladder", &"dc_marker", &"hatch", &"attacker_spawn", '
    '&"defender_spawn", &"objective", &"extraction", &"cover_low", &"cover_high", &"camera_socket", '
    '&"patrol_point", &"ladder_area3d", &"dc_ladder"]\n\n'
    '[res://lot/office/site.tscn]\n\ngroups=[&"cover_high", &"dc_marker", &"cover_low", '
    '&"camera_socket", &"attacker_spawn", &"defender_spawn", &"objective"]\n\n'
    '[res://lot/pharmacy_a01/site.tscn]\n\ngroups=[&"attacker_spawn", &"dc_marker", '
    '&"defender_spawn", &"objective", &"extraction", &"cover_low", &"camera_socket"]\n')


#: A group as a cache file writes it, read here without the module's own pattern.
_CACHED_NAME = re.compile(r'&"([^"]*)"')


def _cache_rows(text):
    """[(scene path, [groups in the order written])] of a cache file's text."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("[") and ln.endswith("]"):
            out.append((ln[1:-1], []))
        elif ln.startswith("groups="):
            out[-1][1].extend(_CACHED_NAME.findall(ln))
    return out


def _scene(path, groups_per_node):
    """A scene whose nodes carry these groups, written as Godot writes them: `groups=["a", "b"]`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['[gd_scene format=3]\n', '\n[node name="Root" type="Node3D"]\n']
    for i, groups in enumerate(groups_per_node):
        g = (' groups=[%s]' % ", ".join('"%s"' % x for x in groups)) if groups else ""
        lines.append('\n[node name="n%d" type="Node3D" parent="."%s]\n' % (i, g))
    path.write_text("".join(lines), encoding="utf-8")


def _others(root):
    """What else a package holds: scenes with no group, and a scene under `.godot`."""
    _scene(root / "lot" / "gs_empty_rowhome_a" / "site.tscn", [[], []])
    _scene(root / "bake.tscn", [[]])
    _scene(root / ".godot" / "imported" / "stale.tscn", [["not_a_package_scene"]])


def test_the_cache_written_is_the_editors_byte_for_byte(tmp_path):
    for res, groups in _cache_rows(EDITOR_CACHE):
        _scene(tmp_path / res[len("res://"):], [[g] for g in groups])
    _others(tmp_path)
    assert L.write_scene_groups_cache(tmp_path) == 3
    assert (tmp_path / L.SCENE_GROUPS_CACHE).read_bytes() == EDITOR_CACHE.encode("utf-8")


def test_groups_spread_over_many_nodes_are_listed_once_each(tmp_path):
    want = {res: set(groups) for res, groups in _cache_rows(EDITOR_CACHE)}
    for res, groups in want.items():
        g = sorted(groups)
        # two to a node, and the marker group on every node, as Deli Counter's markers carry it
        _scene(tmp_path / res[len("res://"):], [g[i:i + 2] + ["dc_marker"] for i in range(0, len(g), 2)])
    _others(tmp_path)
    L.write_scene_groups_cache(tmp_path)
    rows = _cache_rows((tmp_path / L.SCENE_GROUPS_CACHE).read_text(encoding="utf-8"))
    assert {res: set(groups) for res, groups in rows} == want
    assert all(len(groups) == len(set(groups)) for _res, groups in rows)


def test_a_scene_with_no_group_and_the_scenes_under_godot_are_left_out(tmp_path):
    _scene(tmp_path / "lot" / "deli_a01" / "site.tscn", [["ladder"]])
    _others(tmp_path)
    assert L.write_scene_groups_cache(tmp_path) == 1
    text = (tmp_path / L.SCENE_GROUPS_CACHE).read_text(encoding="utf-8")
    assert text == '[res://lot/deli_a01/site.tscn]\n\ngroups=[&"ladder"]\n'


def test_the_groups_of_a_scene_are_read_off_its_node_headers():
    text = ('[gd_scene format=3]\n\n[node name="R" type="Node3D"]\n'
            'groups_note = "groups=[\\"not_a_header\\"]"\n\n'
            '[node name="a" type="Node3D" parent="." groups=["ladder", "dc_marker"]]\n\n'
            '[node name="b" parent="." instance=ExtResource("1") groups=[&"cover_low"]]\n\n'
            '[node name="c" type="Node3D" parent="." groups=["dc_marker"]]\n')
    assert L.scene_groups(text) == ["ladder", "dc_marker", "cover_low"]


def test_a_package_with_no_groups_gets_an_empty_cache(tmp_path):
    _scene(tmp_path / "site.tscn", [[]])
    assert L.write_scene_groups_cache(tmp_path) == 0
    assert (tmp_path / L.SCENE_GROUPS_CACHE).read_bytes() == b""


def test_the_bake_writes_it_after_its_import_and_before_its_work_copy():
    text = (ROOT / "packages" / "exporting" / "light_bake.py").read_text(encoding="utf-8")
    body = text[text.index("def bake("):]
    code = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    imp = code.find("if not _import(export_dir, godot_executable):")
    cache = code.find("write_scene_groups_cache(export_dir)")
    copy = code.find("shutil.copytree(export_dir, work)")
    assert -1 < imp < cache < copy, (imp, cache, copy)
