"""Editing the staged Godot driver must change the Lux stage's fingerprint.

It did not. `probe` reports LUX's repository commit -- that is the repository
this adapter is configured with -- while both drivers live in
`level_factory/assets/godot/`, so an edit to either moved no component of the
cache key and the stage cache-hit the artifact the OLD driver produced. 0.41.0
rewrote `run_lux_apply.gd`; without this, its evidence run would have measured
0.40.0's output and called it a pass.

Unlike `test_lux_preset_readback.py` next door, this is BEHAVIOURAL: it calls
`fingerprint_inputs`, mutates the file, and compares. No Godot required,
because the fingerprint is computed before anything is executed -- which is
the whole reason the defect was invisible.

Run:  python -m pytest tests/unit/test_lux_driver_in_fingerprint.py
"""
import pytest

from adapters.lux import LuxAdapter


@pytest.fixture()
def driver(tmp_path):
    p = tmp_path / "run_lux_apply.gd"
    p.write_text("extends SceneTree\n# version one\n", encoding="utf-8")
    return p


@pytest.fixture()
def apply_spec(tmp_path, driver):
    scene = tmp_path / "site.tscn"
    scene.write_text("[gd_scene load_steps=1 format=3]\n", encoding="utf-8")
    return {"preset": "Blue Hour", "composed_scene": str(scene),
            "driver_src": str(driver)}


@pytest.fixture()
def gate_spec(tmp_path, driver):
    fdir = tmp_path / "fixtures"
    fdir.mkdir()
    (fdir / "a_fixtures.glb").write_bytes(b"glTF")
    return {"mode": "fixture_gate", "fixtures_dir": str(fdir),
            "driver_src": str(driver)}


def _fp(spec):
    return LuxAdapter().fingerprint_inputs(spec, {})


def test_the_apply_driver_is_in_the_fingerprint(apply_spec):
    assert "driver_src_hash" in _fp(apply_spec)


def test_the_fixture_gate_driver_is_in_the_fingerprint(gate_spec):
    """The gate branch returns EARLY, so a driver hash added after the branch
    would cover apply and silently miss the gate."""
    assert "driver_src_hash" in _fp(gate_spec)


@pytest.mark.parametrize("which", ["apply", "gate"])
def test_editing_the_driver_moves_the_fingerprint(which, apply_spec, gate_spec,
                                                  driver):
    spec = apply_spec if which == "apply" else gate_spec
    before = _fp(spec)
    driver.write_text("extends SceneTree\n# version TWO\n", encoding="utf-8")
    after = _fp(spec)
    assert before != after
    assert before["driver_src_hash"] != after["driver_src_hash"]


@pytest.mark.parametrize("which", ["apply", "gate"])
def test_editing_the_driver_moves_NOTHING_ELSE(which, apply_spec, gate_spec,
                                               driver):
    """A fingerprint that changes wholesale on a driver edit would invalidate
    correctly and tell you nothing about why."""
    spec = apply_spec if which == "apply" else gate_spec
    before = _fp(spec)
    driver.write_text("extends SceneTree\n# version TWO\n", encoding="utf-8")
    after = _fp(spec)
    moved = [k for k in set(before) | set(after)
             if before.get(k) != after.get(k)]
    assert moved == ["driver_src_hash"], moved


def test_a_missing_driver_is_not_an_exception(apply_spec, driver):
    """`plan_commands` raises FileNotFoundError for a missing driver, and that
    is the right place for it. The fingerprint runs FIRST and must not turn a
    missing file into a crash before the message that explains it."""
    driver.unlink()
    fp = _fp(apply_spec)
    assert "driver_src_hash" not in fp


def test_the_adapter_version_moved_so_existing_entries_invalidate():
    """Hashing a new input does not invalidate anything on its own: an entry
    written before the key existed still matches on every key it DID record.
    The version bump is what forces the one re-run."""
    assert LuxAdapter.adapter_version != "0.4.0"
