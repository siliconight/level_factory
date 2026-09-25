"""A retuned texture is a different input, and Zoo's fingerprint says so.

MEASURED BEFORE THIS WAS WRITTEN, with Pixelcoat's own builder. Rebuild
`asphalt_delco` with a different `base_colors` -- a pure appearance retune,
which is what a grammar change usually is:

    asphalt_delco.pack.json       fd4678dbc03ab70f -> fd4678dbc03ab70f  IDENTICAL
    asphalt_delco_albedo.png      68e2fd2cb8509e28 -> 500265cbf2630a20  differs

A pack manifest names FILENAMES and carries no digest of their contents, so
new pixels under the same names leave it byte-identical. `skin_hashes` hashed
only `*.pack.json`, so the kit job's fingerprint did not move, the cache hit,
and -- because Zoo BAKES these maps into the GLB -- what shipped was the
previously baked material rather than a stale reference to a fresh file.

This is the rule `adapters/lot/__init__.py:141-162` already applies to the
ground skins, in its own words: fold the pack manifest and every map it names,
and a pack that is not there yet folds nothing. It is also the narrow form of
the open general defect recorded in `packages/core/hashing.py:77-79` --
`BuildFingerprint.upstream_artifact_hashes` "which nothing populates, so every
DAG edge carries this blindness" (roadmap 39).

Run:  python -m pytest tests/unit/test_skin_map_fingerprint.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402


def _ctx(tmp_path):
    return {"work_dir": str(tmp_path / "work"),
            "repository": str(tmp_path / "repo"),
            "python_executable": "python", "blender_executable": "blender"}


def _pack(root: Path, name: str, albedo: bytes, rough: bytes = b"ROUGH"):
    """A minimal pack in the shape Pixelcoat writes and Zoo resolves."""
    d = root / f"{name}_delco_1997"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.pack.json").write_text(
        '{"schema": "pixelcoat-pack/2", "asset_id": "%s", "maps": '
        '{"albedo": "%s_albedo.png", "roughness": "%s_roughness.png"}}'
        % (name, name, name), encoding="utf-8")
    (d / f"{name}_albedo.png").write_bytes(albedo)
    (d / f"{name}_roughness.png").write_bytes(rough)
    return d


def _fp(tmp_path, skins):
    return ZooAdapter().fingerprint_inputs(
        {"mode": "kit", "theme": "delco_1997", "seed": 7,
         "skins_dir": str(skins)}, _ctx(tmp_path))


def test_a_retuned_texture_moves_the_fingerprint(tmp_path):
    """THE DEFECT, as a failing assertion. Same manifest, different pixels."""
    skins = tmp_path / "px"
    _pack(skins, "asphalt", b"\x89PNG-before")
    before = _fp(tmp_path, skins)

    _pack(skins, "asphalt", b"\x89PNG-AFTER-a-retune")
    after = _fp(tmp_path, skins)

    man = "asphalt.pack.json"
    assert before["skin_hashes"][man] == after["skin_hashes"][man], (
        "this test is only meaningful while the MANIFEST stays identical; if "
        "Pixelcoat started digesting its maps into the manifest, rewrite it")
    assert before != after, (
        "a pack whose albedo changed produced the same fingerprint, so the "
        "kit job would cache-hit and ship the previously baked material")


def test_an_untouched_library_fingerprints_the_same(tmp_path):
    """Content-addressed, so the fix can only make the key more sensitive --
    a rebuild that produces identical bytes stays cached."""
    skins = tmp_path / "px"
    _pack(skins, "asphalt", b"\x89PNG-steady")
    _pack(skins, "sidewalk", b"\x89PNG-steady-2")
    assert _fp(tmp_path, skins) == _fp(tmp_path, skins)


def test_every_map_a_pack_names_is_in_the_key(tmp_path):
    skins = tmp_path / "px"
    _pack(skins, "asphalt", b"A")
    h = _fp(tmp_path, skins)["skin_hashes"]
    assert "asphalt.pack.json" in h
    assert "asphalt.pack.json::albedo" in h
    assert "asphalt.pack.json::roughness" in h


def test_a_changed_roughness_map_also_moves_it(tmp_path):
    """Not just the albedo. A roughness retune is what Pixelcoat 0.41.0 was --
    bare metal that had been mirroring the room in stripes."""
    skins = tmp_path / "px"
    _pack(skins, "metal", b"A", rough=b"R1")
    before = _fp(tmp_path, skins)
    _pack(skins, "metal", b"A", rough=b"R2")
    assert _fp(tmp_path, skins) != before


def test_a_map_that_went_missing_is_not_the_same_as_one_never_named(tmp_path):
    """A pack that lost a file is a different input from a complete one, and a
    fingerprint that could not tell would serve the complete build's output
    for the broken one."""
    skins = tmp_path / "px"
    d = _pack(skins, "asphalt", b"A")
    before = _fp(tmp_path, skins)
    (d / "asphalt_albedo.png").unlink()
    after = _fp(tmp_path, skins)
    assert after["skin_hashes"]["asphalt.pack.json::albedo"] == "<missing>"
    assert before != after


def test_an_unreadable_manifest_still_registers(tmp_path):
    """The manifest is hashed before it is parsed, so corruption moves the
    fingerprint even though there is nothing left to enumerate."""
    skins = tmp_path / "px"
    d = _pack(skins, "asphalt", b"A")
    before = _fp(tmp_path, skins)
    (d / "asphalt.pack.json").write_text("{ not json", encoding="utf-8")
    after = _fp(tmp_path, skins)
    assert before != after
    assert "asphalt.pack.json" in after["skin_hashes"]


def test_no_skins_dir_means_no_skin_hashes(tmp_path):
    """Unchanged behaviour: a job without a skin library carries no such key,
    and does not start hashing anything."""
    fp = ZooAdapter().fingerprint_inputs(
        {"mode": "kit", "theme": "delco_1997", "seed": 7}, _ctx(tmp_path))
    assert "skin_hashes" not in fp
