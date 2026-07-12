"""Stub Lot (0.18.0 CLI shape): python lot.py <site_spec.json> <out> [--walkable] [--navqa]."""
import json, sys
from pathlib import Path

def main():
    args = [a for a in sys.argv[1:]]
    pos = [a for a in args if not a.startswith("--")]
    spec_path = pos[0]
    out = Path(pos[1]) if len(pos) > 1 else Path(".")
    walkable = "--walkable" in args
    navqa = "--navqa" in args
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(spec_path).stem
    try:
        spec = json.loads(Path(spec_path).read_text())
    except Exception:
        spec = {}
    gameplay = {
        "site": {"stem": stem}, "buildings": spec.get("buildings", []),
        "rooms": [], "markers": [], "objectives": [], "encounters": [],
        "tactical": {"findings": []},
        "pacing": {"mode": "heist", "estimate_expected_min": 6.4,
                   "range_min": "4.1-8.6 min", "target_min": "7-12 min",
                   "status": "partly outside target (range straddles the window)"},
    }
    (out / f"{stem}.site.gameplay.json").write_text(json.dumps(gameplay, sort_keys=True))
    (out / f"{stem}.tscn").write_text('[gd_scene format=3]\n[node name="Site" type="Node3D"]\n')
    (out / f"{stem}.site.lights.json").write_text(json.dumps({"lights": []}, sort_keys=True))
    if walkable:
        (out / f"{stem}_walk.tscn").write_text('[gd_scene format=3]\n[node name="SiteWalk" type="Node3D"]\n')
    if navqa:
        (out / f"{stem}_navqa.tscn").write_text('[gd_scene format=3]\n[node name="SiteNavQA" type="Node3D"]\n')
    print(f"[lot] assembled '{Path(spec_path).name}' -> {stem}.site.gameplay.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
