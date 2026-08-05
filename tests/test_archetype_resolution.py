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
