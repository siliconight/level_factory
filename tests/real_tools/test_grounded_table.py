"""The GROUNDED table must name the tools this smoke just ran.

WHY THIS LIVES IN THE SMOKE AND NOWHERE ELSE. `contracts.GROUNDED` is the
version each adapter was certified against, and the procedure that licenses a
certification IS the real-tool smoke -- so the smoke is the only place that
can assert the table without asserting something it has not tested. A unit
test cannot: it has no tools to read. `verify-contracts` cannot: it is the
thing that was being ignored.

AND IT WAS IGNORED FOR A LONG TIME. On 2026-09-21 every row but `dispatch`
was behind, `deli_counter` by 66 minors and `lot` by 56. Nothing forced a
re-grounding, and three layers each muffled the signal: a minor gap reads
DRIFT, `verify-contracts` returns exit-2 findings for DRIFT rather than
failing, and each workspace's tools.lock.json overrides its own row locally,
so a workspace that had certified could not see that the shipped table had
not. It took `zoo` crossing 1.0.0 -- same comparison, INCOMPATIBLE, which
fails `doctor` -- to cost a cold run (9063) and make anyone look.

A SKIP HERE IS NOT A PASS. Everything below is gated on `tools_base`, which
skips when LF_TOOLS_DIR is unset or absent, so the stub-only suite is
untouched and this can never fire against tools that are not there. When the
tools ARE there but a particular one cannot be located or will not report a
version, that row is not compared and is NAMED in the skip reason --
conftest's `pytest_terminal_summary` prints every real-tool skip with its
reason, which is the mechanism that makes a quiet absence visible.
"""
import sys
from pathlib import Path

import pytest

from packages.tools import contracts

from .conftest import _find_root

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: How to locate each tool's repo root under LF_TOOLS_DIR. Every marker here
#: is the one the tool's own smoke test already resolves by, so this map
#: cannot drift into finding a different directory than the test that proved
#: the adapter works against it.
MARKERS = {
    "deli_counter": "new_level.py",
    "dispatch": "dispatch/__main__.py",
    "laser_tag": "addons/laser_tag_tool/runners/run_map_eval.gd",
    "lot": "lot.py",
    "lux": "addons/lux/plugin.cfg",
    "patina": "patina/cli.py",
    "pixelcoat": "pixelcoat/cli/main.py",
    "zoo": "tools/zoo_cli.py",
}


def test_every_grounded_tool_has_a_marker():
    """A tool added to GROUNDED with no marker here would simply stop being
    checked, which is the failure mode this whole file is about. No fixture:
    this one is answerable without any tools present, so it answers always."""
    assert set(MARKERS) == set(contracts.GROUNDED), (
        "MARKERS and contracts.GROUNDED disagree: "
        f"only in GROUNDED {sorted(set(contracts.GROUNDED) - set(MARKERS))}, "
        f"only in MARKERS {sorted(set(MARKERS) - set(contracts.GROUNDED))}")


def test_grounded_matches_the_tools_this_smoke_ran(tools_base):
    """Probe each tool the way `verify-contracts` does and hold GROUNDED to it.

    The probe, not the VERSION file. `_probe_tool_versions` calls
    `adapter.probe(...).tool_version`, and two adapters override it --
    `dispatch` and `deli_counter` prefer their `contract` command's version
    over the file. Reading VERSION here instead would pin `dispatch` to 0.4.2
    and leave `verify-contracts` reading DRIFT against a tool that reports
    0.3.0 and stamps 0.3.0 into everything it writes.

    Comparison is `contracts.compare`, the same function the CLI uses, so
    there is one derivation of what OK means rather than a second one here
    that could disagree with it.
    """
    from packages.adapters.registry import AdapterRegistry

    reg = AdapterRegistry()
    compared: dict[str, str] = {}
    unreadable: dict[str, str] = {}
    bad: list[str] = []

    for adapter_id, marker in sorted(MARKERS.items()):
        grounded = contracts.GROUNDED[adapter_id]["version"]
        repo = _find_root(tools_base, marker)
        if repo is None:
            unreadable[adapter_id] = f"no repo under {tools_base} with {marker}"
            continue
        try:
            probe = reg.get(adapter_id).probe(
                {"repository": str(repo), "python_executable": sys.executable})
            installed = probe.tool_version
        except Exception as exc:  # noqa: BLE001 -- the reason is the finding
            unreadable[adapter_id] = f"probe raised {type(exc).__name__}: {exc}"
            continue
        status = contracts.compare(grounded, installed)
        if status == contracts.UNKNOWN:
            # No comparable version. Degrades to unreadable rather than to a
            # false OK, exactly as `compare` does for the CLI.
            unreadable[adapter_id] = f"probe reported {installed!r}"
            continue
        compared[adapter_id] = str(installed)
        if status != contracts.OK:
            bad.append(f"  {adapter_id:<14} grounded {grounded:<10} "
                       f"installed {installed}   [{status}]")

    assert not bad, (
        "contracts.GROUNDED does not match the tools this smoke just ran:\n"
        + "\n".join(bad)
        + "\n\nThe smoke passing is what licenses a pin, so a pin the smoke "
          "disagrees with is a claim nobody made. Re-ground the row(s) above "
          "in packages/tools/contracts.py -- per docs/CERTIFY.md, the smoke "
          "alone does not re-certify geometry -- or, if the tool really is "
          "not certified at that version, this failure is the finding.")

    # A run that compared nothing proved nothing. Say so as a skip, with the
    # rows named, rather than as a green tick.
    if not compared:
        pytest.skip("no tool reported a comparable version: "
                    + "; ".join(f"{k} ({v})" for k, v in sorted(unreadable.items())))
    if unreadable:
        pytest.skip(f"compared {len(compared)} of {len(MARKERS)} tools "
                    f"({', '.join(sorted(compared))}); not compared: "
                    + "; ".join(f"{k} ({v})" for k, v in sorted(unreadable.items())))
