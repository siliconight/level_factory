"""Editing the compose driver -- or an asset it installs -- must change the
presentation stage's fingerprint.

It did not. `fingerprint_inputs` hashed the slots, the modules, the layers, the
lot and DC's composer revision, which is everything the job CONSUMES, and
nothing about the job's own code. `run_presentation_compose.py` is what turns
DC's output into a shippable package, and rewriting it moved no key.

MEASURED 2026-08-30 (roadmap 93). The driver was changed to install the
worldskin importer default into every composed package. The next full run
reported `bank_block_001.presentation_compose  cache` and shipped the previous
package. Nothing was wrong by any measure the scheduler had -- the inputs were
identical -- and the recovery cost two more runs, because `--force` is a
documented no-op and the working command (`cache forget`) had to be found by
reading the CLI.

The same hole was closed once already ONE LEVEL FURTHER OUT: `fp["composer"]`
exists because a DC composer fix on 2026-08-05 reported `cache` and shipped an
invisible wall. This is that lesson applied to the layer that had it next.

Mirrors `tests/unit/test_lux_driver_in_fingerprint.py`, deliberately: Lux got
this right first, and two adapters solving one problem two ways is how they
drift.

Run:  python -m pytest tests/unit/test_presentation_driver_in_fingerprint.py
"""
import pytest

from adapters.presentation import (PresentationAdapter, _driver_path,
                                   _installed_asset_paths)


@pytest.fixture()
def spec(tmp_path):
    slots = tmp_path / "b.slots.json"
    slots.write_text('{"slots": []}', encoding="utf-8")
    glb = tmp_path / "b.glb"
    glb.write_bytes(b"glTF")
    return {"theme": "delco", "style": 1, "slots_path": str(slots),
            "greybox_glb": str(glb), "modules_dir": str(tmp_path / "kit")}


def _fp(spec):
    return dict(PresentationAdapter().fingerprint_inputs(spec, {}))


def test_the_driver_is_in_the_fingerprint(spec):
    assert "driver_src_hash" in _fp(spec)


def test_every_installed_asset_is_in_the_fingerprint(spec):
    """The driver COPIES these into the package, so they ship. An asset hashed
    nowhere is a change to every building's materials that reports `cache`."""
    fp = _fp(spec)
    for a in _installed_asset_paths():
        assert "installed_asset_hash[%s]" % a.name in fp, a


def test_editing_the_driver_moves_the_fingerprint(spec, tmp_path):
    drv = _driver_path()
    before = _fp(spec)
    original = drv.read_bytes()
    try:
        drv.write_bytes(original + b"\n# touched by a test\n")
        after = _fp(spec)
    finally:
        drv.write_bytes(original)
    assert before != after
    assert before["driver_src_hash"] != after["driver_src_hash"]


def test_editing_the_driver_moves_NOTHING_ELSE(spec):
    """A fingerprint that changes wholesale on a driver edit would invalidate
    correctly and tell you nothing about why."""
    drv = _driver_path()
    before = _fp(spec)
    original = drv.read_bytes()
    try:
        drv.write_bytes(original + b"\n# touched by a test\n")
        after = _fp(spec)
    finally:
        drv.write_bytes(original)
    moved = [k for k in set(before) | set(after)
             if before.get(k) != after.get(k)]
    assert moved == ["driver_src_hash"], moved


def test_editing_an_installed_asset_moves_the_fingerprint(spec):
    asset = _installed_asset_paths()[0]
    key = "installed_asset_hash[%s]" % asset.name
    before = _fp(spec)
    original = asset.read_bytes()
    try:
        asset.write_bytes(original + b"\n# touched by a test\n")
        after = _fp(spec)
    finally:
        asset.write_bytes(original)
    assert before[key] != after[key]


def test_a_missing_driver_is_not_an_exception(spec, monkeypatch):
    """`validate_configuration` already reports a missing driver BY NAME. The
    fingerprint runs first and must not replace that message with a traceback.
    """
    import adapters.presentation as mod
    monkeypatch.setattr(mod, "_driver_path",
                        lambda: mod.Path("no-such-driver.py"))
    fp = _fp(spec)
    assert "driver_src_hash" not in fp


def test_the_adapter_version_moved_so_existing_entries_invalidate():
    """Hashing a new input does not invalidate anything on its own: an entry
    written before the key existed still matches on every key it DID record.
    The version bump is what forces the one re-run."""
    assert PresentationAdapter.adapter_version != "0.3.0"
