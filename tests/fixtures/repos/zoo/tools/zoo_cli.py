"""Stub Zoo (0.27.0 CLI shape): tools/zoo_cli.py --build-kit/--dress/--kit --plan."""
import argparse, json, sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(prog="zoo_cli")
    p.add_argument("--build-kit", dest="build_kit", default="")
    p.add_argument("--dress", default="")
    p.add_argument("--kit", default="")
    p.add_argument("--fixtures", default="")
    p.add_argument("--fixture-types", dest="fixture_types", nargs="*", default=None)
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

    def _bid(path):
        try:
            return str(json.load(open(path)).get("building_id") or "building")
        except Exception:
            return "building"

    if a.fixtures:
        try:
            man = json.load(open(a.fixtures))
        except Exception:
            man = {}
        scope = str(man.get("building_id") or man.get("site") or "scene")
        n = len([x for x in man.get("anchors", [])
                 if x.get("type") in ("fluorescent", "streetlight", "sign", "wall_pack")])
        idx = out / f"{scope}_fixtures.built.json"
        idx.write_text(json.dumps(
            {"mode": "fixtures", "scope_id": scope, "fixtures_built": n,
             "emitter_markers": n, "marker_prefix": "LuxEmit",
             "skipped": [], "tool_version": "0.30.1"}, sort_keys=True))
        (out / f"{scope}_fixtures.glb").write_bytes(b"glTF-zoo-fixtures-stub")
        print(f"[zoo] index: {idx}")
        return 0
    if a.dress:
        try:
            man = json.load(open(a.dress))
        except Exception:
            man = {}
        schema = man.get("schema", "")
        if not str(schema).startswith("patina-dressing/"):
            print(f"[zoo] not a Patina dressing manifest (schema={schema!r})", file=sys.stderr)
            return 4
        bid = _bid(a.dress)
        idx = out / f"{bid}_dressing.built.json"
        idx.write_text(json.dumps(
            {"mode": "dress", "building_id": bid, "n_fail": 0,
             "dressing": [{"id": "curb_0", "collision": "none"}]}, sort_keys=True))
    else:
        bid = _bid(a.build_kit)
        idx = out / f"{bid}_kit.built.json"
        idx.write_text(json.dumps(
            {"mode": "kit", "building_id": bid, "theme": a.theme, "modules": [], "n_fail": 0}, sort_keys=True))
        (out / f"{bid}_wall.glb").write_bytes(b"glTF-zoo-stub")
    print(f"[zoo] index: {idx}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
