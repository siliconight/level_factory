"""Stub Pixelcoat (0.2.0 CLI shape):

  build <recipe> --output <dir>            legacy single-recipe pack
  theme-library --theme <t> --out <dir>    themed skins library: one
                                           <kind>_<theme>/ pack per curated
                                           material (what the Zoo kit resolves
                                           from via --skins/--theme).

Emits pixelcoat-pack/1 manifests with their map files written alongside, so the
LF pixelcoat adapter's resolve-check (normalize_validation) passes.
"""
import argparse, json, sys
from pathlib import Path

# A representative curated set -- enough kinds for the Zoo kit to resolve and
# for the adapter to see a real library. Mirrors the real theme profiles.
_KINDS = ("brick", "concrete", "glass", "glass_facade", "metal", "tile", "wood")


def _write_pack(pack_dir, pack_id, theme, transparency=None):
    pack_dir.mkdir(parents=True, exist_ok=True)
    maps = {}
    for m in ("albedo", "normal", "roughness"):
        fn = f"{pack_id}_{m}.png"
        (pack_dir / fn).write_bytes(b"\x89PNG\r\n\x1a\n" + m.encode())
        maps[m] = fn
    pack = {"schema": "pixelcoat-pack/1", "id": pack_id, "theme": theme,
            "maps": maps, "meters_per_tile": 2.0, "tileable": ["x", "y"]}
    if transparency:
        pack["import_hints"] = {"transparency": transparency}
    (pack_dir / f"{pack_id}.pack.json").write_text(
        json.dumps(pack, sort_keys=True))


def _build(a):
    try:
        recipe = json.loads(Path(a.recipe).read_text())
    except Exception:
        recipe = {}
    asset_id = recipe.get("asset_id", "theme")
    asset_dir = Path(a.output) / asset_id
    _write_pack(asset_dir, asset_id, "")
    (asset_dir / "build_report.json").write_text(
        json.dumps({"asset_id": asset_id}, sort_keys=True))
    if a.json:
        print(json.dumps({"tool_version": "0.11.0", "asset_id": asset_id,
                          "files": [f"{asset_id}.pack.json"]}, sort_keys=True))
    return 0


def _theme_library(a):
    out = Path(a.out)
    packs = []
    for kind in _KINDS:
        pack_id = f"{kind}_{a.theme}"
        trans = ({"opacity": 0.4, "ior": 1.45, "alpha_mode": "BLEND"}
                 if kind == "glass" else None)
        _write_pack(out / pack_id, pack_id, a.theme, transparency=trans)
        packs.append(pack_id)
    if a.json:
        print(json.dumps({"tool_version": "0.11.0", "theme": a.theme,
                          "out_dir": str(out), "packs": packs,
                          "kind_count": len(packs)}, sort_keys=True))
    return 0


def main():
    p = argparse.ArgumentParser(prog="pixelcoat")
    sub = p.add_subparsers(dest="command")

    b = sub.add_parser("build")
    b.add_argument("recipe")
    b.add_argument("--output", default="./build")
    b.add_argument("--force", action="store_true")
    b.add_argument("--json", action="store_true")

    t = sub.add_parser("theme-library")
    t.add_argument("--theme", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--profile", default="")
    t.add_argument("--grammars", default="")
    t.add_argument("--size", type=int, default=512)
    t.add_argument("--seed", type=int, default=1999)
    t.add_argument("--json", action="store_true")

    a, _ = p.parse_known_args()
    if a.command == "build":
        return _build(a)
    if a.command == "theme-library":
        return _theme_library(a)
    print("usage: pixelcoat {build|theme-library} ...", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
