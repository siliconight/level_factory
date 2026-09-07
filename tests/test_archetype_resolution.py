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

import json

_ROOT = Path(__file__).resolve().parents[2]

#: Briefs known to name an archetype no preset answers to, with the reason.
#: NOT a suppression list: a brief here is a defect somebody has to decide
#: about, and a brief NOT here that refuses fails this suite immediately.
#: Both are multi-building briefs using `archetype` to name a BLOCK, which is
#: why neither is fixed by an alias -- see roadmap 118's expensive half.
_KNOWN_UNRESOLVABLE = {
    "commercial_strip": "restaurant_row_001, 3 buildings, no lot_library",
    "mixed_block": "rockay_lot_demo_001, 5 buildings, HAS lot_library",
}


#: Directories whose briefs are scratch, not corpus: `_runs` is per-invocation
#: smoke output and `build` is generated.
_SKIP_DIRS = {"_runs", "build", "node_modules", ".git"}


def _brief_paths():
    """Every brief in the repo: examples, recorded cold runs, workspaces.

    A PREDICATE RATHER THAN A LIST OF PATTERNS, deliberately. The first
    version of this spelled four globs and missed `level_factory/examples/`
    entirely -- it found 19 of 21 briefs and reported the corpus clean of a
    defect that was sitting in one of the 2. A walk cannot miss a directory
    shape nobody thought of.
    """
    out = []
    for path in _ROOT.rglob("*.json"):
        if _SKIP_DIRS & set(path.parts):
            continue
        if path.name == "brief.json" or path.parent.name == "briefs":
            out.append(path)
    return sorted(out)


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
