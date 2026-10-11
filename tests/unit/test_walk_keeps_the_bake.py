"""The walk bakes what it re-exports (0.178.3, install test 5).

`walk` wraps the mission's portable export, and re-exports it first by calling `cmd_export` with
its own arguments -- which carried no bake, so every walk since 0.144.0 replaced the baked
package `make` had shipped with an unbaked one in the same folder. Install test 5 measured the
stranger's package after `walk` at 2,526 files with no `bake.exr` and no `light_bake.json`, where
`make` had left 3,008 and a bake. The walk's parser now carries `--bake-lights` at the export's
own default, and `cmd_walk` hands it to the export.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import apps.cli.commands as cmds  # noqa: E402
from apps.cli.main import build_parser  # noqa: E402
from packages.exporting.export import BAKE_LIGHTS_CLI_DEFAULT  # noqa: E402


def _walk_until_the_export(monkeypatch, tmp_path, argv):
    seen = {}
    monkeypatch.setattr(cmds, "_ws", lambda a: SimpleNamespace(jobs_dir=tmp_path,
                                                               internal_dir=tmp_path))
    monkeypatch.setattr(cmds, "walk_content_dir", lambda jobs, m: (tmp_path, "job outputs"))

    def export(a):
        seen["bake_lights"] = getattr(a, "bake_lights", None)
        seen["mode"] = a.mode
        return cmds.EXIT_BLOCKED            # stop the walk here: the export is the question
    monkeypatch.setattr(cmds, "cmd_export", export)
    code = cmds.cmd_walk(build_parser().parse_args(argv))
    return code, seen


def test_the_walk_bakes_the_export_it_wraps_by_default(monkeypatch, tmp_path):
    code, seen = _walk_until_the_export(monkeypatch, tmp_path, ["walk", "m"])
    assert code == cmds.EXIT_BLOCKED
    assert seen == {"bake_lights": BAKE_LIGHTS_CLI_DEFAULT, "mode": "portable-godot"}
    assert BAKE_LIGHTS_CLI_DEFAULT is True


def test_a_quicker_walk_without_the_bake_is_asked_for(monkeypatch, tmp_path):
    _code, seen = _walk_until_the_export(monkeypatch, tmp_path, ["walk", "m", "--no-bake-lights"])
    assert seen["bake_lights"] is False
