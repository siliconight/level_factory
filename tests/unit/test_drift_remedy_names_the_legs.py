"""A DRIFT line sends the reader to the runbook, not to one suite (roadmap 66).

`verify-manifest` used to end every DRIFT line with "re-run the real-tool
smoke and re-certify". That names a suite of ten tests that runs in five
seconds and, by construction, builds no geometry -- so after a deli_counter or
lux bump a green run of it had never touched the walls or the light those
bumps changed, and a set could be stamped on it. The remedy now names the
runbook and its legs; this pins that it keeps doing so and that the smoke is
described for what it is.
"""
from packages.tools import contracts as C


def _drift():
    return C.ContractResult(adapter_id="deli_counter", certified="0.94.0",
                            installed="0.102.0", status=C.DRIFT,
                            source="factory.manifest")


def test_drift_remedy_points_at_the_runbook_and_its_legs():
    msg = _drift().message
    assert "docs/CERTIFY.md" in msg
    for leg in ("real-tool smoke", "walkabout", "engine leg", "lux visual leg"):
        assert leg in msg, leg


def test_drift_remedy_says_the_smoke_builds_no_geometry():
    assert "no geometry" in _drift().message


def test_drift_remedy_does_not_prescribe_the_smoke_alone():
    msg = _drift().message
    assert "re-run the real-tool smoke and re-certify" not in msg
