"""Fixture pipeline (Zoo v0.30 markers -> Lux v0.15 gate) + factory manifest."""
import json
from pathlib import Path

from adapters.lux import LuxAdapter
from adapters.zoo import ZooAdapter
from packages.pipeline.planner import plan_mission
from packages.pipeline import planner as planner_mod
from packages.tools import contracts


class _Brief:
    mission_id = "m1"
    candidate_count = 1
    archetype = "urban_bank"
    theme = "delco"
    time_of_day = "night"
    mode = "heist"


def _selected(plan):
    return plan.candidate_ids[0]


def test_planner_wires_fixture_stages():
    brief = _Brief()
    p1 = plan_mission(brief, seed_base=7, layers={planner_mod.LAYER_ART})
    sel = _selected(p1)
    plan = plan_mission(brief, seed_base=7, layers={planner_mod.LAYER_ART},
                        selected_candidate=sel)
    stages = {j.stage_id: j for j in plan.graph.jobs()}
    assert "zoo_fixtures_build" in stages
    assert "lux_fixture_gate" in stages
    fx = stages["zoo_fixtures_build"]
    gate = stages["lux_fixture_gate"]
    # fixtures build hangs off the selected candidate's DELI job (lights.json)
    assert any("deli_generate" in d for d in fx.depends_on)
    assert fx.resource_class == "blender"
    # the gate hangs off the fixtures build, headless Godot, one report out
    assert gate.depends_on == [fx.job_id]
    assert gate.resource_class == "godot_headless"
    assert gate.expected_outputs == ["fixture_gate.report.json"]


def test_zoo_fixtures_mode_plans_blender_invocation(tmp_path):
    lights = tmp_path / "shell.lights.json"
    lights.write_text(json.dumps({
        "light_manifest_version": "1.1", "building_id": "lf_m1",
        "anchors": [{"id": "a", "type": "fluorescent", "pos": [0, 0, 3]}]}))
    ad = ZooAdapter()
    spec = {"mode": "fixtures", "lights_path": str(lights), "theme": "delco"}
    assert ad.validate_configuration(spec, {}) == []
    cmds = ad.plan_commands(spec, {
        "repository": str(tmp_path), "work_dir": str(tmp_path / "work"),
        "blender_executable": "blender"})
    assert len(cmds) == 1
    args = list(cmds[0].arguments)
    assert args[0] == "--background" and "--fixtures" in args
    assert cmds[0].expected_outputs == ("lf_m1_fixtures.built.json",)
    assert cmds[0].resource_class == "blender"


def test_zoo_fixtures_marker_contract_blocks(tmp_path):
    ad = ZooAdapter()
    pre = tmp_path / "x_fixtures.built.json"
    pre.write_text(json.dumps({"fixtures_built": 4}))  # no emitter_markers
    issues = ad.normalize_validation([pre])
    assert any(i["code"] == "ZOO_FIXTURES_NO_MARKER_CONTRACT" and i["blocking"]
               for i in issues)

    bad = tmp_path / "y_fixtures.built.json"
    bad.write_text(json.dumps({"fixtures_built": 4, "emitter_markers": 3}))
    issues = ad.normalize_validation([bad])
    assert any(i["code"] == "ZOO_FIXTURES_MARKER_MISMATCH" and i["blocking"]
               for i in issues)

    good = tmp_path / "z_fixtures.built.json"
    good.write_text(json.dumps({"fixtures_built": 4, "emitter_markers": 4}))
    assert ad.normalize_validation([good]) == []


def _index(tmp_path, name, **fields):
    p = tmp_path / f"{name}_fixtures.built.json"
    p.write_text(json.dumps(fields))
    return p


def _places(marked, markerless, *, kind="club_wash"):
    """Placements shaped like Zoo's: `marker` is a per-placement bool.

    Zoo's `build.py` reads `p.get("marker", True)`, so a placement with no
    flag counts as marked; both spellings appear here on purpose.
    """
    out = [{"anchor_id": f"m{i}", "species": "pendant_fixture",
            "type": "pendant"} for i in range(marked)]
    if out:
        out[0]["marker"] = True          # explicit
    return out + [{"anchor_id": f"u{i}", "species": "club_fixture",
                   "type": kind, "marker": False} for i in range(markerless)]


def test_zoo_fixtures_markerless_is_accounted_for_not_blocked(tmp_path):
    """The cold-run-9064 refusal, in its own numbers.

    `strip_club_a02` built 25 fixtures, 18 with markers and 7 markerless by
    design, and 18 + 7 = 25. The v0.30 spelling of the contract
    (`emitter_markers == fixtures_built`) called that a blocker and refused a
    correct package.
    """
    ad = ZooAdapter()
    club = _index(tmp_path, "strip_club_a02", fixtures_built=25,
                  emitter_markers=18, markerless_fixtures=7,
                  placements=_places(18, 7), tool_version="1.1.1")
    issues = ad.normalize_validation([club])
    assert [i for i in issues if i["blocking"]] == []
    # The number survives the blocker's removal, as an observation.
    obs = [i for i in issues if i["code"] == "ZOO_FIXTURES_MARKERLESS"]
    assert len(obs) == 1 and not obs[0]["blocking"]
    assert "7 of 25" in obs[0]["message"] and "18 marker" in obs[0]["message"]

    # The other two shells in the same run have no markerless fixtures and
    # must stay silent -- an observation on every index is noise.
    clinic = _index(tmp_path, "clinic_a01", fixtures_built=15,
                    emitter_markers=15, markerless_fixtures=0,
                    placements=_places(15, 0), tool_version="1.1.1")
    assert ad.normalize_validation([clinic]) == []


def test_zoo_fixtures_pre_094_index_still_holds_the_v030_rule(tmp_path):
    """An index with no `markerless_fixtures` key reads it as 0, which is the
    old check to the bit: cold run 9060 built this same shell at 18/18."""
    ad = ZooAdapter()
    old_ok = _index(tmp_path, "a", fixtures_built=18, emitter_markers=18,
                    placements=_places(18, 0), tool_version="0.92.0")
    assert ad.normalize_validation([old_ok]) == []

    # Markers short with nothing declaring why: still a blocker, which is the
    # failure the contract exists for.
    old_bad = _index(tmp_path, "b", fixtures_built=18, emitter_markers=11,
                     tool_version="0.92.0")
    codes = {i["code"] for i in ad.normalize_validation([old_bad]) if i["blocking"]}
    assert codes == {"ZOO_FIXTURES_MARKER_MISMATCH"}


def test_zoo_fixtures_unaccounted_placements_block(tmp_path):
    """The three numbers are present and do not add up."""
    ad = ZooAdapter()
    idx = _index(tmp_path, "c", fixtures_built=25, emitter_markers=18,
                 markerless_fixtures=3, tool_version="1.1.1")
    issues = [i for i in ad.normalize_validation([idx]) if i["blocking"]]
    assert [i["code"] for i in issues] == ["ZOO_FIXTURES_MARKER_MISMATCH"]
    assert "4 placement(s) are unaccounted for" in issues[0]["message"]


def test_zoo_fixtures_counts_must_tally_with_the_placements(tmp_path):
    """The arithmetic alone is an identity on anything Zoo wrote -- the
    placements are the independent second opinion, and disagreeing with them
    is the only way a modern index can fail this gate."""
    ad = ZooAdapter()
    idx = _index(tmp_path, "d", fixtures_built=25, emitter_markers=18,
                 markerless_fixtures=7, placements=_places(19, 6),
                 tool_version="1.1.1")
    codes = {i["code"] for i in ad.normalize_validation([idx]) if i["blocking"]}
    assert codes == {"ZOO_FIXTURES_MARKER_TALLY_MISMATCH"}


def test_zoo_fixtures_unreadable_counts_fail_rather_than_pass(tmp_path):
    """`isinstance(built, int)` guarded the old comparison, so an index whose
    `fixtures_built` was null, a string, or absent went through unchecked and
    the gate reported clean about a file it could not read."""
    ad = ZooAdapter()
    for value in (None, "25", 25.0, True):
        idx = _index(tmp_path, "e", fixtures_built=value, emitter_markers=18,
                     markerless_fixtures=7)
        codes = {i["code"] for i in ad.normalize_validation([idx])
                 if i["blocking"]}
        assert codes == {"ZOO_FIXTURES_INDEX_UNREADABLE"}, value

    # ...and the same for the two counts the sum is taken from.
    idx = _index(tmp_path, "f", fixtures_built=25, emitter_markers=18,
                 markerless_fixtures="seven")
    codes = {i["code"] for i in ad.normalize_validation([idx]) if i["blocking"]}
    assert codes == {"ZOO_FIXTURES_INDEX_UNREADABLE"}


def test_lux_gate_normalization_blocks_and_passes(tmp_path):
    ad = LuxAdapter()
    rep = tmp_path / "fixture_gate.report.json"

    rep.write_text(json.dumps({
        "markers": 4, "spawnable": 4, "spawned": 3,
        "colocation_errors": ["1 spawned lamp(s) sit more than 0.10 m..."],
        "powered": {"kill": True, "restore": False}}))
    codes = {i["code"] for i in ad.normalize_validation([rep]) if i["blocking"]}
    assert codes == {"LUX_FIXTURE_SPAWN_MISMATCH", "LUX_FIXTURE_COLOCATION",
                     "LUX_FIXTURE_POWER_GATE"}

    rep.write_text(json.dumps({
        "markers": 20, "spawnable": 20, "spawned": 20,
        "colocation_errors": [], "powered": {"kill": True, "restore": True}}))
    assert [i for i in ad.normalize_validation([rep]) if i["blocking"]] == []

    rep.write_text(json.dumps({
        "markers": 0, "spawnable": 0, "spawned": 0,
        "colocation_errors": [], "powered": {"kill": True, "restore": True}}))
    issues = ad.normalize_validation([rep])
    assert any(i["code"] == "LUX_NO_FIXTURE_MARKERS" and not i["blocking"]
               for i in issues)


def test_factory_manifest_lockstep(tmp_path):
    (tmp_path / "zoo").mkdir()
    (tmp_path / "zoo" / "VERSION").write_text("0.30.1\n")
    (tmp_path / "lux").mkdir()
    (tmp_path / "lux" / "VERSION").write_text("Lux 0.15.2\n")
    manifest = {
        "factory_version": "1.0.0",
        "tools": {"zoo": {"version": "0.30.1"},
                  "lux": {"version": "0.15.2"}}}
    (tmp_path / "factory.manifest.json").write_text(json.dumps(manifest))

    results = {r.adapter_id: r for r in contracts.verify_manifest(tmp_path)}
    assert results["zoo"].status == contracts.OK
    assert results["lux"].status == contracts.OK  # display prefix stripped

    (tmp_path / "lux" / "VERSION").write_text("Lux 0.16.0\n")
    results = {r.adapter_id: r for r in contracts.verify_manifest(tmp_path)}
    assert results["lux"].status == contracts.DRIFT
