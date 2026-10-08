"""0.156.0 -- Lot's site-level markers reach Dispatch (roadmap 204).

`dispatch_inputs._iter_records` turned Lot's gameplay `markers`, `objectives`
and `loot` into anchors and never read `site_markers`. So the getaway van's
crew spawn and extraction (Lot 0.98.0) never reached the package, and
`ensure_mission_anchors` covered the gap:
- with no `player_start` among Lot's anchors, it synthesized one at the
  centroid of every Lot anchor -- cold run 9198's `lot:mission_start`, at
  (-7.03, 0.68), 14 m from the van;
- with extractions present and none tagged, it tagged every building's as the
  mission's.
Lot 0.99.0's responder arrivals went the same way.

The site below is cold run 9200's seed_9054 as Lot wrote it -- the van's
point, the three arrivals' stops, two buildings' street extractions -- cut
down to what the staging reads. The instruments are the test's own: the
staged anchors are read from the file the staging writes, by position and
tag.
"""
import json
import math

from packages.staging.dispatch_inputs import stage_dispatch_inputs

#: Cold run 9200, seed_9054 (site plan frame, metres).
VAN = (-4.15, -14.95)
STOPS = [(-29.9, -1.0), (-14.0, -22.6), (7.0, -19.8)]
BUILDING_EXITS = [("EXIT", 6.0, -13.0), ("STREET", -56.0, -12.0)]


def _lot_gameplay(site_markers=True):
    gp = {"up_axis": "z",
          "markers": [{"id": name, "type": "extraction", "x": x, "y": y, "z": 0.0}
                      for name, x, y in BUILDING_EXITS]
          + [{"id": "MAIN_W", "type": "door", "x": -2.4, "y": -13.0, "z": 0.0}]}
    if site_markers:
        gp["site_markers"] = (
            [{"type": "crew_spawn", "at": list(VAN), "source": "getaway_van"},
             {"type": "extraction", "at": list(VAN), "source": "getaway_van",
              "getaway": "step_van"}]
            + [{"type": "responder_spawn", "at": list(p), "source": "responder_arrival",
                "arrival": {"stop": list(p)}} for p in STOPS])
    return gp


def _staged(tmp_path, lot_gp):
    deli = tmp_path / "deli"
    deli.mkdir()
    (deli / "shell.gameplay.json").write_text(json.dumps({"up_axis": "z", "markers": []}),
                                              encoding="utf-8")
    lot = tmp_path / "lot_out"
    lot.mkdir()
    (lot / "site.site.gameplay.json").write_text(json.dumps(lot_gp), encoding="utf-8")
    stage_dispatch_inputs(tmp_path / "stage", deli_gameplay=deli / "shell.gameplay.json",
                          shell_glb=deli / "shell.glb",
                          lot_gameplay=lot / "site.site.gameplay.json", mission_id="m")
    staged = json.loads((tmp_path / "stage" / "lot" / "lot.gameplay.json").read_text(encoding="utf-8"))
    return staged["anchors"]


def _at(anchor, plan):
    return math.dist(anchor["pos"][:2], plan) < 1e-6


def test_the_mission_starts_at_the_van(tmp_path):
    anchors = _staged(tmp_path, _lot_gameplay())
    starts = [a for a in anchors if "mission_start" in (a.get("tags") or [])]
    assert len(starts) == 1, starts
    assert starts[0]["type"] == "player_start" and _at(starts[0], VAN)
    assert starts[0]["pos"][2] == 0.0                                  # on the plate


def test_the_mission_ends_at_the_van_and_only_there(tmp_path):
    anchors = _staged(tmp_path, _lot_gameplay())
    tagged = [a for a in anchors if "extraction" in (a.get("tags") or [])]
    assert len(tagged) == 1 and _at(tagged[0], VAN), tagged
    # the buildings' street points are still anchors, and no longer the mission's
    for name, x, y in BUILDING_EXITS:
        (a,) = [a for a in anchors if a["id"] == f"lot:{name}"]
        assert a["type"] == "extraction" and "extraction" not in (a.get("tags") or [])


def test_no_start_is_synthesized_at_the_centroid(tmp_path):
    anchors = _staged(tmp_path, _lot_gameplay())
    assert not [a for a in anchors if a["id"] == "lot:mission_start"]


def test_the_responders_arrive_where_lot_put_them(tmp_path):
    anchors = _staged(tmp_path, _lot_gameplay())
    responders = [a for a in anchors if "responder" in (a.get("tags") or [])]
    assert len(responders) == len(STOPS)
    assert all(a["type"] == "ai_spawn" for a in responders)
    assert sorted(tuple(round(v, 3) for v in a["pos"][:2]) for a in responders) == sorted(STOPS)


def test_a_site_without_site_markers_stages_as_before(tmp_path):
    """No site markers: the old behaviour, unchanged -- a start synthesized at
    the centroid and every extraction tagged as the mission's."""
    anchors = _staged(tmp_path, _lot_gameplay(site_markers=False))
    (start,) = [a for a in anchors if "mission_start" in (a.get("tags") or [])]
    assert start["id"] == "lot:mission_start"
    tagged = [a for a in anchors if "extraction" in (a.get("tags") or [])]
    assert len(tagged) == len(BUILDING_EXITS)
