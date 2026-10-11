"""The site spec tells Lot the package will bake its lights (0.178.0,
roadmap 231's second lever): Lot cuts its plates for the per-mesh light
cap, and a lightmapped mesh pairs with no baked light, so under the bake
it cuts them bigger (Lot 0.115.0's MESH_TILE_BAKED). One constant says
what `export` does unless told otherwise, and the parser and the spec
writer both read it.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from apps.cli.main import build_parser
from packages.core.models import MissionBrief
from packages.exporting.export import BAKE_LIGHTS_CLI_DEFAULT, ExportProfile


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def _deli_out(tmp_path: Path) -> Path:
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    return tmp_path / "deli"


def _brief():
    return MissionBrief(mission_id="m", display_name="m", archetype="bank",
                        building_count=1, theme="delco_1997",
                        candidate_count=1, lot_library=None)


def test_the_export_bakes_unless_told_otherwise_and_the_parser_reads_the_one_constant():
    assert BAKE_LIGHTS_CLI_DEFAULT is True
    # code that builds a profile says what it wants (the comment on the field)
    assert ExportProfile().bake_lights is False
    p = build_parser()
    assert p.parse_args(["export", "m"]).bake_lights is BAKE_LIGHTS_CLI_DEFAULT
    assert p.parse_args(["export", "m", "--no-bake-lights"]).bake_lights is False


def test_both_specs_tell_lot_the_lights_bake(tmp_path):
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    grey = cmds._write_site_spec(ws, _brief(), _deli_out(tmp_path), seed=9234)
    themed = cmds._write_site_spec(
        ws, _brief(), tmp_path / "deli", seed=9234,
        themed_scene=str(tmp_path / "compose" / "site.tscn"))
    for p in (grey, themed):
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert doc["render"] == {"lights_baked": BAKE_LIGHTS_CLI_DEFAULT}, p
