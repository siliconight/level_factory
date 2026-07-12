"""Stub Deli Counter (v0.74.0 contract shape) for integration tests."""
import argparse, json, sys
from pathlib import Path

def cmd_contract():
    print(json.dumps({"tool_version": "0.74.0", "gameplay_schema": "1.21.0",
                      "capabilities": ["generate_building", "validate_building",
                                       "combat_audit", "floorplan_preview",
                                       "slot_contract", "deterministic_build"]}))
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "contract":
        return cmd_contract()
    p = argparse.ArgumentParser()
    p.add_argument("command")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", required=True)
    p.add_argument("--formats", default="glb")
    p.add_argument("--spec", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--archetype", default="")
    p.add_argument("--blender", default="")
    p.add_argument("--emit-gameplay", action="store_true")
    p.add_argument("--emit-slots", action="store_true")
    p.add_argument("--emit-lights", action="store_true")
    p.add_argument("--combat-audit", default="")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    s = a.seed
    (out / "shell.glb").write_bytes(b"glTF-stub-" + str(s).encode())
    (out / "shell.gameplay.json").write_text(json.dumps({
        "schema": "1.21.0", "seed": s,
        "stair_systems": [{"id": "s1", "role": "primary"}],
        "ladders": [], "platforms": [], "fire_escapes": [],
        "anchors": [{"id": f"vault_door_{s}", "type": "breach_point",
                     "required_authority": "server"}],
        "intel": []}, sort_keys=True))
    (out / "shell.slots.json").write_text(json.dumps(
        {"slots": [{"id": "slot_a", "kind": "vault"}]}, sort_keys=True))
    (out / "shell.manifest.json").write_text(json.dumps(
        {"seed": s, "archetype": a.archetype, "theme": a.theme}, sort_keys=True))
    (out / "shell.lights.json").write_text(json.dumps(
        {"lights": [{"id": "l1", "kind": "point"}]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
