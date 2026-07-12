"""Stub Lot (v0.17.x) for integration tests."""
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command")
    p.add_argument("--out", required=True)
    p.add_argument("--audit", default="json")
    p.add_argument("--walkable", action="store_true")
    p.add_argument("--nav-qa", action="store_true")
    p.add_argument("--building", action="append", default=[])
    p.add_argument("--lights", action="append", default=[])
    p.add_argument("--spec", default="")
    p.add_argument("--target-minutes", default="")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "site.tscn").write_text('[gd_scene format=3]\n[node name="Site" type="Node3D"]\n')
    (out / "site.gameplay.json").write_text(json.dumps(
        {"buildings": a.building, "merged_anchors": len(a.building)}, sort_keys=True))
    (out / "site.nav_hints.json").write_text(json.dumps({"nav": "hints"}, sort_keys=True))
    (out / "site.audit.json").write_text(json.dumps({"findings": []}, sort_keys=True))
    (out / "pacing.json").write_text(json.dumps(
        {"estimate_minutes": [25, 35], "note": "estimate"}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
