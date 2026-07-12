"""Stub Patina (v0.18.0): base cohesion or dressing manifest."""
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command")  # apply | dress
    p.add_argument("--theme", default="")
    p.add_argument("--slots", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--dressing", action="store_true")
    p.add_argument("--panel-fields", action="store_true")
    p.add_argument("--frames", action="store_true")
    p.add_argument("--gutters", action="store_true")
    p.add_argument("--pilasters", action="store_true")
    p.add_argument("--panel-size", default="")
    p.add_argument("--panel-gap", default="")
    p.add_argument("--templates", action="store_true")
    p.add_argument("--overrides", default="")
    p.add_argument("--family", default="")
    a, _ = p.parse_known_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.command == "dress":
        (out / "dressing_manifest.json").write_text(json.dumps({
            "schema": "patina.dressing/1", "space": "spec",
            "orders": [{"kind": "panel_field", "size2": [1.2, 1.2]}]}, sort_keys=True))
        (out / "trim.atlas.png").write_bytes(b"PNG-atlas")
        (out / "trim.atlas.json").write_text(json.dumps({"pieces": ["frame"]}, sort_keys=True))
    else:
        (out / "patina.atlas.png").write_bytes(b"PNG-base")
        (out / "patina.atlas.json").write_text(json.dumps(
            {"theme": a.theme, "palette": "65_20_10_5"}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
