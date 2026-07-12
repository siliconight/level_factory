"""Stub Dispatch (v0.3.0, dispatch.mission.v0.2) for integration tests."""
import argparse, json, sys
from pathlib import Path

HANDOFF = (
    "This package contains a self-contained Godot 4.7 mission shell, "
    "presentation resources, gameplay anchors, proposed mission beats, and "
    "runtime integration requirements.\n\n"
    "Level Factory and its authoring tools are not required to consume this package.\n\n"
    "The production game runtime remains authoritative for mission progression, "
    "gameplay behavior, enemy AI, replication, persistence, late joining, "
    "reconnection, and online correctness.\n")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "contract":
        print(json.dumps({"tool_version": "0.3.0",
                          "mission_contract": "dispatch.mission.v0.2",
                          "modes": ["shell-handoff", "preview-playtest"]}))
        return 0
    p = argparse.ArgumentParser()
    p.add_argument("command")
    p.add_argument("spec")
    p.add_argument("--mode", default="shell-handoff")
    p.add_argument("--out", required=True)
    p.add_argument("--include-preview", action="store_true")
    p.add_argument("--strict-licenses", action="store_true")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "mission.tscn").write_text(
        '[gd_scene format=3]\n[node name="Mission" type="Node3D"]\n'
        '[node name="Functional" type="Node3D" parent="."]\n'
        '[node name="Presentation" type="Node3D" parent="."]\n'
        '[node name="Handoff" type="Node3D" parent="."]\n')
    (out / "mission_manifest.json").write_text(json.dumps(
        {"schema": "dispatch.mission.v0.2", "mode": a.mode}, sort_keys=True))
    (out / "gameplay_anchors.json").write_text(json.dumps(
        {"schema": "gameplay_anchors.v0.2",
         "anchors": [{"shell_id": "m/vault_door", "runtime_binding": None}]}, sort_keys=True))
    (out / "runtime_ownership_requirements.json").write_text(json.dumps(
        {"schema": "dispatch.runtime_ownership_requirements.v0.2",
         "anchors": [{"shell_id": "m/vault_door", "integration_status": "unimplemented",
                      "runtime_requirements": {"authoritative_owner": "server"}}]}, sort_keys=True))
    (out / "proposed_beat_graph.json").write_text(json.dumps(
        {"schema": "proposed_beat_graph.v0.2", "status": "proposed", "beats": []}, sort_keys=True))
    (out / "navigation_hints.json").write_text(json.dumps({"nav": "hints"}, sort_keys=True))
    (out / "build.lock.json").write_text(json.dumps(
        {"schema": "dispatch.build.lock.v0.2"}, sort_keys=True))
    (out / "HANDOFF.md").write_text(HANDOFF)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
