"""A pack that is present is not necessarily a pack that is intact.

`PixelcoatAdapter.normalize_validation` has always refused a manifest naming a
map that is not there. Pixelcoat 0.47.0 writes `map_sha256` -- the digest of
each map, read back from disk by the process that wrote it -- so the adapter
can now also say when a map IS there and is not what the pack says it is: a
truncated write, a half-copied stage directory, a file edited in place.

WHY IT ADVISES RATHER THAN BLOCKS. A missing map cannot be drawn; a mismatched
one can, and may be a pack somebody retouched on purpose. The split follows
`advise_configuration`'s rule in `packages/adapters/sdk.py` -- a refusal says
the tool cannot produce information from these inputs, an advisory says it will
run and mark the result down. Nobody has seen this fire on a real run yet, so
it reports before it gates.

Run:  python -m pytest tests/unit/test_pack_intact.py
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.pixelcoat import PixelcoatAdapter  # noqa: E402


def _pack(d: Path, asset="asphalt", albedo=b"\x89PNG-a", rough=b"\x89PNG-r",
          digests=True):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{asset}_albedo.png").write_bytes(albedo)
    (d / f"{asset}_roughness.png").write_bytes(rough)
    man = {
        "schema": "pixelcoat-pack/2",
        "asset_id": asset,
        "maps": {"albedo": f"{asset}_albedo.png",
                 "roughness": f"{asset}_roughness.png"},
    }
    if digests:
        man["map_sha256"] = {
            "albedo": hashlib.sha256(albedo).hexdigest(),
            "roughness": hashlib.sha256(rough).hexdigest(),
        }
    p = d / f"{asset}.pack.json"
    p.write_text(json.dumps(man, indent=2, sort_keys=True), encoding="utf-8")
    return p


def _findings(*paths):
    return list(PixelcoatAdapter().normalize_validation(list(paths)))


def _codes(findings):
    return sorted(f["code"] for f in findings)


def test_an_intact_pack_reports_nothing(tmp_path):
    assert _findings(_pack(tmp_path / "px")) == []


def test_a_map_that_stopped_matching_its_digest_is_reported(tmp_path):
    p = _pack(tmp_path / "px")
    (tmp_path / "px" / "asphalt_albedo.png").write_bytes(b"truncated")
    found = _findings(p)
    assert _codes(found) == ["PIXELCOAT_PACK_MAP_MODIFIED"]
    assert "albedo" in found[0]["message"]


def test_that_finding_advises_rather_than_blocks(tmp_path):
    """A mismatched map can still be drawn. The missing-map check beside it
    blocks; this one does not, on purpose."""
    p = _pack(tmp_path / "px")
    (tmp_path / "px" / "asphalt_albedo.png").write_bytes(b"different")
    found = _findings(p)
    assert found[0]["blocking"] is False
    assert found[0]["severity"] == "major"


def test_a_missing_map_still_blocks_and_is_not_double_reported(tmp_path):
    """The two checks must not both claim the same file: a map that is gone is
    the older check's, and a digest finding on top would make one defect read
    as two."""
    p = _pack(tmp_path / "px")
    (tmp_path / "px" / "asphalt_roughness.png").unlink()
    found = _findings(p)
    assert _codes(found) == ["PIXELCOAT_PACK_UNRESOLVED"]
    assert found[0]["blocking"] is True


def test_a_pack_written_before_0_47_0_is_silent(tmp_path):
    """No `map_sha256` means nothing to disagree with. Findings about files
    that are fine are how a checker teaches people to ignore it."""
    assert _findings(_pack(tmp_path / "px", digests=False)) == []


def test_a_digest_block_that_is_not_a_dict_is_ignored(tmp_path):
    """An unrecognised shape must not be read as an empty problem list by
    accident -- but nor should a malformed third-party pack crash the
    adapter. It is skipped, and the missing-map check still runs."""
    p = _pack(tmp_path / "px")
    man = json.loads(p.read_text(encoding="utf-8"))
    man["map_sha256"] = "not-a-dict"
    p.write_text(json.dumps(man), encoding="utf-8")
    assert _findings(p) == []


def test_every_mismatched_map_gets_its_own_finding(tmp_path):
    """Two corrupted maps are two statements, not one. The repo has paid for
    the opposite before: a gate reporting one number for three defects."""
    p = _pack(tmp_path / "px")
    (tmp_path / "px" / "asphalt_albedo.png").write_bytes(b"x")
    (tmp_path / "px" / "asphalt_roughness.png").write_bytes(b"y")
    found = _findings(p)
    assert len(found) == 2
    assert {"albedo", "roughness"} == {
        k for k in ("albedo", "roughness")
        if any(k in f["message"] for f in found)}


def test_several_packs_are_each_checked(tmp_path):
    a = _pack(tmp_path / "a", asset="asphalt")
    b = _pack(tmp_path / "b", asset="sidewalk")
    (tmp_path / "b" / "sidewalk_albedo.png").write_bytes(b"z")
    found = _findings(a, b)
    assert len(found) == 1
    assert "sidewalk" in found[0]["message"]


def test_a_non_pack_file_is_left_alone(tmp_path):
    d = tmp_path / "px"
    d.mkdir()
    other = d / "build_report.json"
    other.write_text('{"tool_version": "0.47.0"}', encoding="utf-8")
    assert _findings(other) == []
