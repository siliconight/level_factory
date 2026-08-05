"""The compose must invalidate when DC's COMPOSER changes.

This job does not merely read Deli Counter's data, it executes DC's code:
`portable_building.build_package`, through a driver. So its output can change
while every input hash stays identical.

Measured 2026-08-05. `strip_greybox_base` was fixed in DC -- exact slot-id
match, so `VAULT` stopped deleting `VAULTLEDGE_0`'s visual while leaving its
collider, which had put an invisible wall in a walkable room. DC committed,
DC's suite went green, `run --art --force` reported `deli_generate SUCCEEDED`
and `zoo_kit_build SUCCEEDED`, and this job reported `cache`. The composed
`site_base.glb` came back byte-identical and the invisible wall was still
there. The rebuild looked real and was not.

`verify-contracts` catches a sub-tool DRIFTING out from under an adapter.
This is that failure with the opposite sign -- a sub-tool FIX not reaching a
cached job -- and nothing was watching for it.
"""

import pathlib
import shutil
import tempfile

import pytest

from adapters.presentation import (PresentationAdapter,  # noqa: F401
                                   _COMPOSER_SOURCES,
                                   _composer_fingerprint)


@pytest.fixture
def dc_repo():
    root = tempfile.mkdtemp()
    for rel in _COMPOSER_SOURCES:
        pathlib.Path(root, rel).write_text("original\n")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_every_declared_source_is_hashed(dc_repo):
    fp = _composer_fingerprint({"deli_repo": dc_repo}, {})
    assert set(fp) == set(_COMPOSER_SOURCES)


def test_editing_the_composer_moves_the_fingerprint(dc_repo):
    """THE regression. `strip_greybox_base` lives in portable_building.py."""
    before = _composer_fingerprint({"deli_repo": dc_repo}, {})
    pathlib.Path(dc_repo, "portable_building.py").write_text("exact match\n")
    after = _composer_fingerprint({"deli_repo": dc_repo}, {})
    assert before != after
    assert [k for k in before if before[k] != after[k]] == ["portable_building.py"]


@pytest.mark.parametrize("rel", _COMPOSER_SOURCES)
def test_each_source_individually_invalidates(dc_repo, rel):
    before = _composer_fingerprint({"deli_repo": dc_repo}, {})
    pathlib.Path(dc_repo, rel).write_text("changed\n")
    assert _composer_fingerprint({"deli_repo": dc_repo}, {}) != before


def test_unrelated_dc_files_do_not_invalidate(dc_repo):
    """A cache that invalidates on everything is a cache nobody keeps. A test,
    a preset or a status script moving must not rebuild every compose."""
    before = _composer_fingerprint({"deli_repo": dc_repo}, {})
    pathlib.Path(dc_repo, "presets.py").write_text("irrelevant\n")
    pathlib.Path(dc_repo, "test_stair_core.py").write_text("irrelevant\n")
    assert _composer_fingerprint({"deli_repo": dc_repo}, {}) == before


def test_missing_repo_degrades_rather_than_raising():
    """A bad path is `plan_commands`' problem to report. Raising here would
    turn it into a crash at cache-lookup time."""
    assert _composer_fingerprint({}, {}) == {}
    assert _composer_fingerprint({"deli_repo": "/nope/nowhere"}, {}) == {}


def test_missing_source_files_are_skipped_not_faked(dc_repo):
    """A DC version that lacks one of these must fingerprint the rest, not
    substitute a placeholder that collides across versions."""
    pathlib.Path(dc_repo, "circulation.py").unlink()
    fp = _composer_fingerprint({"deli_repo": dc_repo}, {})
    assert "circulation.py" not in fp
    assert len(fp) == len(_COMPOSER_SOURCES) - 1


def test_fingerprint_inputs_carries_the_composer():
    """The whole point: it has to actually reach the job fingerprint."""
    a = PresentationAdapter()
    fp = a.fingerprint_inputs({"theme": "rockay"}, {})
    assert "composer" in fp
