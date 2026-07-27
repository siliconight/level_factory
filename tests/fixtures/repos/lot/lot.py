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
    bl = spec.get("buildings", [])

    def _mission_xz():
        """The three mission points in Godot XZ, shared by the site's ground
        slab and the walk scene's root properties so they cannot drift apart."""
        def _at(i, dx, dy):
            at = list(bl[i % len(bl)].get("at", [0, 0])) + [0, 0] if bl else [0, 0, 0, 0]
            return (float(at[0]) + dx, -(float(at[1]) + dy))
        return [_at(0, 0, 0), _at(1, 12, 8), _at(2, -10, 20)]

    pts = _mission_xz()
    # Real Lot lays the walkable surface as StaticBody3D + BoxShape3D slabs, and
    # Laser Tag's validate_map() rays straight down from the spawn onto them. A
    # stub that emitted no floor would be refused by the ground-contact
    # pre-flight before any of the pipeline behaviour under test ran; a stub
    # that floors its own mission is the honest stand-in. The unfloored case is
    # covered directly in tests/unit/test_ground_contact.py.
    xs = [p[0] for p in pts] or [0.0]
    zs = [p[1] for p in pts] or [0.0]
    cx, cz = (min(xs) + max(xs)) / 2.0, (min(zs) + max(zs)) / 2.0
    sx, sz = max(xs) - min(xs) + 60.0, max(zs) - min(zs) + 60.0
    rows = ['[gd_scene load_steps=2 format=3]',
            '',
            '[sub_resource type="BoxShape3D" id="BoxShape_Ground"]',
            f'size = Vector3({sx:g}, 0.5, {sz:g})',
            '',
            '[node name="Site" type="Node3D"]',
            '',
            '[node name="Ground" type="StaticBody3D" parent="."]',
            f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {cx:g}, -0.25, {cz:g})',
            '',
            '[node name="col" type="CollisionShape3D" parent="./Ground"]',
            'shape = SubResource("BoxShape_Ground")']
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
        def _v(p):
            return f"Vector3({p[0]:g}, 1, {p[1]:g})"
        # A name Godot cannot keep: `/` is rewritten to `_` at load, so the
        # child below is dropped unless staging sanitizes both sides. The stub
        # reproduces Lot's old defect on purpose -- the staging net is only
        # proven by a scene that actually needs it.
        #
        # The walk scene instances the site rather than restating it, the way
        # real Lot does: the ground the mission stands on lives in the site.
        (out / f"{stem}_walk.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n\n'
            f'[ext_resource type="PackedScene" path="res://{stem}.tscn" id="site"]\n\n'
            '[node name="SiteWalk" type="Node3D"]\n'
            f'spawn_pos = {_v(pts[0])}\n'
            f'objective_pos = {_v(pts[1])}\n'
            f'extraction_pos = {_v(pts[2])}\n\n'
            '[node name="Site" parent="." instance=ExtResource("site")]\n\n'
            '[node name="b0/LADDER_0_climb" type="Area3D" parent="." groups=["ladder"]]\n\n'
            '[node name="shape" type="CollisionShape3D" parent="b0/LADDER_0_climb"]\n')
    if navqa:
        (out / f"{stem}_navqa.tscn").write_text('[gd_scene format=3]\n[node name="SiteNavQA" type="Node3D"]\n')
    print(f"[lot] assembled '{Path(spec_path).name}' -> {stem}.site.gameplay.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
