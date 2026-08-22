"""Functional lock + post-art regression (TDD 23.4, 31)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.approvals.lock import compute_lock, verify_no_drift


def _write(p: Path, data: dict) -> Path:
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_unchanged_shell_has_no_drift(tmp_path):
    site = _write(tmp_path / "site.gameplay.json", {"buildings": ["b"], "route": {"a": 1}})
    deli = _write(tmp_path / "shell.gameplay.json", {
        "stair_systems": [{"id": "s1"}], "anchors": [{"id": "vault", "type": "breach"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    result = verify_no_drift(lock, site, deli)
    assert result.passed
    assert result.drift == []


def test_collision_drift_is_detected(tmp_path):
    site = _write(tmp_path / "site.gameplay.json", {"buildings": ["b"]})
    deli = _write(tmp_path / "shell.gameplay.json", {"stair_systems": [{"id": "s1"}],
                                                     "anchors": [{"id": "v"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    # Art pass illegally moved a stair.
    _write(deli, {"stair_systems": [{"id": "s1", "moved": True}], "anchors": [{"id": "v"}]})
    result = verify_no_drift(lock, site, deli)
    assert not result.passed
    assert any("collision" in d for d in result.drift)


def test_anchor_drift_is_detected(tmp_path):
    site = _write(tmp_path / "site.gameplay.json", {})
    deli = _write(tmp_path / "shell.gameplay.json", {"anchors": [{"id": "v", "type": "breach"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    _write(deli, {"anchors": [{"id": "v2", "type": "breach"}]})  # anchor id changed
    result = verify_no_drift(lock, site, deli)
    assert not result.passed
    assert any("anchor" in d for d in result.drift)


_INTER = [{"id": "b:if:11111111", "kind": "window", "slot_ref": "ext_0_S_open1",
           "building": "b", "states": ["intact", "broken"], "default": "intact",
           "transitions": [{"event": "break", "from": "intact", "to": "broken"}],
           "collision_per_state": {"intact": True, "broken": False},
           "transform": {"translation": [3.0, 8.0, 1.1], "rot_y": 0}}]


def test_interactive_semantics_drift_without_geometry(tmp_path):
    """The answer to 'two collision states, one hash': the fingerprint hashes
    the level at rest, and the per-state truth is protected as DATA. Flipping
    a state's collision semantics moves the interactive registry hash without
    moving a single vertex."""
    site = _write(tmp_path / "site.gameplay.json",
                  {"interactives": _INTER, "markers": [{"name": "b/S", "type": "spawn"}]})
    deli = _write(tmp_path / "shell.gameplay.json", {"anchors": [{"id": "v"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    changed = [dict(_INTER[0], collision_per_state={"intact": True, "broken": True})]
    _write(site, {"interactives": changed, "markers": [{"name": "b/S", "type": "spawn"}]})
    result = verify_no_drift(lock, site, deli)
    assert not result.passed
    assert any("interactive" in d for d in result.drift)
    # and NOT reported as collision drift -- geometry did not move
    assert not any("collision" in d for d in result.drift)


def test_dropped_fixture_is_drift(tmp_path):
    site = _write(tmp_path / "site.gameplay.json", {"interactives": _INTER})
    deli = _write(tmp_path / "shell.gameplay.json", {"anchors": [{"id": "v"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    _write(site, {"interactives": []})  # an art pass lost the fixture
    result = verify_no_drift(lock, site, deli)
    assert not result.passed
    assert any("interactive" in d for d in result.drift)


def test_interactives_backfill_from_deli_when_site_omits(tmp_path):
    """A site file written before Lot carried the key: the building's own
    declaration is the truth, same rule as stair_systems."""
    site = _write(tmp_path / "site.gameplay.json", {"markers": []})
    deli = _write(tmp_path / "shell.gameplay.json",
                  {"anchors": [{"id": "v"}], "interactives": _INTER})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    assert verify_no_drift(lock, site, deli).passed
    _write(deli, {"anchors": [{"id": "v"}],
                  "interactives": [dict(_INTER[0], default="broken")]})
    result = verify_no_drift(lock, site, deli)
    assert not result.passed
    assert any("interactive" in d for d in result.drift)


def test_v02_lock_needs_recompute_not_drift(tmp_path):
    """Adding a signature changes the definition set: v0.2 locks are
    incomparable, and incomparable is 'recompute', never 'drift'."""
    from packages.approvals.lock import blocks_export
    site = _write(tmp_path / "site.gameplay.json", {"interactives": _INTER})
    deli = _write(tmp_path / "shell.gameplay.json", {"anchors": [{"id": "v"}]})
    lock = compute_lock(mission_id="m1", candidate_id="c1", seed=1,
                        site_gameplay_path=site, deli_gameplay_path=deli)
    lock.schema = "level_factory.functional_lock.v0.2"
    result = verify_no_drift(lock, site, deli)
    assert result.needs_recompute and result.drift == [] and not result.passed
    assert not blocks_export(result)
