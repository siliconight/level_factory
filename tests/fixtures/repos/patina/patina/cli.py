"""Stub Patina (0.18.0 CLI shape): patina <shell.glb> [--dressing ...] --out <path>.patina.glb."""
import json, sys
from pathlib import Path

def main():
    args = sys.argv[1:]
    pos = [a for a in args if not a.startswith("--")]
    inp = pos[0] if pos else "shell.glb"
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
    out = opt("--out", "shell.patina.glb")
    dressing = "--dressing" in args
    out_path = Path(out)
    base = str(out_path)[:-4] if str(out_path).endswith(".glb") else str(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"glTF-patina-stub")
    manifest = {"input": inp, "mode": opt("--mode", "vertex-color"),
                "theme": opt("--theme", "default"), "dressing": dressing,
                "collision": "untouched", "warnings": []}
    Path(base + ".json").write_text(json.dumps(manifest, sort_keys=True))
    Path(base + ".gameplay.json").write_text(json.dumps(
        {"collision": "untouched", "anchors": []}, sort_keys=True))
    if dressing and "--anchors" in args:
        Path(base + ".dressing.json").write_text(json.dumps(
            {"schema": "patina-dressing/1", "building_id": Path(inp).stem.split(".")[0],
             "orders": [{"kind": "curb", "count": 4}]}, sort_keys=True))
        Path(base + ".anchors.json").write_text(json.dumps(
            {"schema": "patina-anchors/1", "anchors": []}, sort_keys=True))
        print(f"[patina] dressing -> {base}.dressing.json")
    print(f"[patina] {'dressing' if dressing else 'base'} -> {out_path}")
    print("[patina] visual 2096 tris; collision 12 tris (untouched)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
