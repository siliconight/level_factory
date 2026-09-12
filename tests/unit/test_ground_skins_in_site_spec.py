"""The themed site spec names a Pixelcoat pack per outdoor family.

Roadmap 152: cold run 9014's exterior ground was one untextured grey, so the
only detail outdoors was the clutter scattered on it. The themed site now
carries `ground_skins` -- a pack DIRECTORY per family, constructed from the
theme build's `<kind>_<theme>` layout before any job runs -- and Lot reads
the pack when it assembles. The greybox site carries nothing: it is the one
the candidate is judged on.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from packages.core.models import MissionBrief


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


def test_the_pack_directories_are_constructed_from_the_theme_layout():
    skins = cmds._ground_skins_for(Path("/px/out"), "delco_1997")
    assert skins == {
        "ground": str(Path("/px/out") / "asphalt_delco_1997"),
        "path": str(Path("/px/out") / "sidewalk_delco_1997"),
        "courtyard": str(Path("/px/out") / "concrete_delco_1997"),
        "road": str(Path("/px/out") / "asphalt_delco_1997"),
        "sidewalk": str(Path("/px/out") / "sidewalk_delco_1997"),
        "paint": str(Path("/px/out") / "road_paint_delco_1997"),
    }
    assert set(cmds.GROUND_SKIN_KINDS) == {"ground", "path", "courtyard", "road", "sidewalk", "paint"}


def test_the_themed_spec_carries_the_skins_and_the_greybox_spec_does_not(tmp_path):
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    skins = cmds._ground_skins_for(tmp_path / "px", "delco_1997")
    grey = cmds._write_site_spec(ws, _brief(), _deli_out(tmp_path), seed=9014)
    assert "ground_skins" not in json.loads(grey.read_text(encoding="utf-8"))
    themed = cmds._write_site_spec(
        ws, _brief(), tmp_path / "deli", seed=9014,
        themed_scene=str(tmp_path / "compose" / "site.tscn"), ground_skins=skins)
    doc = json.loads(themed.read_text(encoding="utf-8"))
    assert doc["ground_skins"] == skins
    assert themed != grey


def test_the_lot_adapter_publishes_the_skins_beside_the_scene(tmp_path):
    """Cold run 9016: Lot wrote skins/*.png beside site.tscn and the adapter
    published only .tscn/.json/.csv/.glb/.gd, so the Lux stage loaded a
    scene whose textures were not there."""
    from adapters.lot import LotAdapter
    work = tmp_path / "work"
    (work / "skins").mkdir(parents=True)
    (work / "site.tscn").write_text("[gd_scene]", encoding="utf-8")
    (work / "skins" / "asphalt_delco_albedo.png").write_bytes(b"\x89PNG")
    (work / "notes.txt").write_text("not published", encoding="utf-8")
    got = {p.relative_to(work).as_posix()
           for p in LotAdapter().collect_outputs({}, {"work_dir": str(work)})}
    assert got == {"site.tscn", "skins/asphalt_delco_albedo.png"}
