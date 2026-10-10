"""The walk preview starts at the package's player_start, its visual check can see, and its next
steps name commands the person has (0.171.0, roadmap 202's install test).

Found by walking cold run 9222's package from a fresh unpack:

* "player at default (no markers)": an export's `mission.tscn` loads its content at runtime,
  so a search of its text for markers finds none, and the player stood at (0, 1.5, 3);
* the shot bot's five frames were 100% black and all five read OK: the package's shader
  warm-up covers the screen while it sweeps, and black is neither the void colour nor a frame
  that differs from its twin;
* the walk printed PowerShell's `& "<godot>"` to cmd users, and the export named `godot` and
  `python tools/walk_export.py`, which nobody who installed only Blender and Godot has.

The shot bot is GDScript and needs a display, which this suite does not have, so its two
changes are held here by reading the script; the run that proved them is in the changelog.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export as export_mod  # noqa: E402
from packages.preview import walk_preview  # noqa: E402
from packages.preview.walk_preview import build_walk_preview  # noqa: E402

_PLAYER_SRC = ROOT / "assets" / "godot"

# What an export's entry scene is: content loaded at runtime, no Markers in the text.
_ENTRY_TSCN = '''[gd_scene load_steps=2 format=3]

[sub_resource type="GDScript" id="mission_entry"]
script/source = "extends Node3D
func _ready() -> void:
	add_child((load('res://site.tscn') as PackedScene).instantiate())
"

[node name="Mission" type="Node3D"]
script = SubResource("mission_entry")
'''

_SITE_WITH_MARKERS = '''[gd_scene load_steps=1 format=3]

[node name="site" type="Node3D"]

[node name="Markers" type="Node3D" parent="."]

[node name="SPAWN_1" type="Node3D" parent="Markers" groups=["spawn", "dc_marker"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 5.0, 0.0, -3.0)
metadata/marker_type = "spawn"
'''


def _anchors(player_start=(53.85, 0.0, 16.965)):
    anchors = [{"anchor_type": "attacker_spawn", "transform": {"pos": [1.0, 0.0, 1.0]}}]
    if player_start is not None:
        anchors.append({"anchor_type": "player_start",
                        "node_dispatch": "Functional/GameplayAnchors/PlayerStarts/van_0",
                        "transform": {"pos": list(player_start), "rot_y_deg": 0.0}})
    return {"schema": "dispatch.gameplay_anchors.v0.2", "anchors": anchors}


def _content(tmp_path, *, entry=True, anchors=None, site=_SITE_WITH_MARKERS):
    c = tmp_path / "export"
    c.mkdir()
    (c / "site.tscn").write_text(site, encoding="utf-8")
    if entry:
        (c / "mission.tscn").write_text(_ENTRY_TSCN, encoding="utf-8")
    if anchors is not None:
        (c / "gameplay_anchors.json").write_text(
            anchors if isinstance(anchors, str) else json.dumps(anchors), encoding="utf-8")
    return c


def _origin(report):
    return tuple(report["spawn_transform"][9:12])


def test_the_player_starts_at_the_packages_player_start(tmp_path):
    report = build_walk_preview(_content(tmp_path, anchors=_anchors()), _PLAYER_SRC,
                                tmp_path / "preview")
    assert report["spawn_source"].startswith("anchor:player_start")
    assert "van_0" in report["spawn_source"]
    assert _origin(report) == (53.85, 0.6, 16.965)       # at grade, plus the preview's 0.6


def test_an_entry_scene_alone_is_what_left_the_player_at_the_default(tmp_path):
    # the case the install test found: the entry scene's text has no markers to read
    report = build_walk_preview(_content(tmp_path, anchors=None), _PLAYER_SRC,
                                tmp_path / "preview")
    assert report["spawn_source"] == "default (no markers)"


def test_without_a_player_start_the_markers_still_decide(tmp_path):
    report = build_walk_preview(
        _content(tmp_path, entry=False, anchors=_anchors(player_start=None)),
        _PLAYER_SRC, tmp_path / "preview")
    assert report["spawn_source"] == "marker:spawn"
    assert _origin(report) == (5.0, 0.6, -3.0)


def test_an_unreadable_anchors_file_falls_back_rather_than_guessing(tmp_path):
    report = build_walk_preview(_content(tmp_path, entry=False, anchors="{not json"),
                                _PLAYER_SRC, tmp_path / "preview")
    assert report["spawn_source"] == "marker:spawn"
    assert walk_preview._spawn_from_anchors(tmp_path / "export") is None


def test_a_player_start_without_a_position_is_not_a_spawn(tmp_path):
    bad = {"anchors": [{"anchor_type": "player_start", "transform": {"pos": [1.0, 2.0]}}]}
    assert walk_preview._spawn_from_anchors(_content(tmp_path, anchors=bad)) is None


# ------------------------------------------------------------- the shot bot

_SHOT_BOT = (ROOT / "assets" / "godot" / "shot_bot.gd").read_text(encoding="utf-8")


def test_the_shot_bot_holds_the_warmup_before_the_content_enters_the_tree():
    hold = _SHOT_BOT.find("_hold_warmups(site)")
    enter = _SHOT_BOT.find("root.add_child(site)")
    assert 0 < hold < enter
    body = _SHOT_BOT[_SHOT_BOT.find("func _hold_warmups"):]
    assert 'has_signal("warmup_finished")' in body and '"enabled", false' in body


def test_the_shot_bot_holds_what_the_export_ships():
    # the warm-up it holds is the one the export writes into mission.tscn
    warmup = (ROOT / "assets" / "godot" / "warmup.gd").read_text(encoding="utf-8")
    assert "signal warmup_finished" in warmup
    assert re.search(r"@export var enabled: bool", warmup)
    assert re.search(r"@export var cover_screen: bool", warmup)


def test_a_frame_of_one_colour_fails_its_station():
    verdict = _SHOT_BOT[_SHOT_BOT.find("func _shoot"):_SHOT_BOT.find("func _frame")]
    gate = verdict.find("if _one_colour(a):")
    assert gate > 0
    assert 'st["ok"] = false' in verdict[gate:gate + 200]


# ------------------------------------------------------------- the hints

_COMMANDS = (ROOT / "apps" / "cli" / "commands" / "__init__.py").read_text(encoding="utf-8")


def test_the_walk_names_its_own_open_and_play_not_powershell():
    assert "& \"{godot" not in _COMMANDS
    assert re.search(r'print\(f"  open:  \{_again\} --open"\)', _COMMANDS)
    assert re.search(r'print\(f"  play:  \{_again\} --play"\)', _COMMANDS)
    assert '_again = f"{discovery.command_name()} -C {ws.root} walk {mission_id}"' in _COMMANDS


def test_the_export_names_no_command_the_person_lacks():
    # code lines only: the comment that says what the hints used to be quotes them
    code = "\n".join(ln for ln in _COMMANDS.splitlines() if not ln.lstrip().startswith("#"))
    assert "python tools/walk_export.py" not in code
    assert "godot --headless --path <dir> --import" not in code
    assert "walk {mission_id} --play" in code


def test_the_handoff_tells_its_reader_to_walk_with_level_factory():
    text = export_mod.HANDOFF_LANGUAGE
    assert "python tools/walk_export.py" not in text
    assert "walk <mission_id> --play" in text
    assert ".\\factory" in text and "sh factory.sh" in text
