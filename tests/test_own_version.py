"""level_factory has to agree with itself about what version it is.

`verify-manifest` already answers this and answers it well -- it is what
caught the mistake this file was first written about. The gap it leaves is
that it only runs when a person types it. These tests ask the same question
from `pytest`, using the factory's own instrument rather than a second opinion
about semver.

WHAT THIS FILE IS NOT. Its first draft was built around a version regression
that did not exist: VERSION and pyproject.toml were read from stale copies
served by the file bridge, showing 0.22.0 against a CHANGELOG at 0.43.3.
`verify-manifest`, run against the real tree, reported VERSION 0.43.3 and an
ordinary UNRELEASED. The tests below are the ones that survive knowing that --
each pins something true about how this repo already works, so the value is in
keeping it working rather than in a defect it once described.
"""
from __future__ import annotations

import re
from pathlib import Path

from packages.tools import contracts

_LF = Path(__file__).resolve().parents[1]


def _version_file() -> str:
    return contracts.strip_version_prefix(
        (_LF / "VERSION").read_text(encoding="utf-8"))


def test_version_file_is_a_semver():
    assert contracts.parse_semver(_version_file()), _version_file()


def test_pyproject_derives_its_version_from_the_version_file():
    """pyproject declares `dynamic = ["version"]` and reads the VERSION file,
    so the two CANNOT disagree. That is the right design and it is already in
    place; this test exists so nobody replaces it with a literal.

    A hard-coded version in pyproject would be a second place to remember,
    and a second place to remember is a place to forget.
    """
    text = (_LF / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'dynamic\s*=\s*\[\s*"version"\s*\]', text), \
        "pyproject no longer declares a dynamic version"
    assert re.search(r'version\s*=\s*\{\s*file\s*=\s*"VERSION"\s*\}', text), \
        "pyproject no longer reads its version from the VERSION file"
    assert not re.search(r'^\s*version\s*=\s*"\d+\.\d+\.\d+"', text, re.M), \
        "pyproject hard-codes a version; it should derive it from VERSION"


def test_level_factory_agrees_with_its_own_changelog():
    """`self_disagreement` is None when VERSION and the newest CHANGELOG
    heading match, UNRELEASED when the record is ahead, UNDOCUMENTED when the
    version is. Anything but None is a finding -- the same one
    `verify-manifest` reports, asked from the suite so it is asked every time.
    """
    installed = _version_file()
    documented = contracts.newest_changelog_entry(_LF)
    assert documented, "level_factory has no CHANGELOG heading to check against"
    verdict = contracts.self_disagreement(installed, documented)
    assert verdict is None, (
        f"level_factory says it is {installed} and its CHANGELOG's newest "
        f"entry is {documented}: {verdict}. "
        + ("The record is right; VERSION should follow it."
           if verdict == contracts.UNRELEASED
           else "The version is right; the record owes an entry."))


def test_version_never_goes_backwards_against_its_own_sidecars():
    """Every `VERSION.pre_*` sidecar is a value VERSION previously held, so
    none may be HIGHER than the current one.

    This passes today and is expected to: the sidecars run 0.23.0 and 0.43.2
    against a VERSION of 0.44.0. It is kept because a backwards reset is
    checkable from the filesystem alone, without knowing why it happened --
    and because Zoo's CHANGELOG records one that really did occur, taking
    VERSION back to 0.31.0 and costing four releases' worth of entries.
    """
    now = contracts.parse_semver(_version_file())
    ahead = []
    for side in sorted(_LF.glob("VERSION.pre_*")):
        was = contracts.parse_semver(
            contracts.strip_version_prefix(
                side.read_text(encoding="utf-8", errors="replace")))
        if was and was > now:
            ahead.append(f"{side.name}={was[0]}.{was[1]}.{was[2]}")
    assert not ahead, (
        f"VERSION is {_version_file()} but these earlier values are higher: "
        + ", ".join(ahead) + ". VERSION has gone backwards.")


def test_the_check_can_actually_fail():
    """Falsification. Every assertion above passes trivially if
    `self_disagreement` returns None for everything, so pin its behaviour on
    inputs whose answer is known by inspection."""
    assert contracts.self_disagreement("0.43.3", "0.44.0") == \
        contracts.UNRELEASED
    assert contracts.self_disagreement("0.44.0", "0.43.3") == \
        contracts.UNDOCUMENTED
    assert contracts.self_disagreement("0.44.0", "0.44.0") is None


def test_the_manifest_pin_is_deliberately_not_checked_here():
    """factory.manifest.json's pin for level_factory is NOT asserted equal to
    VERSION, on purpose.

    The pin means "this combination was verified together" and moves only on
    re-certification, which asserts the real-tool smoke passed. A unit test
    forcing them equal would let a green `pytest` stand in for evidence nobody
    gathered, turning the manifest from a record of verification into a
    restatement of VERSION.
    """
    assert hasattr(contracts, "FACTORY_MANIFEST")
