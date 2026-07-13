"""Drive the REAL Siliconight tools through the rebound Level Factory adapters.

Each test resolves the real repo, builds the adapter's planned command, runs it
against the tool's own bundled example, and asserts the adapter's expected
outputs are produced. This is the TDD 37.5 real-tool smoke — it proves the
adapters invoke the real CLIs correctly (not just the stubs).

Run with:  LF_TOOLS_DIR=/path/to/tools pytest tests/real_tools -q
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _run_adapter(adapter, job_spec, repo, work):
    ctx = {"repository": str(repo), "work_dir": str(work),
           "python_executable": sys.executable}
    problems = adapter.validate_configuration(job_spec, ctx)
    assert not problems, problems
    cmd = adapter.plan_commands(job_spec, ctx)[0]
    env = {**os.environ, "PYTHONPATH": str(repo)}
    proc = subprocess.run(cmd.argv(), cwd=str(cmd.working_directory), env=env,
                          capture_output=True, text=True, timeout=300)
    outs = list(adapter.collect_outputs(job_spec, ctx))
    names = {p.name for p in outs}
    return proc, cmd, outs, names


def test_real_dispatch(tool_root):
    from adapters.dispatch import DispatchAdapter
    repo = tool_root("dispatch/__main__.py")
    # dispatch package lives at <root>/dispatch; the mission example is bundled.
    example = repo / "examples" / "gas_station_robbery_001" / "dispatch.mission.json"
    if not example.exists():
        pytest.skip("dispatch example mission not present")
    adapter = DispatchAdapter()
    # Probe the real contract command.
    probe = adapter.probe({"repository": str(repo), "python_executable": sys.executable})
    assert probe.available, probe.problems
    assert probe.tool_version  # real version string from `dispatch contract`

    work = repo / "_lf_smoke_out"
    job = {"mission_spec_path": str(example), "mode": "shell-handoff", "inputs": {}}
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # The adapter's real validation normalization runs on real outputs.
    issues = adapter.normalize_validation(outs)
    assert all("code" in i for i in issues)


def test_real_lot(tool_root, tmp_path):
    from adapters.lot import LotAdapter
    repo = tool_root("lot.py")
    spec = repo / "specs" / "gs_heist.json"
    if not spec.exists():
        pytest.skip("lot example spec not present")
    adapter = LotAdapter()
    job = {"site_spec_path": str(spec), "walkable": True}
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, tmp_path / "out")
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # Pacing is surfaced as a non-blocking estimate.
    issues = adapter.normalize_validation(outs)
    assert all(not i["blocking"] or i["severity"] == "blocker" for i in issues)


def test_real_dispatch_handoff_from_lf_staged_inputs(tool_root, tmp_path):
    """The end-to-end LF bridge: real Lot output + LF's dispatch-input staging
    fed to a real `dispatch build`. This is the stage that was previously broken
    (LF assembled an invalid spec against an assumed contract). Asserts a real
    handoff with no blockers."""
    import json, os, subprocess
    from packages.staging.dispatch_inputs import stage_dispatch_inputs
    lot_repo = tool_root("lot.py")
    disp_repo = tool_root("dispatch/__main__.py")

    # DC build needs Blender; use a realistic DC-schema gameplay fixture.
    deli = tmp_path / "deli"; deli.mkdir()
    (deli / "shell.gameplay.json").write_text(json.dumps({
        "up_axis": "z",
        "markers": [{"id": "AUTO_DOOR", "type": "door", "x": 0, "y": -1.5, "z": 0},
                    {"id": "AUTO_COVER", "type": "cover_low", "x": 3, "y": 2, "z": 0}],
        "objectives": [{"id": "take", "type": "objective", "x": -4, "y": 5, "z": 0,
                        "objective": "grab_the_take"}],
        "loot": [{"id": "reg", "type": "loot", "x": 2, "y": 1, "z": 0}], "props": []}))
    (deli / "shell.glb").write_bytes(b"glTF\x02\x00\x00\x00shell")

    # Real Lot.
    lot_out = tmp_path / "lot"; lot_out.mkdir()
    (tmp_path / "site.json").write_text(json.dumps({
        "name": "m1", "up_axis": "z",
        "buildings": [{"id": "b0", "glb": "b0.glb",
                       "gameplay": str(deli / "shell.gameplay.json"), "at": [0, 0], "rot": 0}]}))
    env = {**os.environ, "PYTHONPATH": str(lot_repo)}
    r = subprocess.run([sys.executable, "lot.py", str(tmp_path / "site.json"),
                        str(lot_out), "--walkable"], cwd=str(lot_repo), env=env,
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    lot_gp = next(lot_out.glob("*.site.gameplay.json"))

    # LF staging.
    stage = tmp_path / "stage"
    m = stage_dispatch_inputs(stage, deli_gameplay=deli / "shell.gameplay.json",
        shell_glb=deli / "shell.glb", lot_gameplay=lot_gp, mission_id="m1", theme="delco")

    # Valid v0.2 spec (mirrors _write_dispatch_spec) + real dispatch build.
    spec = {"schema": "dispatch.mission.v0.2", "mission_id": "m1", "title": "M1",
            "engine": "godot_4_7", "mode": "online_coop_pve",
            "players": {"min": 1, "max": 4, "preferred": 4},
            "networking": {"model": "server_authoritative", "critical_state_owner": "server"},
            "theme": "delco", "inputs": m,
            "mission_flow": [{"step": "spawn", "location_tag": "mission_start"},
                             {"step": "extract", "location_tag": "extraction"}],
            "validation": {"require_online_runtime_readiness": False,
                           "require_all_objectives_reachable": False,
                           "require_all_players_spawn_valid": True,
                           "require_ai_navmesh": False, "require_performance_budget": False}}
    (stage / "dispatch.mission.json").write_text(json.dumps(spec, indent=2))
    out = tmp_path / "handoff"
    denv = {**os.environ, "PYTHONPATH": str(disp_repo)}
    rd = subprocess.run([sys.executable, "-m", "dispatch", "build",
                         str(stage / "dispatch.mission.json"), "--mode", "shell-handoff",
                         "--out", str(out), "--strict-licenses"],
                        cwd=str(disp_repo), env=denv, capture_output=True, text=True, timeout=120)
    assert rd.returncode == 0, (rd.stdout + rd.stderr)[-1000:]
    for f in ("mission.tscn", "mission_manifest.json", "gameplay_anchors.json",
              "HANDOFF.md", "build.lock.json"):
        assert (out / f).exists(), f"missing handoff artifact: {f}"
    report = json.loads((out / "validation" / "report.json").read_text())
    assert not report.get("blockers"), report.get("blockers")


def test_real_patina(tool_root, tmp_path):
    from adapters.patina import PatinaAdapter
    repo = tool_root("patina/cli.py")
    glb = repo / "examples" / "shell.glb"
    if not glb.exists():
        pytest.skip("patina example shell.glb not present")
    adapter = PatinaAdapter()
    job = {"input_glb": str(glb), "art_mode": "vertex-color", "theme": "default"}
    work = tmp_path / "out"; work.mkdir()
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # Patina must preserve collision (prints "collision N tris (untouched)").
    assert "untouched" in (proc.stdout + proc.stderr)


def test_real_patina_dressing_emits_manifest_for_zoo(tool_root, tmp_path):
    """The patina --dressing --anchors pass must emit the <stem>.patina.dressing.json
    (schema patina-dressing/1) that Zoo's --dress consumes."""
    import json
    from adapters.patina import PatinaAdapter
    repo = tool_root("patina/cli.py")
    glb = repo / "examples" / "shell.glb"
    if not glb.exists():
        pytest.skip("patina example shell.glb not present")
    adapter = PatinaAdapter()
    job = {"input_glb": str(glb), "art_mode": "vertex-color", "theme": "default",
           "dressing": True, "panel_size": 1.2, "panel_gap": 0.03}
    work = tmp_path / "out"; work.mkdir()
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    dressing = next((p for p in outs if p.name.endswith(".patina.dressing.json")), None)
    assert dressing is not None, "patina dressing did not emit a dressing manifest"
    schema = json.loads(dressing.read_text()).get("schema", "")
    assert schema.startswith("patina-dressing/"), schema


def test_real_pixelcoat(tool_root, tmp_path):
    import json
    from adapters.pixelcoat import PixelcoatAdapter
    repo = tool_root("pixelcoat/cli/main.py")
    # A recipe needs a source image; synthesize a minimal one.
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available to synthesize a pixelcoat source image")
    src = tmp_path / "src.png"
    Image.new("RGB", (32, 32), (90, 120, 140)).save(src)
    recipe = tmp_path / "theme.recipe.json"
    recipe.write_text(json.dumps({
        "asset_id": "theme", "source": {"path": "src.png"},
        "palette": {"colors": ["#0b1020", "#233a52", "#88b0ac", "#f2f6ec"]}}))
    adapter = PixelcoatAdapter()
    job = {"recipe_path": str(recipe), "source_path": str(src), "asset_id": "theme"}
    work = tmp_path / "out"; work.mkdir()
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    rel = {p.relative_to(work).as_posix() for p in outs}
    expected = {e.replace("\\", "/") for e in cmd.expected_outputs}
    assert expected <= rel, expected - rel


def test_real_zoo_plan(tool_root, tools_base, tmp_path):
    """Zoo geometry builds need Blender; the headless --kit --plan path is the
    runnable pre-build gate and is what the adapter emits in plan_only mode."""
    from adapters.zoo import ZooAdapter
    repo = tool_root("tools/zoo_cli.py")
    slots = next((p for p in tools_base.rglob("*.slots.json")), None)
    if slots is None:
        pytest.skip("no slots.json available for a zoo plan")
    adapter = ZooAdapter()
    job = {"mode": "kit", "plan_only": True, "slots_path": str(slots),
           "theme": "delco", "seed": 3}
    work = tmp_path / "out"; work.mkdir()
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert cmd.resource_class == "python_cpu"  # plan is headless


def test_real_deli_new_level(tool_root):
    """Deli's build.py needs Blender; new_level.py (spec generation) is headless
    and is the container-runnable half of the two-step. This drives the real
    new_level via the adapter's first planned command and asserts the spec is
    written, then confirms the build command targets the work dir + Blender."""
    from adapters.deli_counter import DeliCounterAdapter, _preset_for
    repo = tool_root("new_level.py")
    adapter = DeliCounterAdapter()
    # Archetype -> real preset mapping resolves to a valid DC preset.
    preset = _preset_for("urban_bank")
    assert preset == "bank"

    work = repo / "_lf_smoke_work"
    ctx = {"repository": str(repo), "work_dir": str(work),
           "python_executable": sys.executable, "blender_executable": "/usr/bin/blender"}
    job = {"archetype": "urban_bank", "mode": "heist", "seed": 4242,
           "level_name": "lf_realsmoke"}
    cmds = adapter.plan_commands(job, ctx)
    # Step 1: real new_level.
    env = {**os.environ, "PYTHONPATH": str(repo)}
    r1 = subprocess.run(cmds[0].argv(), cwd=str(cmds[0].working_directory), env=env,
                        capture_output=True, text=True, timeout=90)
    spec = repo / "specs" / "lf_realsmoke_4242.json"
    try:
        assert r1.returncode == 0, (r1.stdout + r1.stderr)[-800:]
        assert spec.exists(), "new_level did not write the spec"
        # Step 2 (build) is Blender-gated: assert its shape, don't run it.
        build_argv = cmds[1].argv()
        assert str(spec) in build_argv
        assert "--out" in build_argv and "--blender" in build_argv
        assert cmds[1].resource_class == "blender"
    finally:
        spec.unlink(missing_ok=True)


def test_real_lasertag_runner_and_invocation(tool_root, tmp_path):
    """Laser Tag needs Godot to execute; in-container we verify the real runner
    exists and the adapter stages a project + emits the real `-s run_map_eval.gd`
    invocation pointing at it. Execution is on the user's Godot hardware."""
    from adapters.laser_tag import LaserTagAdapter
    repo = tool_root("addons/laser_tag_tool/runners/run_map_eval.gd")
    runner = repo / "addons" / "laser_tag_tool" / "runners" / "run_map_eval.gd"
    scenario = repo / "addons" / "laser_tag_tool" / "resources" / "default_laser_tag_scenario.tres"
    assert runner.exists(), "real run_map_eval.gd runner missing"
    assert scenario.exists(), "default scenario resource missing"

    # A stand-in walkable scene (Lot output) to stage.
    scene = tmp_path / "site_walk.tscn"
    scene.write_text('[gd_scene format=3]\n[node name="SiteWalk" type="Node3D"]\n')
    adapter = LaserTagAdapter()
    job = {"seed": 1997, "run_count": 25,
           "evaluation_scene": str(scene),
           "addon_dir": str(repo / "addons" / "laser_tag_tool"),
           "staging_dir": str(tmp_path / "stage")}
    ctx = {"work_dir": str(tmp_path / "out"), "godot_executable": "godot",
           "repository": str(repo)}
    (tmp_path / "out").mkdir()
    cmd = adapter.plan_commands(job, ctx)[0]
    argv = cmd.argv()
    # Real invocation shape.
    assert "-s" in argv
    assert "res://addons/laser_tag_tool/runners/run_map_eval.gd" in argv
    assert "--map" in argv and "--scenario" in argv and "--output" in argv
    # Staging assembled the addon + scene into the project.
    proj = tmp_path / "stage"
    assert (proj / "project.godot").exists()
    assert (proj / "addons" / "laser_tag_tool" / "runners" / "run_map_eval.gd").exists()
    assert (proj / "level.tscn").exists()
    # The staged project must carry the global class cache, else Godot can't
    # resolve the runner's class_name types (LT_MapEvalHarness/LT_TestScenario).
    cache = proj / ".godot" / "global_script_class_cache.cfg"
    assert cache.exists(), "class cache not staged — Godot would fail to parse the runner"
    ctext = cache.read_text()
    assert "LT_MapEvalHarness" in ctext and "LT_TestScenario" in ctext


def test_real_lux_addon_and_driver_invocation(tool_root, tmp_path):
    """Lux is in-engine only; in-container we verify the real addon exists, LF's
    headless driver is staged, and the adapter emits the real `-s run_lux_apply.gd`
    invocation. Execution + preview capture are on the user's Godot hardware."""
    from adapters.lux import LuxAdapter
    repo = tool_root("addons/lux/plugin.cfg")
    addon = repo / "addons" / "lux"
    assert (addon / "runtime" / "lux_root.gd").exists(), "real LuxRoot missing"
    driver = Path(ROOT) / "assets" / "godot" / "run_lux_apply.gd"
    assert driver.exists(), "LF Lux driver run_lux_apply.gd missing"
    # The driver uses the real LuxRoot API.
    driver_text = driver.read_text()
    assert "LuxRoot" in driver_text and "blend_to_preset" in driver_text

    scene = tmp_path / "site.tscn"
    scene.write_text('[gd_scene format=3]\n[node name="Site" type="Node3D"]\n')
    adapter = LuxAdapter()
    job = {"preset": "gothic_street_night", "composed_scene": str(scene),
           "addon_dir": str(addon), "driver_src": str(driver),
           "staging_dir": str(tmp_path / "stage")}
    ctx = {"work_dir": str(tmp_path / "out"), "godot_executable": "godot",
           "repository": str(repo)}
    (tmp_path / "out").mkdir()
    cmd = adapter.plan_commands(job, ctx)[0]
    argv = cmd.argv()
    assert "-s" in argv and "res://run_lux_apply.gd" in argv
    assert "--scene" in argv and "--preset" in argv
    proj = tmp_path / "stage"
    assert (proj / "run_lux_apply.gd").exists()  # driver staged at project root
    assert (proj / "addons" / "lux" / "runtime" / "lux_root.gd").exists()
    cache = proj / ".godot" / "global_script_class_cache.cfg"
    assert cache.exists(), "class cache not staged — Godot would fail to resolve LuxRoot"
    assert "LuxRoot" in cache.read_text()
