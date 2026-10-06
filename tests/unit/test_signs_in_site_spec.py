"""Which business each building is (roadmap 153, the 1990s street).

Pixelcoat names a theme's businesses; Lot hangs the band on the facade
that faces the street; this is the piece between them.

WHERE PIXELCOAT IS, AND WHY THAT IS A SEARCH (0.94.0). It was
`parents[3] / "pixelcoat"` -- correct beside the sibling checkouts, and
`scratchpad/pixelcoat` from a git worktree. The profile was there the whole
time; two tests failed with `KeyError: 'signs'` under the builder's own
`no shop signs: theme 'delco_1997' names no businesses` message, which is
what a missing checkout and an empty theme look like from here. The locator
now walks up to the profile it is about to read, and it ASSERTS rather than
letting the absence answer the question -- `tests/siblings.py`.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from packages.core.models import MissionBrief
from tests.siblings import not_found, sibling_repo

#: The file these tests are really about: without it, `_signs_for` returns {}
#: and every assertion below reads as a design answer rather than a missing
#: repo. So it is the marker, not the directory name.
_PROFILE = "profiles/signs/delco_1997.json"
PIXELCOAT = sibling_repo("pixelcoat", marker=_PROFILE)


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        assert PIXELCOAT is not None, not_found("pixelcoat", marker=_PROFILE)
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


def test_the_flappahs_store_reads_as_a_convenience_store():
    """0.146.0: read before `store` makes it retail. The walker, 2026-10-06:
    the Flappahs store is always Flappahs."""
    assert cmds.sign_family("convenience_store_a01") == "convenience"
    assert cmds.sign_family("convenience_store") == "convenience"
    assert cmds.sign_family("gas_station") == "gas_station"


def test_a_generated_building_reads_as_the_briefs_archetype():
    """0.146.0: a generated row names no archetype and read as `default`."""
    rows = [{"id": "b0"}, {"id": "b1", "archetype": "deli_a01"}]
    out = cmds._sign_rows(rows, "convenience_store")
    assert [cmds.sign_family(r["archetype"]) for r in out] == ["convenience", "deli"]
    assert rows[0] == {"id": "b0"}          # the site spec's own rows are untouched


def test_a_generated_building_reads_as_the_preset_it_was_built_from():
    """0.146.0: read raw, `station` is civic -- a generated `service_station`
    wore a civic name, a `mini_mart` a default one, a `go_go_bar` a bar's."""
    for word, family in (("service_station", "gas_station"),
                         ("mini_mart", "convenience"),
                         ("go_go_bar", "club"),
                         ("county_hospital", "civic")):
        (row,) = cmds._sign_rows([{"id": "b0"}], word)
        assert cmds.sign_family(row["archetype"]) == family, (word, row)
    # a word no preset answers to is kept: nothing was generated for it
    (row,) = cmds._sign_rows([{"id": "b0"}], "mixed_block")
    assert row["archetype"] == "mixed_block"


def test_a_station_and_a_store_wear_flappahs_never_the_price_board():
    """0.146.0. The walker, 2026-10-06: "Flappahs store always Flappahs".
    The gas family is FLAPPAHS and the fuel price board (Pixelcoat 0.58.0),
    and the board names nobody. Before names-only dealing a generated gas
    station standing alone drew the board, and so did `gas_station_a02` at
    the head of a row."""
    ws = _Workspace()
    for archetype in ("gas_station", "convenience_store"):
        rows = cmds._sign_rows([{"id": "b0"}], archetype)
        signs = cmds._signs_for(ws, rows, Path("/px/out"), "delco_1997")
        assert Path(signs["b0"]).name == "sign_flappahs", (archetype, signs)
    for archetype in ("gas_station_a01", "gas_station_a02", "convenience_store_a01"):
        for i in range(4):
            rows = [{"id": f"x{j}", "archetype": "deli_a01"} for j in range(i)]
            rows.append({"id": "b", "archetype": archetype})
            signs = cmds._signs_for(ws, rows, Path("/px/out"), "delco_1997")
            assert Path(signs["b"]).name == "sign_flappahs", (archetype, i, signs)
    # one brand a site: a station beside the store is FLAPPAHS twice
    rows = [{"id": "b0", "archetype": "gas_station_a02"},
            {"id": "b1", "archetype": "convenience_store_a01"}]
    signs = cmds._signs_for(ws, rows, Path("/px/out"), "delco_1997")
    assert {Path(d).name for d in signs.values()} == {"sign_flappahs"}, signs


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
