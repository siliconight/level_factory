"""Zoo partial-build (some modules failed) is a NON-BLOCKING quality finding.

Zoo exits 2 when n_fail > 0 but still writes its index and the modules that did
build; Deli's resolver falls back to base for the rest. Paired with the
scheduler's exit_advisory handling, the kit build completes with a finding
instead of hard-failing the presentation.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402


def _index(tmp_path, **fields) -> Path:
    p = tmp_path / "lf_m1_kit.built.json"
    p.write_text(json.dumps(fields))
    return p


def test_partial_build_is_nonblocking_finding(tmp_path):
    idx = _index(tmp_path, building_id="lf_m1", n_fail=3, modules=[])
    issues = ZooAdapter().normalize_validation([idx])
    codes = {i["code"] for i in issues}
    assert "ZOO_PARTIAL_BUILD" in codes
    pb = next(i for i in issues if i["code"] == "ZOO_PARTIAL_BUILD")
    assert pb["blocking"] is False


def test_clean_build_has_no_partial_finding(tmp_path):
    idx = _index(tmp_path, building_id="lf_m1", n_fail=0, modules=[])
    issues = ZooAdapter().normalize_validation([idx])
    assert all(i["code"] != "ZOO_PARTIAL_BUILD" for i in issues)


def test_dressing_collision_still_blocks(tmp_path):
    # The existing collision guard must remain a hard blocker.
    idx = _index(tmp_path, building_id="lf_m1", n_fail=0,
                 dressing=[{"id": "curb_0", "collision": "mesh"}])
    issues = ZooAdapter().normalize_validation([idx])
    assert any(i["code"] == "ZOO_DRESSING_HAS_COLLISION" and i["blocking"] for i in issues)
