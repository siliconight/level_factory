"""A test finds a sibling repo by looking for it, not by counting parents.

0.91.0 fixed one of these and named the shape: `parents[3] / "deli_counter"`
is correct from a checkout sitting beside its siblings and wrong from a git
WORKTREE, which is where the work happens. Three more were carrying it on
2026-09-16, found by running the suite from
`gabagool_factory/scratchpad/lf_stairs`, and two of them FAILED rather than
skipped -- `KeyError: 'signs'` and a `FileNotFoundError` naming
`scratchpad\\patina\\`.

THE FIRST TWO CLASSES HERE TEST `tests/siblings.py`. The last is the one that
generalises, and it is a source guard rather than a behaviour test: the defect
is not that any one locator is wrong, it is that the arithmetic keeps getting
written. A `parents[N]` that lands above this repo is that arithmetic, and it
can be recognised without running anything.

WHAT THE GUARD DOES NOT CATCH, said out loud because a checker whose reach is
unstated gets believed further than it should: it reads this repo's own
`tests/`, by `ast` so that prose about `parents[3]` in a docstring is not a
finding, and it knows nothing about paths built one function call away. It is
a floor, not a proof.

Run:  python -m pytest tests/unit/test_sibling_locator.py
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from tests.siblings import env_var, factory_root, not_found, sibling_repo

_REPO = Path(__file__).resolve().parents[2]

#: The repos this factory routes work to (`USING_THE_FACTORY.md`). Used only
#: by the second half of the guard, which looks for one of these names joined
#: onto an expression ending in `.parent`.
_SIBLINGS = ("deli_counter", "dispatch", "lasertag", "lot", "lux", "patina",
             "pixelcoat", "zoo")


# ------------------------------------------------------------- the search

def test_it_finds_a_repo_above_the_caller(tmp_path, monkeypatch):
    """The whole point: an ancestor, at any distance, not a fixed one."""
    monkeypatch.delenv(env_var("patina"), raising=False)
    assert sibling_repo("patina",
                        marker="patina/asset_sets/ground_clutter.json")


def test_a_directory_with_the_right_name_is_not_the_repo(tmp_path, monkeypatch):
    """The marker is the argument that makes this a search for a REPO. Without
    it the walk answers with the first directory wearing the name, which under
    `tests/fixtures/repos/` is a stub written to be incomplete."""
    monkeypatch.setenv(env_var("patina"), str(tmp_path))
    (tmp_path / "patina").mkdir()
    assert sibling_repo("patina", marker="patina/asset_sets/x.json") is None
    # ...and without one it answers with the first directory that fits the
    # name, which is why every caller in this repo passes a marker.
    assert sibling_repo("patina") == tmp_path


def test_the_override_takes_either_spelling(tmp_path, monkeypatch):
    repo = tmp_path / "patina"
    (repo / "patina" / "asset_sets").mkdir(parents=True)
    (repo / "patina" / "asset_sets" / "x.json").write_text("{}")
    rel = "patina/asset_sets/x.json"
    for value in (repo, tmp_path):
        monkeypatch.setenv(env_var("patina"), str(value))
        assert sibling_repo("patina", marker=rel) == repo


def test_a_wrong_override_is_reported_not_papered_over(tmp_path, monkeypatch):
    """It does NOT fall back to the walk. An override naming the wrong place
    is a mistake to say out loud -- silently reading a different checkout than
    the one asked for is the defect this module is about, one level up."""
    monkeypatch.setenv(env_var("patina"), str(tmp_path / "nowhere"))
    assert sibling_repo("patina",
                        marker="patina/asset_sets/ground_clutter.json") is None


def test_the_env_name_is_derived_and_dc_keeps_the_one_it_shipped():
    assert env_var("deli_counter") == "LF_DC_ROOT"      # 0.91.0, in use
    assert env_var("pixelcoat") == "LF_PIXELCOAT_ROOT"
    assert env_var("patina") == "LF_PATINA_ROOT"


def test_the_message_names_the_file_and_the_override():
    msg = not_found("patina", marker="patina/asset_sets/x.json")
    assert "patina/patina/asset_sets/x.json" in msg
    assert "LF_PATINA_ROOT" in msg


def test_the_factory_root_holds_this_repo(monkeypatch):
    monkeypatch.delenv("LF_DC_ROOT", raising=False)
    root = factory_root()
    assert root is not None, "no deli_counter above %s" % _REPO
    assert (root / "deli_counter" / "agent_contract.json").is_file()
    # This repo is in it, however the suite was started -- which is the claim
    # `parents[2]` was making and could not keep from a worktree.
    assert (root / "workspaces").is_dir()


# --------------------------------------------------------- the source guard

#: Not swept: the fixture repos under `tests/fixtures/`, which are stubs
#: standing in for other projects and are not this repo's code, and the build
#: leftovers that are not source at all.
_NOT_SOURCE = {"fixtures", "__pycache__", ".git", "build", "dist",
               "level_factory.egg-info", ".pytest_cache"}


def _sources():
    """Every `.py` in this repo, NOT only the suite.

    It started at `tests/` because that is where the six were. Widening it
    cost one line and found a seventh, in production: `adapters/zoo`'s
    `_FACTORY_ROOT = parents[3]`, which reaches `tools/shape_metrics.py` at
    the factory root and reached `scratchpad/tools/` from a worktree, so
    `measure_shapes` refused and three tests in `test_dressing_jobs.py` went
    red. The depth rule is what makes the widening free: `parents[N]` is
    compared against each file's OWN distance to the repo root, so a
    `parents[3]` that is correct in `apps/cli/commands/` is not a finding
    while the same spelling two directories up is.
    """
    return sorted(p for p in _REPO.rglob("*.py")
                  if not _NOT_SOURCE & set(p.parts))


def _depth_to_repo(path: Path) -> int:
    """`parents[N]` at this N is the repo root, for a file at `path`.

    One per directory between the file and the root, which is exactly what
    `len(relative.parts) - 1` counts. Anything larger has left the repo.
    """
    return len(path.relative_to(_REPO).parts) - 1


def _parents_above_repo(path: Path):
    """`(lineno, N)` for every `....parents[N]` that lands above the repo."""
    out = []
    root = _depth_to_repo(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if not (isinstance(value, ast.Attribute) and value.attr == "parents"):
            continue
        index = node.slice
        if isinstance(index, ast.Constant) and isinstance(index.value, int):
            if index.value > root:
                out.append((node.lineno, index.value))
    return out


def _sibling_off_a_parent(path: Path):
    """`(lineno, name)` for `<expr>.parent / "<repo>"`, and `.parents[N]` too.

    `.parent`, WITH THE DOT. The first version asked whether the left-hand
    source contained the word, and flagged `for parent in here.parents: parent
    / "deli_counter"` -- 0.91.0's correct walk, which is the thing this guard
    exists to recommend. A checker that reports the fix as the defect is worse
    than no checker.
    """
    out = []
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Div)
                and isinstance(node.right, ast.Constant)
                and node.right.value in _SIBLINGS):
            continue
        left = ast.get_source_segment(src, node.left) or ""
        if ".parent" in left:
            out.append((node.lineno, node.right.value))
    return out


#: The id is the path, not the basename: this repo has eleven `__init__.py`
#: and a failure reading `__init__.py10` names none of them.
@pytest.mark.parametrize("path", _sources(),
                         ids=lambda p: p.relative_to(_REPO).as_posix())
def test_nothing_reaches_above_this_repo_by_counting_parents(path):
    """THE GUARD. On 0.93.0 it fails on seven files, which is the sweep that
    found them: `test_signs_in_site_spec` and `test_layer3_wiring` (the two
    that FAILED from a worktree, the second through `ROOT.parent`),
    `test_agent_contract_seam`, `test_theme_zoo_resolution` and
    `test_lasertag_contract` (the three that SKIPPED there, which is 0.91.0's
    failure again), `test_archetype_resolution`, whose brief sweep read the
    other worktrees instead of the factory and PASSED on them, and
    `adapters/zoo/__init__.py`, which is not a test at all.

    NOT `test_dc_preset_registry`, which 0.91.0 had already fixed: its walk is
    the shape this recommends, and its docstring quotes the old spelling as
    history."""
    hits = ["line %d: parents[%d]" % h for h in _parents_above_repo(path)]
    hits += ["line %d: parent / %r" % h for h in _sibling_off_a_parent(path)]
    assert hits == [], (
        "%s locates something outside the repo by counting parents; use "
        "tests.siblings.sibling_repo, which searches for it -- %s"
        % (path.relative_to(_REPO).as_posix(), "; ".join(hits)))


def test_the_guard_can_fail(tmp_path):
    """A checker nobody has seen fail is indistinguishable from one that
    passes (CLAUDE.md). Both halves, against source written to trip them."""
    bad = _REPO / "tests" / "unit" / "_not_a_real_file.py"
    src = ('from pathlib import Path\n'
           'A = Path(__file__).resolve().parents[3] / "pixelcoat"\n'
           'ROOT = Path(__file__).resolve().parents[2]\n'
           'B = ROOT.parent / "patina"\n')
    written = tmp_path / "probe.py"
    written.write_text(src, encoding="utf-8")
    # `_depth_to_repo` reads the PATH, so the probe is measured as if it sat
    # where a unit test sits; the bytes are the tmp_path file's.
    original = Path.read_text
    try:
        Path.read_text = lambda self, **kw: (
            src if self == bad else original(self, **kw))
        assert _parents_above_repo(bad) == [(2, 3)]
        assert _sibling_off_a_parent(bad) == [(2, "pixelcoat"), (4, "patina")]
    finally:
        Path.read_text = original


def test_the_guard_reads_code_and_not_prose():
    """`test_dc_preset_registry.py` explains `parents[3] / "deli_counter"` in
    its own docstring, which is history rather than a locator. `ast` is what
    makes the difference, and this is the case that proves it is being used."""
    path = _REPO / "tests" / "unit" / "test_dc_preset_registry.py"
    assert 'parents[3] / "deli_counter"' in path.read_text(encoding="utf-8")
    assert _parents_above_repo(path) == []
    assert _sibling_off_a_parent(path) == []


def test_the_suite_can_be_run_from_anywhere():
    """What all of it is for: the locator answers the same from a checkout and
    from a worktree, so nothing here depends on which one was used."""
    assert os.path.isdir(_REPO)
    assert sibling_repo("pixelcoat",
                        marker="profiles/signs/delco_1997.json") is not None
