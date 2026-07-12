"""Stub Zoo (v0.27.0): kit build or collision-free dressing build."""
import argparse, json
from pathlib import Path

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
    (out / f"zoo_{kind}.glb").write_bytes(b"glTF-zoo-" + kind.encode())
    manifest = {"schema": "zoo.asset/1", "kind": kind, "seed": a.seed}
    if a.command == "dress":
        # Dressing covers are collision-free by contract.
        manifest["dressing"] = [{"id": "panel_field_0", "collision": "none"}]
    (out / "zoo.manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
