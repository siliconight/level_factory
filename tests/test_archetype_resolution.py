"""The DC adapter must never silently guess an archetype.

`_preset_for` used to end in `return "bank"`. Every mission in the lot demo
carries `archetype: "mixed_block"` -- not a preset, not an alias, no keyword
match -- so all of them silently built BANKS, and nothing said so. It surfaced
only because bank's vault sits at a hardcoded corner offset that collides with
a stairwell, and someone walked into it in the viewport.

A wrong-but-plausible building is this adapter's worst failure mode: the
pipeline succeeds, every gate passes, and the deliverable is the wrong
archetype.
"""

from pathlib import Path

import pytest

from adapters.deli_counter import (UnknownArchetype, _ARCHETYPE_ALIASES,
                                   _VALID_PRESETS, _preset_for)
from tests.siblings import factory_root


@pytest.mark.parametrize("preset", sorted(_VALID_PRESETS))
def test_every_real_preset_resolves_to_itself(preset):
    assert _preset_for(preset) == preset


@pytest.mark.parametrize("alias,preset", sorted(_ARCHETYPE_ALIASES.items()))
def test_every_alias_resolves(alias, preset):
    assert _preset_for(alias) == preset
    assert preset in _VALID_PRESETS, "an alias must point at a real preset"


def test_qualifier_is_stripped():
    assert _preset_for("downtown_office") == "office"
    assert _preset_for("URBAN_BANK") == "bank"


def test_keyword_match_is_allowed():
    """Still a guess, but a justified one -- the archetype literally contains
    a preset's name."""
    assert _preset_for("storefront_bank") == "bank"


@pytest.mark.parametrize("bad", ["mixed_block", "nonsense", "", "   ", None])
def test_unknown_archetype_raises_instead_of_guessing(bad):
    """THE regression. Silence here shipped banks for a whole demo."""
    with pytest.raises(UnknownArchetype):
        _preset_for(bad)


def test_the_error_names_the_way_out():
    """A raise that does not say what to do instead is just a crash."""
    with pytest.raises(UnknownArchetype) as ex:
        _preset_for("mixed_block")
    msg = str(ex.value)
    assert "mixed_block" in msg
    assert "_ARCHETYPE_ALIASES" in msg
    for preset in ("bank", "casino_tower", "office"):
        assert preset in msg


def test_bank_is_no_longer_reachable_by_accident():
    """`bank` must be reached by naming it, aliasing to it, or containing it --
    never by falling off the end of the resolver."""
    assert _preset_for("bank") == "bank"
    with pytest.raises(UnknownArchetype):
        _preset_for("mixed_block")


# ---- fingerprinting must not validate --------------------------------------
#
# The first version of this fix broke `test_fingerprint_is_stable[deli_counter]`:
# the adapter-contract suite fingerprints a MINIMAL spec that carries no
# archetype, and `fingerprint_inputs` resolved a preset to hash it. Hashing is
# not the place to reject a config -- a fingerprint only has to be stable and
# distinguishing. `plan_commands` is where a preset is actually used, so that
# is where an unknown archetype must fail.

from adapters.deli_counter import _preset_or_raw


def test_fingerprint_helper_tolerates_a_missing_archetype():
    assert _preset_or_raw({}) == "<unresolved:>"
    assert _preset_or_raw({"archetype": "mixed_block"}) == "<unresolved:mixed_block>"


def test_fingerprint_helper_still_resolves_a_real_one():
    assert _preset_or_raw({"archetype": "bank"}) == "bank"
    assert _preset_or_raw({"archetype": "urban_bank"}) == "bank"


def test_unresolvable_archetypes_still_hash_DISTINCTLY():
    """Degrading to the raw string must not collapse two different briefs into
    one fingerprint -- that would silently share a cache entry between
    different buildings, which is the same class of bug one layer down."""
    a = _preset_or_raw({"archetype": "mixed_block"})
    b = _preset_or_raw({"archetype": "mixed_tower"})
    assert a != b


# ---------------------------------------------------------------------------
# THE CORPUS. Everything above this line is synthetic, and that is the gap
# roadmap 118 records: `_preset_for` was given ten tests and none of them ever
# asked whether the briefs ON DISK resolve. The brief whose silent-bank
# incident is quoted in this module's own docstring STILL names an archetype
# that refuses -- it stopped building the wrong thing and never started
# building the right one, because nothing looked.
# ---------------------------------------------------------------------------

import functools
import json
import os

#: The tree the corpus lives in: `level_factory/examples`, the recorded cold
#: runs and `workspaces/`. `parents[2]` named it from a checkout and named
#: `scratchpad` from a worktree -- where this sweep read the OTHER worktrees'
#: copies of these same briefs, found more than twenty of them and passed, on
#: a corpus nobody meant. Derived from Deli Counter now (`tests/siblings.py`),
#: so both spellings of "run the suite" read one tree.
_ROOT = factory_root()

#: Briefs known to name an archetype no preset answers to, with the reason.
#: NOT a suppression list: a brief here is a defect somebody has to decide
#: about, and a brief NOT here that refuses fails this suite immediately.
#:
#: `commercial_strip` CAME OUT 2026-09-09, and how it came out is the point.
#: Cold run 9003 built `restaurant_row_001` and the resolver refused, so the
#: run needed an intervention -- and the first one made was an alias,
#: `commercial_strip -> corner_deli`, which THIS TEST caught within the hour.
#: Roadmap 118 had already decided against exactly that: both entries were
#: multi-building briefs using `archetype` to name a BLOCK, and its status
#: settles the question from the corpus rather than by argument -- 17 of the
#: 19 multi-building briefs on disk already name a BUILDING while asking for
#: three to five of them. So the brief was wrong, not the resolver, and the
#: fix was to name its anchor building: the one the objectives hang on, which
#: for `enter_kitchen` / `reach_office` / `crack_safe` is `corner_deli`.
#: The alias was reverted.
#:
#: `mixed_block` STAYS, and not because nobody got to it. Its only carrier is
#: under `workspaces/rockay-ws`, which CLAUDE.md makes read-only evidence --
#: "a level to iterate against: read it, do not edit it". Fixing it means
#: fixing the brief, and that brief is not ours to edit.
_KNOWN_UNRESOLVABLE = {
    "mixed_block": "rockay_lot_demo_001, 5 buildings, HAS lot_library; "
                   "its brief lives under read-only rockay-ws",
    # 0.243.0: the factory's cold run 9394, the first civic brief, refused at the shell leg as it should be --
    # no preset generates a funeral home (the factory's roadmap 309). The brief is that run's record.
    "funeral_home": "funeral_row_001, cold run 9394's record; no preset generates one (roadmap 309)",
}


#: Directories whose briefs are scratch, not corpus: `_runs` is per-invocation
#: smoke output and `build` is generated.
_SKIP_DIRS = {"_runs", "build", "node_modules", ".git"}


def _keep(path):
    """The corpus predicate, asked of a whole path: a brief is `brief.json` or
    any JSON in a `briefs` directory, and nothing under `_SKIP_DIRS` is one."""
    if _SKIP_DIRS & set(path.parts):
        return False
    return path.name == "brief.json" or path.parent.name == "briefs"


def _corpus_walk(root):
    """Every path `root.rglob("*.json")` yields that `_keep` keeps -- found
    without entering a directory in `_SKIP_DIRS`.

    THE SAME LIST, BY CONSTRUCTION. A path below a skipped directory carries
    that directory's name in its parts, so `_keep` refuses it whether or not
    the walk went in. `os.walk` neither follows a link into a directory nor
    stops at one it cannot read, as `rglob` does not; `normcase` gives the
    extension the platform's case rule, as `rglob`'s match does; and a
    directory whose name matches is a match, as it is to `rglob`. On the
    factory (docs/findings/lf_suite_time/, 2026-10-12): 487 briefs both ways,
    in the same order, 29.95 s against 18.85 s warm -- the skipped directories
    held 384,372 of the tree's 1,524,870 entries.
    """
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in _SKIP_DIRS]
        for name in dirs + files:
            if os.path.normcase(name).endswith(".json"):
                p = Path(d, name)
                if _keep(p):
                    out.append(p)
    return sorted(out)


@functools.lru_cache(maxsize=None)
def _brief_paths():
    """Every brief in the repo: examples, recorded cold runs, workspaces.

    A PREDICATE RATHER THAN A LIST OF PATTERNS, deliberately. The first
    version of this spelled four globs and missed `level_factory/examples/`
    entirely -- it found 19 of 21 briefs and reported the corpus clean of a
    defect that was sitting in one of the 2. A walk cannot miss a directory
    shape nobody thought of.

    ONCE A SESSION (0.193.2). The three tests below each walked the whole
    factory: 58.3, 30.4 and 30.1 s of a 443.1 s suite (0.193.1's own run), for
    487 briefs in a tree of 1.5 million entries that grows with every cold
    run. The list is read once and shared, as a tuple, so no test can change
    what the next one reads.
    """
    assert _ROOT is not None, (
        "the factory root is not above %s -- set LF_DC_ROOT. A corpus sweep "
        "with no corpus passes and proves nothing."
        % Path(__file__).resolve().parent)
    return tuple(_corpus_walk(_ROOT))


def _archetype(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    a = d.get("archetype")
    return a if isinstance(a, str) and a else None


def test_the_corpus_is_not_empty():
    """A sweep over zero briefs passes and proves nothing (CLAUDE.md)."""
    paths = _brief_paths()
    assert len(paths) >= 20, [str(p) for p in paths]
    assert [p for p in paths if _archetype(p)], "no brief carries an archetype"


def test_every_brief_on_disk_resolves_or_is_a_named_defect():
    unresolved = {}
    for path in _brief_paths():
        a = _archetype(path)
        if a is None:
            continue
        try:
            _preset_for(a)
        except UnknownArchetype:
            unresolved.setdefault(a, []).append(
                str(path.relative_to(_ROOT)).replace("\\", "/"))
    new = {a: f for a, f in unresolved.items() if a not in _KNOWN_UNRESOLVABLE}
    assert not new, (
        "brief archetype(s) resolve to no preset and are not recorded in "
        "_KNOWN_UNRESOLVABLE: %s" % new)


def test_the_known_offenders_are_still_there():
    """If one gets fixed, this fails and the entry comes out. A stale
    exception list is how a fixed defect keeps looking open -- and how a
    reintroduced one keeps looking fixed."""
    seen = set()
    for path in _brief_paths():
        a = _archetype(path)
        if a is None:
            continue
        try:
            _preset_for(a)
        except UnknownArchetype:
            seen.add(a)
    assert seen == set(_KNOWN_UNRESOLVABLE), (
        "recorded %s, found %s" % (sorted(_KNOWN_UNRESOLVABLE), sorted(seen)))


# ---- the walk ----------------------------------------------------------------
#
# 0.193.2 walks the corpus once a session and never into a directory it
# discards. These hold it to what `rglob` found, to not looking where the
# predicate would refuse anyway, and to walking once.


def _tree(root):
    """A small factory: briefs where the corpus keeps them, a brief under each
    skipped directory, a `briefs` directory under one, JSON that is not a
    brief, and a directory named like one in a `briefs` directory."""
    for rel in ("level_factory/examples/a/brief.json",
                "docs/cold_runs/cold_1/briefs/mission_one.json",
                "docs/cold_runs/cold_1/briefs/notes.txt",
                "workspaces/w-ws/briefs/m.json",
                "workspaces/w-ws/missions/m/brief.json",
                "workspaces/w-ws/missions/m/other.json",
                "_runs/x/brief.json",
                "_runs/briefs/y.json",
                "deli_counter/build/briefs/z.json",
                "zoo/node_modules/p/brief.json",
                ".git/briefs/q.json",
                "lot/.git/objects/brief.json"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"archetype": "bank"}', encoding="utf-8")
    (root / "docs" / "briefs" / "folder.json").mkdir(parents=True)
    return root


def test_the_walk_finds_what_rglob_found(tmp_path):
    root = _tree(tmp_path / "factory")
    got = _corpus_walk(root)
    assert got == sorted(p for p in root.rglob("*.json") if _keep(p))
    assert [p.relative_to(root).as_posix() for p in got] == [
        "docs/briefs/folder.json",
        "docs/cold_runs/cold_1/briefs/mission_one.json",
        "level_factory/examples/a/brief.json",
        "workspaces/w-ws/briefs/m.json",
        "workspaces/w-ws/missions/m/brief.json",
    ]


def test_the_walk_never_enters_a_directory_it_discards(tmp_path, monkeypatch):
    root = _tree(tmp_path / "factory")
    real = os.scandir
    listed = []

    def spy(path=".", *args, **kwargs):
        listed.append(Path(os.fspath(path)))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", spy)
    _corpus_walk(root)
    assert root in listed, "the walk listed nothing, so this test proves nothing"
    entered = [p for p in listed if _SKIP_DIRS & set(p.relative_to(root).parts)]
    assert not entered, entered


def test_the_corpus_is_walked_once_a_session(monkeypatch):
    walks = []

    def counting(root):
        walks.append(root)
        return [Path("briefs", "a.json")]

    monkeypatch.setitem(globals(), "_corpus_walk", counting)
    _brief_paths.cache_clear()
    try:
        first, second = _brief_paths(), _brief_paths()
    finally:
        _brief_paths.cache_clear()
    assert walks == [_ROOT]
    assert first is second and isinstance(first, tuple)
