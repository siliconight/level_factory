"""Stub Zoo (0.27.0 CLI shape): tools/zoo_cli.py --build-kit/--dress/--kit --plan."""
import argparse, json, sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(prog="zoo_cli")
    p.add_argument("--build-kit", dest="build_kit", default="")
    p.add_argument("--dress", default="")
    p.add_argument("--kit", default="")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--skins", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--seed", default="")
    p.add_argument("--roof-props", dest="roof_props", default="")
    p.add_argument("--density", default="")
    p.add_argument("--out", default="")
    a, _ = p.parse_known_args()

    if a.plan:  # headless Intent + BuildPlan, no geometry
        print("[zoo] kit for 'stub' (theme=%s, style=01):" % (a.theme or "delco"))
        print("[zoo]   Intent + BuildPlan (dry-run)")
        return 0
    if not a.out:
        print("[zoo] a build needs --out", file=sys.stderr); return 3
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.dress:
        try:
            man = json.load(open(a.dress))
        except Exception:
            man = {}
        schema = man.get("schema", "")
        if not str(schema).startswith("patina-dressing/"):
            print(f"[zoo] not a Patina dressing manifest (schema={schema!r})", file=sys.stderr)
            return 4
        (out / "zoo.manifest.json").write_text(json.dumps(
            {"mode": "dress", "dressing": [{"id": "curb_0", "collision": "none"}]}, sort_keys=True))
    else:
        (out / "zoo.manifest.json").write_text(json.dumps(
            {"mode": "kit", "theme": a.theme, "modules": []}, sort_keys=True))
        (out / "kit.glb").write_bytes(b"glTF-zoo-stub")
    print(f"[zoo] manifest: {out / 'zoo.manifest.json'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
