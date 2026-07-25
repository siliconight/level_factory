"""Stub Lot (0.18.0 CLI shape): python lot.py <site_spec.json> <out> [--walkable] [--navqa]."""
import json, sys
from pathlib import Path

def main():
    args = [a for a in sys.argv[1:]]
    pos = [a for a in args if not a.startswith("--")]
    spec_path = pos[0]
    out = Path(pos[1]) if len(pos) > 1 else Path(".")
    walkable = "--walkable" in args
    navqa = "--navqa" in args
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(spec_path).stem
    try:
        spec = json.loads(Path(spec_path).read_text())
    except Exception:
        spec = {}
    gameplay = {
        "site": {"stem": stem}, "buildings": spec.get("buildings", []),
        "rooms": [], "markers": [], "objectives": [], "encounters": [],
        "tactical": {"findings": []},
        "pacing": {"mode": "heist", "estimate_expected_min": 6.4,
                   "range_min": "4.1-8.6 min", "target_min": "7-12 min",
                   "status": "partly outside target (range straddles the window)"},
    }
    (out / f"{stem}.site.gameplay.json").write_text(json.dumps(gameplay, sort_keys=True))
    # Real Lot bakes each building's `at`/`rot` into the scene transform, so a
    # stub that ignores placement would emit the same scene for every candidate
    # and quietly hide exactly the bug the diversity gate exists to catch.
    rows = ['[gd_scene format=3]', '[node name="Site" type="Node3D"]']
    for i, b in enumerate(spec.get("buildings", [])):
        at = list(b.get("at", [0, 0])) + [0, 0]
        rows.append(f'\n[node name="{b.get("id", f"b{i}")}" parent="." type="Node3D"]')
        rows.append(f'transform = Transform3D({b.get("rot", 0)}, {at[0]}, {at[1]})')
    for role in ("spawn", "objective", "extraction"):
        if spec.get(role):
            rows.append(f'\n[node name="{role}_{spec[role]}" parent="." type="Marker3D"]')
    (out / f"{stem}.tscn").write_text("\n".join(rows) + "\n")
    (out / f"{stem}.site.lights.json").write_text(json.dumps({"lights": []}, sort_keys=True))
    if walkable:
        # Real Lot's walk scene carries the mission's three positions as root
        # properties. Laser Tag reads NODES, not properties, so a stub that
        # emitted a bare root would let the end-to-end test pass while the
        # pipeline shipped maps the evaluator refuses to play -- which is
        # exactly what shipped. Derive them from the site so the staged scene
        # has something real to build the LT_* hooks from.
        bl = spec.get("buildings", [])
        def _at(i, dx, dy):
            at = list(bl[i % len(bl)].get("at", [0, 0])) + [0, 0] if bl else [0, 0, 0, 0]
            return f"Vector3({float(at[0]) + dx:g}, 1, {-(float(at[1]) + dy):g})"
        # A name Godot cannot keep: `/` is rewritten to `_` at load, so the
        # child below is dropped unless staging sanitizes both sides. The stub
        # reproduces Lot's old defect on purpose -- the staging net is only
        # proven by a scene that actually needs it.
        (out / f"{stem}_walk.tscn").write_text(
            '[gd_scene format=3]\n\n'
            '[node name="SiteWalk" type="Node3D"]\n'
            f'spawn_pos = {_at(0, 0, 0)}\n'
            f'objective_pos = {_at(1, 12, 8)}\n'
            f'extraction_pos = {_at(2, -10, 20)}\n\n'
            '[node name="b0/LADDER_0_climb" type="Area3D" parent="." groups=["ladder"]]\n\n'
            '[node name="shape" type="CollisionShape3D" parent="b0/LADDER_0_climb"]\n')
    if navqa:
        (out / f"{stem}_navqa.tscn").write_text('[gd_scene format=3]\n[node name="SiteNavQA" type="Node3D"]\n')
    print(f"[lot] assembled '{Path(spec_path).name}' -> {stem}.site.gameplay.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
