"""Stub Pixelcoat (0.2.0 CLI shape): python -m pixelcoat.cli.main build <recipe> --output <dir>."""
import argparse, json, sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(prog="pixelcoat")
    sub = p.add_subparsers(dest="command")
    b = sub.add_parser("build")
    b.add_argument("recipe")
    b.add_argument("--output", default="./build")
    b.add_argument("--force", action="store_true")
    b.add_argument("--json", action="store_true")
    a, _ = p.parse_known_args()
    if a.command != "build":
        print("usage: pixelcoat build <recipe>", file=sys.stderr); return 3
    try:
        recipe = json.loads(Path(a.recipe).read_text())
    except Exception:
        recipe = {}
    asset_id = recipe.get("asset_id", "theme")
    asset_dir = Path(a.output) / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    for m in ("albedo", "normal", "roughness"):
        (asset_dir / f"{asset_id}_{m}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + m.encode())
    pack = {"schema": "pixelcoat-pack/1", "asset_id": asset_id,
            "maps": {"albedo": f"{asset_id}_albedo.png",
                     "normal": f"{asset_id}_normal.png",
                     "roughness": f"{asset_id}_roughness.png"},
            "meters_per_tile": 2.0, "tileable": ["x", "y"]}
    (asset_dir / f"{asset_id}.pack.json").write_text(json.dumps(pack, sort_keys=True))
    (asset_dir / "build_report.json").write_text(json.dumps({"asset_id": asset_id}, sort_keys=True))
    if a.json:
        print(json.dumps({"tool_version": "0.9.0", "asset_id": asset_id,
                          "files": [f"{asset_id}.pack.json"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
