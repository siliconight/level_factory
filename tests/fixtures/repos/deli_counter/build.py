"""Stub Deli Counter build (0.74.2 shape): build.py <spec> --out <path>.glb --blender <exe>.

The real build.py runs inside Blender; this stub writes the same output contract
(glb + gameplay/slots/lights/manifest sidecars next to --out) without Blender."""
import argparse, json, sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("spec")
    p.add_argument("--out", required=True)
    p.add_argument("--format", "-f", default="glb")
    p.add_argument("--blender", default="")
    a, _ = p.parse_known_args()
    try:
        spec = json.loads(Path(a.spec).read_text())
    except Exception:
        spec = {}
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    base = str(out)[:-4] if str(out).endswith(".glb") else str(out)
    out.write_bytes(b"glTF-deli-stub-" + spec.get("preset", "").encode())
    Path(base + ".gameplay.json").write_text(json.dumps({
        "schema": "1.21.0", "preset": spec.get("preset"),
        "stair_systems": [{"id": "s1", "role": "primary"}],
        "ladders": [], "platforms": [], "fire_escapes": [],
        "anchors": [{"id": "vault_door", "type": "breach_point",
                     "required_authority": "server"}],
        "intel": []}, sort_keys=True))
    Path(base + ".slots.json").write_text(json.dumps(
        {"version": "1", "building_id": spec.get("name", "b0"),
         "theme": spec.get("preset", ""),
         "slots": [{"id": "slot_a", "kind": "vault", "role": "trim"}]}, sort_keys=True))
    Path(base + ".lights.json").write_text(json.dumps(
        {"lights": [{"id": "l1", "kind": "point"}]}, sort_keys=True))
    Path(base + ".manifest.json").write_text(json.dumps(
        {"preset": spec.get("preset"), "mode": spec.get("mode")}, sort_keys=True))
    print(f"built {out} (+ gameplay/slots/lights/manifest)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
