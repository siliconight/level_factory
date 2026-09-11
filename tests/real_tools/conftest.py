"""Real-tool smoke fixtures (TDD 37.5).

Gated on the LF_TOOLS_DIR environment variable pointing at a directory that
contains the real Siliconight tool repos. When it's absent (normal CI / the
stub-only suite), every test here is skipped — the fast suite never depends on
Blender, Godot, or the private repos being present.

LF_TOOLS_DIR may point either at a dir of repos or their parent; each tool's
real root is resolved by locating its package/entry inside.
"""
import os
from pathlib import Path

import pytest

TOOLS_DIR = os.environ.get("LF_TOOLS_DIR")


def _find_root(base: Path, marker_rel: str) -> Path | None:
    """Find the deepest dir under base that contains marker_rel."""
    if (base / marker_rel).exists():
        return base
    for cand in base.rglob(marker_rel):
        # marker_rel may be nested; return its containing repo root.
        root = cand
        for _ in range(marker_rel.count("/") + 1):
            root = root.parent
        if (root / marker_rel).exists():
            return root
    return None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Say what the smoke ran and what it did not, by name.

    Six of these tests skip themselves on a missing fixture, and a suite where
    six tests can go quiet without the total changing is one where a real
    absence reads the same as a benign one (roadmap 66). "Green" has to carry
    its own coverage: every real-tool test is listed here as ran or skipped,
    with the skip's reason, so the person stamping a certification can see
    which tools the run actually touched.
    """
    stats = terminalreporter.stats
    mine = {}
    for outcome in ("passed", "failed", "skipped", "error"):
        for rep in stats.get(outcome, []):
            nodeid = getattr(rep, "nodeid", "")
            if "real_tools" not in nodeid.replace("\\", "/"):
                continue
            # setup-phase skips (the session fixtures) and call-phase results
            # both land here; the worst outcome per test wins.
            name = nodeid.split("::")[-1]
            reason = ""
            if outcome == "skipped" and isinstance(rep.longrepr, tuple):
                reason = str(rep.longrepr[-1])
                if reason.startswith("Skipped: "):
                    reason = reason[len("Skipped: "):]
            prev = mine.get(name)
            if prev is None or outcome in ("failed", "error"):
                mine[name] = (outcome, reason)
    if not mine:
        return
    ran = sorted(n for n, (o, _r) in mine.items() if o == "passed")
    skipped = sorted((n, r) for n, (o, r) in mine.items() if o == "skipped")
    bad = sorted(n for n, (o, _r) in mine.items() if o in ("failed", "error"))
    tr = terminalreporter
    tr.write_sep("-", "real-tool smoke coverage")
    tr.write_line(f"ran {len(ran)} of {len(mine)} real-tool tests"
                  + (f", {len(skipped)} skipped" if skipped else "")
                  + (f", {len(bad)} FAILED" if bad else ""))
    for n in ran:
        tr.write_line(f"  ran      {n}")
    for n, r in skipped:
        tr.write_line(f"  skipped  {n} -- {r}")
    for n in bad:
        tr.write_line(f"  FAILED   {n}")
    tr.write_line("this suite is adapter-and-contract depth in seconds; it "
                  "builds no geometry. Re-certification is docs/CERTIFY.md, "
                  "all legs.")


@pytest.fixture(scope="session")
def tools_base():
    if not TOOLS_DIR:
        pytest.skip("LF_TOOLS_DIR not set; real-tool smoke skipped")
    base = Path(TOOLS_DIR)
    if not base.exists():
        pytest.skip(f"LF_TOOLS_DIR does not exist: {base}")
    return base


@pytest.fixture(scope="session")
def tool_root(tools_base):
    def resolve(marker: str) -> Path:
        root = _find_root(tools_base, marker)
        if root is None:
            pytest.skip(f"tool with marker '{marker}' not found under {tools_base}")
        return root
    return resolve
