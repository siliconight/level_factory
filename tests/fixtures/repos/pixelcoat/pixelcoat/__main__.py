"""Stub Pixelcoat (v0.2.0): emits a pixelcoat-pack/1 pack set."""
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command")
    p.add_argument("--recipes", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--theme", default="")
    p.add_argument("--palette", default="")
    p.add_argument("--force", action="store_true")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for role in ("albedo", "normal", "roughness"):
        (out / f"theme_{role}.png").write_bytes(b"PNG-stub-" + role.encode())
    (out / "theme.pack.json").write_text(json.dumps({
        "schema": "pixelcoat-pack/1",
        "maps": {"albedo": "theme_albedo.png", "normal": "theme_normal.png",
                 "roughness": "theme_roughness.png"},
        "tileable_axes": ["u", "v"], "meters_per_tile": 2.0, "theme": a.theme,
    }, sort_keys=True))
    (out / "theme.pixelcoat.json").write_text(json.dumps({"recipe": "theme"}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
