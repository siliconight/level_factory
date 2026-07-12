"""Stub Dispatch (0.3.0 CLI shape): python -m dispatch {contract,build} ...."""
import argparse, json, sys
from pathlib import Path

REAL_CONTRACT = {
    "tool": "dispatch", "version": "0.3.0", "contract": "dispatch.mission.v0.2",
    "modes": ["shell-handoff", "playtest", "preview-playtest", "runtime-adapter"],
    "schemas": ["dispatch.manifest.v0.2", "dispatch.report.v0.2"],
    "capabilities": ["assemble_shell", "validate_shell", "export_godot",
                     "shell_handoff", "portable_resource_closure",
                     "dependency_manifest", "license_aggregation"],
}

def cmd_contract():
    print(json.dumps(REAL_CONTRACT, sort_keys=True))
    return 0

def cmd_build(argv):
    p = argparse.ArgumentParser(prog="dispatch build")
    p.add_argument("spec")
    p.add_argument("--out", required=True)
    p.add_argument("--mode", default="shell-handoff")
    p.add_argument("--include-preview", action="store_true")
    p.add_argument("--strict-licenses", action="store_true")
    a, _ = p.parse_known_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "validation").mkdir(parents=True, exist_ok=True)
    try:
        spec = json.loads(Path(a.spec).read_text())
    except Exception:
        spec = {}
    mission_id = spec.get("mission_id", "mission")

    (out / "mission.tscn").write_text(
        '[gd_scene format=3]\n[node name="MissionShell" type="Node3D"]\n')
    (out / "mission_manifest.json").write_text(json.dumps(
        {"mission_id": mission_id, "mode": a.mode, "schema": "dispatch.manifest.v0.2"}, sort_keys=True))
    (out / "resource_manifest.json").write_text(json.dumps(
        {"resources": [], "schema": "dispatch.resource_manifest.v0.2"}, sort_keys=True))
    (out / "gameplay_anchors.json").write_text(json.dumps(
        {"anchors": [{"id": "vault", "required_authority": "server"}]}, sort_keys=True))
    (out / "runtime_ownership_requirements.json").write_text(json.dumps(
        {"owned_by_runtime": ["mission_state", "replication", "persistence"]}, sort_keys=True))
    (out / "proposed_beat_graph.json").write_text(json.dumps({"beats": []}, sort_keys=True))
    (out / "navigation_hints.json").write_text(json.dumps({"hints": []}, sort_keys=True))
    (out / "build.lock.json").write_text(json.dumps(
        {"tool": "dispatch", "version": "0.3.0"}, sort_keys=True))
    (out / "HANDOFF.md").write_text(
        "# Handoff\n\nThis package is a shell-handoff. The production game runtime remains "
        "authoritative for mission progression, gameplay, AI, replication, and "
        "persistence. Runtime ownership requirements are listed as downstream "
        "requirements, not implemented here.\n")
    (out / "validation" / "report.json").write_text(json.dumps(
        {"readiness": 100, "status": "ready_for_handoff", "issues": []}, sort_keys=True))
    print(f"exported {out} (mode {a.mode})")
    print("readiness 100 (ready_for_handoff) — 0 blocker, 0 major, 0 moderate, 0 minor")
    return 0

def main():
    argv = sys.argv[1:]
    if not argv:
        print("usage: dispatch {contract,build}", file=sys.stderr); return 3
    cmd, rest = argv[0], argv[1:]
    if cmd == "contract":
        return cmd_contract()
    if cmd == "build":
        return cmd_build(rest)
    print(f"unknown dispatch command: {cmd}", file=sys.stderr)
    return 3

if __name__ == "__main__":
    raise SystemExit(main())
