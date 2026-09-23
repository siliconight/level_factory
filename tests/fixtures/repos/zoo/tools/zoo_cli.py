"""Stub Zoo (0.27.0 CLI shape): tools/zoo_cli.py --build-kit/--dress/--kit --plan."""
import argparse, json, sys
from pathlib import Path



def _stub_glb(tag="stub"):
    """A real, minimal glTF 2.0 binary.

    These stubs used to emit `b"glTF-..."` -- four bytes of magic and then
    nothing a parser accepts. Harmless while nothing in the export read a
    GLB's contents; a hard failure once the reference gate read every one of
    them, because an unreadable `.glb` is a finding there rather than a skip.
    A stub that emits something the pipeline cannot parse is not standing in
    for the tool.
    """
    import json as _json, struct as _struct
    doc = {"asset": {"version": "2.0", "generator": str(tag)}, "scene": 0,
           "scenes": [{"nodes": [0]}], "nodes": [{"name": str(tag)}]}
    payload = _json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    chunk = _struct.pack("<II", len(payload), 0x4E4F534A) + payload
    return _struct.pack("<III", 0x46546C67, 2, 12 + len(chunk)) + chunk

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
        (out / f"{scope}_fixtures.glb").write_bytes(_stub_glb("zoo-fixtures"))
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
        # THE GEOMETRY, which this branch never published. Real Zoo's
        # --dress returns `res["files"]["glb"]` and prints it;
        # `presentation_compose` requires a `*_dressing.glb` in this
        # job's out/. Writing the index alone made `zoo_dressing_build`
        # report success and compose fail two stages later. The
        # --fixtures branch above has always written its own .glb --
        # which is why `lux_fixture_gate` passed in the same run.
        (out / f"{bid}_dressing.glb").write_bytes(_stub_glb("zoo-dressing"))
    else:
        bid = _bid(a.build_kit)
        idx = out / f"{bid}_kit.built.json"
        idx.write_text(json.dumps(
            {"mode": "kit", "building_id": bid, "theme": a.theme, "modules": [], "n_fail": 0}, sort_keys=True))
        (out / f"{bid}_wall.glb").write_bytes(_stub_glb("zoo-wall"))
    print(f"[zoo] index: {idx}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
