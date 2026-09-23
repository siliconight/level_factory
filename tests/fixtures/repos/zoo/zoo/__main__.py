"""Stub Zoo (v0.27.0): kit build or collision-free dressing build."""
import argparse, json
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
    p = argparse.ArgumentParser()
    p.add_argument("command")  # build | dress
    p.add_argument("--slots", default="")
    p.add_argument("--manifest", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--theme", default="")
    p.add_argument("--skins", default="")
    p.add_argument("--roof-props", action="store_true")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    kind = "structural" if a.command == "build" else "dressing"
    (out / f"zoo_{kind}.glb").write_bytes(_stub_glb("zoo-" + kind))
    manifest = {"schema": "zoo.asset/1", "kind": kind, "seed": a.seed}
    if a.command == "dress":
        # Dressing covers are collision-free by contract.
        manifest["dressing"] = [{"id": "panel_field_0", "collision": "none"}]
    (out / "zoo.manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
