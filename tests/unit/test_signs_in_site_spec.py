"""Which business each building is (roadmap 153, the 1990s street).

Pixelcoat names a theme's businesses; Lot hangs the band on the facade
that faces the street; this is the piece between them.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from packages.core.models import MissionBrief

PIXELCOAT = Path(__file__).resolve().parents[3] / "pixelcoat"


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {"pixelcoat": str(PIXELCOAT)}}


class _NoTools(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def test_an_archetype_reads_as_a_family_of_business():
    assert cmds.sign_family("bank_branch_a02") == "bank"
    assert cmds.sign_family("deli_a01") == "deli"
    assert cmds.sign_family("warehouse_a02") == "warehouse"
    assert cmds.sign_family("gas_station_a03") == "gas_station"
    assert cmds.sign_family("pawn_shop_a01") == "pawn"
    assert cmds.sign_family("landmark_hall_a02") == "default"
    assert cmds.sign_family("") == "default"


def test_each_building_takes_a_business_of_its_own_family_and_no_two_repeat():
    ws = _Workspace()
    buildings = [{"id": "b0", "archetype": "bank_branch_a02"},
                 {"id": "b1", "archetype": "deli_a01"},
                 {"id": "b2", "archetype": "bank_tower_a03"}]
    signs = cmds._signs_for(ws, buildings, Path("/px/out"), "delco_1997")
    assert set(signs) == {"b0", "b1", "b2"}
    slugs = [Path(d).name for d in signs.values()]
    assert len(set(slugs)) == 3, slugs           # a strip with two of one reads wrong
    profile = {s["slug"]: s for s in cmds._sign_profile(ws, "delco_1997")}
    for bid, d in signs.items():
        slug = Path(d).name[len("sign_"):]
        fam = cmds.sign_family(next(b["archetype"] for b in buildings if b["id"] == bid))
        assert fam in profile[slug]["families"], (bid, slug)
        assert Path(d).parent.name == "signs"
    # stable: the same row picks the same shops
    assert cmds._signs_for(ws, buildings, Path("/px/out"), "delco_1997") == signs


def test_a_theme_with_no_businesses_gives_nobody_a_sign():
    ws = _Workspace()
    assert cmds._signs_for(ws, [{"id": "b0", "archetype": "bank"}],
                           Path("/px/out"), "no_such_theme") == {}
    # and a workspace that is not pinned to a pixelcoat checkout says the same
    assert cmds._signs_for(_NoTools(), [{"id": "b0", "archetype": "bank"}],
                           Path("/px/out"), "delco_1997") == {}


def _deli_out(tmp_path: Path) -> Path:
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    return tmp_path / "deli"


def test_the_themed_spec_carries_the_signs_and_the_greybox_does_not(tmp_path):
    brief = MissionBrief(mission_id="m", display_name="m", archetype="bank",
                         building_count=2, theme="delco_1997",
                         candidate_count=1, lot_library=None)
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    grey = cmds._write_site_spec(ws, brief, _deli_out(tmp_path), seed=9039)
    assert "signs" not in json.loads(grey.read_text(encoding="utf-8"))
    themed = cmds._write_site_spec(
        ws, brief, tmp_path / "deli", seed=9039,
        themed_scene=str(tmp_path / "compose" / "site.tscn"),
        pixelcoat_out=tmp_path / "px")
    doc = json.loads(themed.read_text(encoding="utf-8"))
    assert doc["signs"], "the themed street has no shop signs"
    for bid, d in doc["signs"].items():
        assert bid in {b["id"] for b in doc["buildings"]}
        assert Path(d).name.startswith("sign_")
