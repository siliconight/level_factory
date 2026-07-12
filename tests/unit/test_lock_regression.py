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
