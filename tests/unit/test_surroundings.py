"""What stands beyond the plate's edge, named by the brief or decided by the archetype (0.175.0,
roadmap 228 step D): the site spec carries `surroundings` for Lot's backdrop recipe."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import apps.cli.commands as cmds
from packages.core.models import MissionBrief
from packages.pipeline import site_variation as sv


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def _deli_out(tmp_path: Path) -> Path:
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    return tmp_path / "deli"


def _brief(**kw):
    fields = dict(mission_id="m", display_name="m", archetype="bank", building_count=1,
                  theme="delco_1997", candidate_count=1, lot_library=None)
    fields.update(kw)
    return MissionBrief(**fields)


@pytest.mark.parametrize("archetype, site_shape, want", [
    ("strip_club", "street_block", "borough"),
    ("urban_bank", "street_block", "borough"),
    ("industrial_warehouse", "yard", "yards"),
    ("industrial_warehouse", "street_block", "yards"),
    ("corner_deli", "yard", "yards"),
    ("county_hospital", "campus", "parkland"),
    ("card_shop", "campus", "parkland"),
    ("gas_station", "strip", "roadside"),
    ("convenience_store", "strip", "roadside"),
    ("gas_station", "street_block", "borough"),
    ("", "", "borough"),
])
def test_unnamed_the_archetype_and_the_site_shape_decide(archetype, site_shape, want):
    assert sv.surroundings_of("", archetype, site_shape) == want


def test_a_named_recipe_wins_whatever_the_archetype():
    assert sv.surroundings_of("Parkland", "industrial_warehouse", "yard") == "parkland"
    assert sv.surroundings_of(" none ", "strip_club", "street_block") == "none"


def test_a_word_nobody_knows_is_the_borough_and_said_unknown():
    assert sv.surroundings_of("moon", "strip_club", "street_block") == "borough"
    assert sv.surroundings_known("moon") is False
    assert sv.surroundings_known("") is True and sv.surroundings_known("YARDS") is True
    assert sv.SURROUNDINGS == ("borough", "none", "yards", "parkland", "roadside")


def test_the_brief_carries_the_field_and_the_lock_does_not():
    b = cmds._brief_model({"mission_id": "m", "display_name": "m", "surroundings": "Yards"})
    assert b.surroundings == "Yards"
    assert "surroundings" not in b.functional_signature()
    assert MissionBrief(mission_id="m", display_name="m").surroundings == ""


def test_a_backdrop_piece_with_a_z_is_composed_at_its_foot_plus_half_its_height():
    from packages.exporting.backdrop_layer import manifest_from_drawn
    drawn = {"name": "site", "cover_modules": {"dir": "k", "theme": "delco_1997", "style": 1},
             "backdrop": [
                 {"species": "cargo_container", "at": [10.0, 60.0], "yaw": 90.0,
                  "dims": [2.44, 6.06, 2.59], "side": "N"},
                 {"species": "cargo_container", "at": [10.0, 60.0], "yaw": 90.0,
                  "dims": [2.44, 6.06, 2.59], "side": "N", "z": 2.59}]}
    lower, upper = manifest_from_drawn(drawn)["orders"]
    assert abs(lower["pos"][2] - 2.59 / 2) < 1e-9
    assert abs(upper["pos"][2] - (2.59 + 2.59 / 2)) < 1e-9
    assert lower["asset_id"] == upper["asset_id"]


def test_the_site_spec_carries_what_was_asked_what_it_got_and_whether_the_word_was_known(tmp_path):
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    deli = _deli_out(tmp_path)
    spec = json.loads(cmds._write_site_spec(ws, _brief(archetype="county_hospital", site_shape="campus"),
                                            deli, seed=9225).read_text(encoding="utf-8"))
    assert spec["surroundings"] == "parkland"
    assert spec["surroundings_resolved"] == {"asked": "", "got": "parkland", "known": True}
    spec = json.loads(cmds._write_site_spec(ws, _brief(surroundings="moon"), deli, seed=9226)
                      .read_text(encoding="utf-8"))
    assert spec["surroundings"] == "borough"
    assert spec["surroundings_resolved"] == {"asked": "moon", "got": "borough", "known": False}
