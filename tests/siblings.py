"""Where a sibling tool repo is, asked from wherever the suite is running.

A check that reads another repo on disk has to find it first, and several of
them located it as `Path(__file__).resolve().parents[N] / "<repo>"`. That
arithmetic is correct for a checkout sitting beside its siblings in
`gabagool_factory` and silently wrong from a git WORKTREE, which is where the
contributing guide says to do the work: from
`gabagool_factory/scratchpad/<branch>/tests/unit/`, `parents[3]` is
`scratchpad`, and there is no tool repo in it.

FOUND TWICE, and the two failures are not equally forgiving:

* 0.91.0, `test_dc_preset_registry.py`: the locator missed and the test
  SKIPPED -- a pass it had not made, standing between this repo and a sixth
  refused cold run.
* 0.94.0, `test_signs_in_site_spec.py` and `test_layer3_wiring.py`: the
  locator missed and the tests FAILED, with `KeyError: 'signs'` and
  `FileNotFoundError: scratchpad\\patina\\patina\\asset_sets\\...`. Louder,
  and therefore the better of the two failures -- an absent repo that reads
  as an empty answer is the shape worth removing, not the noise.

So the arithmetic is replaced by a SEARCH, and the answer is `None` rather
than a guessed path: the caller decides whether absence is a skip or an
assertion, and says where it looked either way.

Run:  python -m pytest tests/unit/test_signs_in_site_spec.py
"""
from __future__ import annotations

import os
from pathlib import Path

#: Overrides that predate the rule and are kept as they are: `LF_DC_ROOT`
#: shipped in 0.91.0 and is in use. Everything else derives its name, so a
#: repo added later needs no entry here.
_ENV_KEY = {"deli_counter": "LF_DC_ROOT"}


def env_var(name: str) -> str:
    """The environment variable that overrides the search for `name`."""
    return _ENV_KEY.get(name, "LF_%s_ROOT" % name.upper())


def _carries(root: Path, marker: str) -> bool:
    return root.is_dir() and (not marker or (root / marker).exists())


def sibling_repo(name: str, *, marker: str = "") -> Path | None:
    """The nearest `<name>/` at or above this file that carries `marker`.

    `marker` is a path RELATIVE TO THE REPO and is the whole point of the
    argument: a directory with the right name is not the repo, and the first
    version of this walk would have answered with one. Pass the file the
    caller is about to read.

    The override accepts either the repo itself or the directory holding it,
    because both spellings have been typed at this variable and neither is
    wrong enough to refuse. It does NOT fall back to the walk: an override
    that names the wrong place is a mistake to report, not to paper over.
    """
    env = os.environ.get(env_var(name))
    if env:
        for root in (Path(env), Path(env) / name):
            if _carries(root, marker):
                return root
        return None
    for parent in Path(__file__).resolve().parents:
        root = parent / name
        if _carries(root, marker):
            return root
    return None


def factory_root(*, anchor: str = "deli_counter",
                 marker: str = "agent_contract.json") -> Path | None:
    """The directory the sibling tool repos sit in, or None.

    DERIVED FROM A SIBLING rather than counted, for the same reason as the
    walk above: `parents[2]` is this directory from a checkout and
    `scratchpad` from a worktree. A corpus sweep anchored on it then read the
    OTHER worktrees instead of the factory -- and passed, because they carry
    copies of this repo's own briefs, so "at least 20 briefs" was satisfied by
    a corpus nobody meant. That is the failure a sweep cannot report on its
    own: it found files, they were the wrong files.

    The anchor is Deli Counter's `agent_contract.json` because CLAUDE.md makes
    it the single source of truth for the factory -- a directory holding it is
    the factory root, and one that does not is a directory with the right
    name.
    """
    repo = sibling_repo(anchor, marker=marker)
    return repo.parent if repo else None


def not_found(name: str, *, marker: str = "") -> str:
    """The sentence a skip or an assertion says when the search came back
    empty. It names the repo, the file that made it recognisable and the
    variable that overrides the search, because "not found" on its own has
    sent somebody looking in the wrong directory before."""
    what = "%s/%s" % (name, marker) if marker else name + "/"
    return ("no %s at or above %s -- set %s"
            % (what, Path(__file__).resolve().parent, env_var(name)))
