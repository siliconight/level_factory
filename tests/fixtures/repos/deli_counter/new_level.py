"""Stub Deli Counter new_level (0.74.2 shape): --preset --name --mode --force -> specs/<name>.json."""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preset", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--mode", default="heist")
    p.add_argument("--floors", type=int, default=2)
    p.add_argument("--basement", action="store_true")
    p.add_argument("--no-basement", dest="no_basement", action="store_true")
    p.add_argument("--vertex-nuance", dest="vertex_nuance", action="store_true")
    p.add_argument("--rarity", default="")
    p.add_argument("--force", action="store_true")
    a, _ = p.parse_known_args()
    specs = HERE / "specs"; specs.mkdir(parents=True, exist_ok=True)
    spec = {"schema": "deli.level.v1", "name": a.name, "preset": a.preset,
            "mode": a.mode, "floors": a.floors,
            "basement": (a.basement and not a.no_basement),
            "vertex_nuance": a.vertex_nuance, "rarity": a.rarity}
    (specs / f"{a.name}.json").write_text(json.dumps(spec, sort_keys=True))
    print(f"wrote {specs / (a.name + '.json')}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
