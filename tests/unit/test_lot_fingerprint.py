"""The Lot job's fingerprint must watch everything the site spec names.

Guards the defect where Deli Counter's light-anchor fix landed and the site did
not change. DC moved every ceiling fixture from inside a floor slab to below it
(28 of 28 fluorescents, from z 3.90/7.90/-0.10 to 3.60/7.60/-0.40), which
rewrote each building's `<stem>.lights.json` and left every `shell.glb`
byte-identical -- the geometry did not move. The Lot adapter hashed only the
GLBs, so its fingerprint was unchanged, the job reported `cache`, and
`site.site.lights.json` shipped the old heights while DC's own output carried
the new ones.

A stage whose output depends on a file its fingerprint does not watch will serve
a stale answer and call it a hit. That is the same shape as the export built
from week-old jobs in roadmap 33, one layer down.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.lot import LotAdapter  # noqa: E402


def _site(tmp_path: Path, ceiling_z: float) -> tuple[Path, dict]:
    """A one-building site whose geometry never changes."""
    (tmp_path / "shell.glb").write_bytes(b"GEOMETRY-BYTE-IDENTICAL")
    (tmp_path / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    (tmp_path / "shell.lights.json").write_text(
        json.dumps({"anchors": [{"id": "r_ceiling", "type": "fluorescent",
                                 "pos": [0.0, 0.0, ceiling_z]}]}),
        encoding="utf-8")
    spec = tmp_path / "site.json"
    spec.write_text(json.dumps({
        "name": "site",
        "buildings": [{"id": "b0",
                       "glb": str(tmp_path / "shell.glb"),
                       "gameplay": str(tmp_path / "shell.gameplay.json"),
                       "at": [0, 0], "rot": 0}],
    }), encoding="utf-8")
    job = {"site_spec_path": str(spec), "walkable": True, "navqa": False,
           "building_glbs": [str(tmp_path / "shell.glb")]}
    return spec, job


def test_a_changed_light_manifest_moves_the_fingerprint(tmp_path):
    """The regression. Only the lights change; the job must re-run."""
    _spec, job = _site(tmp_path, 3.90)
    before = LotAdapter().fingerprint_inputs(job, {})

    # Exactly what DC's fix did: rewrite the light manifest, touch nothing else.
    (tmp_path / "shell.lights.json").write_text(
        json.dumps({"anchors": [{"id": "r_ceiling", "type": "fluorescent",
                                 "pos": [0.0, 0.0, 3.60]}]}),
        encoding="utf-8")
    after = LotAdapter().fingerprint_inputs(job, {})

    assert (before["building_hashes"]["shell.glb"]
            == after["building_hashes"]["shell.glb"]), "geometry must not move"
    assert before["site_spec_hash"] == after["site_spec_hash"], "spec must not move"
    assert before != after, (
        "the fingerprint ignored a file Lot merges into its output")


def test_the_fingerprint_watches_the_manifests_the_spec_names(tmp_path):
    """Named, not incidental -- so a reader can see what is covered."""
    _spec, job = _site(tmp_path, 3.90)
    fp = LotAdapter().fingerprint_inputs(job, {})
    watched = set(fp["building_hashes"])
    assert {"shell.glb", "shell.gameplay.json", "shell.lights.json"} <= watched, watched


def test_a_building_added_only_to_the_spec_is_still_covered(tmp_path):
    """The spec is the source of truth, not the caller's parallel list.

    `building_glbs` is passed separately by the CLI, so a building added to the
    spec and not to that list would be invisible to a fingerprint that trusted
    the list. Reading the spec is what makes that impossible.
    """
    spec, job = _site(tmp_path, 3.90)
    (tmp_path / "second.glb").write_bytes(b"SECOND")
    doc = json.loads(spec.read_text(encoding="utf-8"))
    doc["buildings"].append({"id": "b1", "glb": str(tmp_path / "second.glb"),
                             "at": [10, 0], "rot": 0})
    spec.write_text(json.dumps(doc), encoding="utf-8")
    # deliberately NOT added to job["building_glbs"]
    fp = LotAdapter().fingerprint_inputs(job, {})
    assert "second.glb" in fp["building_hashes"], fp["building_hashes"]


def test_a_missing_manifest_is_not_an_error(tmp_path):
    """A building with no lights sidecar fingerprints fine.

    Not every building carries every manifest, and a fingerprint that raised on
    an absent optional file would fail builds that are correct.
    """
    _spec, job = _site(tmp_path, 3.90)
    (tmp_path / "shell.lights.json").unlink()
    fp = LotAdapter().fingerprint_inputs(job, {})
    assert "shell.lights.json" not in fp["building_hashes"]
    assert "shell.glb" in fp["building_hashes"]
