"""A composed scene's fingerprint has to see the art the scene points at.

The defect this pins shipped twice. A ``.tscn`` names its GLBs and textures by
PATH, so an art pass can rewrite ten megabytes while the scene's own bytes do
not move by one character. An adapter fingerprinting the scene with
``hash_file`` alone matches, serves the previous answer, and calls it a hit --
and the only symptom is that nothing looks different.

  * 2026-08-03: ``themed_site_assemble cache`` and ``lux_apply cache`` behind a
    ``zoo_dressing_build succeeded``.
  * 2026-08-04: six fixes landed, every stage above ``lux_apply`` re-ran, and
    the shipped LIT scene kept the previous day's art for the whole session.

Lot was fixed first and Lux inherited the same blindness, which is why the rule
now lives in ``packages.core.hashing`` with two importers instead of two copies.
"""

from pathlib import Path

from packages.core.hashing import scene_payload_hashes


def _scene(root: Path, payload=b"OLD"):
    (root / "art").mkdir(parents=True, exist_ok=True)
    scene = root / "site.tscn"
    scene.write_text('[gd_scene load_steps=2 format=3]\n'
                     '[ext_resource type="PackedScene" '
                     'path="res://art/dress.glb" id="1"]\n')
    (root / "art" / "dress.glb").write_bytes(payload * 100)
    return scene


def test_rebuilt_art_moves_the_fingerprint_though_the_scene_does_not(tmp_path):
    """THE case. Rewrite the GLB, touch nothing else, and the hash must move."""
    scene = _scene(tmp_path)
    before = scene_payload_hashes(scene)
    scene_bytes = scene.read_bytes()

    (tmp_path / "art" / "dress.glb").write_bytes(b"NEW" * 100)

    assert scene.read_bytes() == scene_bytes      # the scene is untouched
    assert scene_payload_hashes(scene) != before  # and the fingerprint knows


def test_unchanged_art_is_a_genuine_cache_hit(tmp_path):
    """The other half: this must not defeat caching, only make it honest."""
    scene = _scene(tmp_path)
    assert scene_payload_hashes(scene) == scene_payload_hashes(scene)


def test_a_plain_glb_input_does_not_hash_its_whole_job_directory(tmp_path):
    """A greybox ``shell.glb`` is not a composed scene, and walking its job
    directory would hash every candidate's output on every fingerprint."""
    _scene(tmp_path)
    assert scene_payload_hashes(tmp_path / "art" / "dress.glb") == {}
    assert scene_payload_hashes(tmp_path / "does_not_exist.tscn") == {}


def test_keys_are_relative_and_slash_separated(tmp_path):
    """The fingerprint travels between machines; a backslash would make the
    same tree hash differently on Windows and Linux."""
    scene = _scene(tmp_path)
    assert sorted(scene_payload_hashes(scene)) == ["art/dress.glb"]


def test_a_new_art_file_is_noticed_too(tmp_path):
    """Not just a changed payload -- an ADDED one. A dressing pass that emits
    an extra GLB is a different build."""
    scene = _scene(tmp_path)
    before = scene_payload_hashes(scene)
    (tmp_path / "art" / "extra.png").write_bytes(b"\x89PNG")
    after = scene_payload_hashes(scene)
    assert set(after) - set(before) == {"art/extra.png"}


def test_non_payload_files_are_ignored(tmp_path):
    """A log or a provenance sidecar landing beside the art is not the art."""
    scene = _scene(tmp_path)
    before = scene_payload_hashes(scene)
    (tmp_path / "art" / "job.log").write_text("ran for 4.2s")
    (tmp_path / "site.tscn.provenance.json").write_text("{}")
    assert scene_payload_hashes(scene) == before


def test_both_adapters_use_the_one_rule():
    """Two copies of a rule drift, and this toolchain has paid for that more
    than once. Lot had it first; Lux needed it identical a day later."""
    from adapters.lot import LotAdapter
    from adapters.lux import LuxAdapter
    import adapters.lot as lot_mod
    import adapters.lux as lux_mod
    assert lot_mod.scene_payload_hashes is scene_payload_hashes
    assert lux_mod.scene_payload_hashes is scene_payload_hashes
    # and the bump that makes the fix take effect
    assert LuxAdapter.adapter_version == "0.4.0"
    assert LotAdapter.adapter_version == "0.3.0"
