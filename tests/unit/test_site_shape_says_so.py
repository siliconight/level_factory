"""A `site_shape` nobody added is not the same as a `site_shape` that means row
(roadmap 100).

`shape_of` falls back to "row" for any spelling `_SHAPE_ALIASES` does not
carry, and the comment defending that was right: refusing a build over a
label is the wrong trade. What was wrong is that the fallback left no trace.
A census of every brief on disk on 2026-09-11:

    street_block         7     boardwalk_crescent   4     yard      3
    strip                3     street_row           3     row       2
    courtyard            2     campus               2     string    1

Seventeen of twenty-seven asked for a shape the table did not know, and every
one of them silently became a row -- including both of the two most recent
cold runs, `warehouse_yard_001` ("yard") and `county_hospital_001` ("campus").
A wrong-but-plausible SITE is the archetype defect one level up: `_preset_for`
used to end in `return "bank"`, and every lot-demo mission built banks.

THE TEST THAT MATTERS IS `test_an_unknown_spelling_is_distinguishable_from_row`.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.pipeline import site_variation as sv  # noqa: E402


def test_an_unknown_spelling_is_distinguishable_from_row():
    """THE POINT. Both resolve to a row; only one of them MEANT a row."""
    assert sv.shape_of("street_row") == "row" and sv.shape_known("street_row")
    assert sv.shape_of("string") == "row" and not sv.shape_known("string")


def test_the_fallback_is_kept():
    """Refusing a build over a label is the wrong trade, and the original
    comment was right about that. Unknown still lays out -- it just says so."""
    assert sv.shape_of("no_such_shape") == "row"
    assert sv.shape_of(None) == "row"


@pytest.mark.parametrize("spelling,shape", [
    ("street_block", "row"),          # 7 briefs: buildings along a street
    ("yard", "row"),                  # 3 briefs: two buildings across a yard
    ("boardwalk_crescent", "L"),      # 4 briefs: a crescent bends once
    ("campus", "courtyard"),          # 2 briefs: buildings around a quad
])
def test_the_spellings_the_briefs_use_are_known(spelling, shape):
    """Added deliberately and once, each as a stated reading of the word."""
    assert sv.shape_known(spelling)
    assert sv.shape_of(spelling) == shape


def test_a_typo_is_left_unknown_on_purpose():
    """`string` is one brief and a typo of something. Guessing which would be
    the defect this closes, so it stays unknown and the writer says so."""
    assert not sv.shape_known("string")


def test_an_empty_shape_means_row_and_is_known():
    """A brief that says nothing gets a row deliberately. That is a choice the
    table makes, not a word it failed to recognise."""
    assert sv.shape_known("") and sv.shape_known(None)


def test_known_spellings_is_what_the_message_lists():
    known = sv.known_spellings()
    assert "" not in known                    # the empty key is not a spelling
    assert "courtyard" in known and "campus" in known
    assert known == sorted(known)


def test_every_shipped_brief_resolves_to_a_known_shape():
    """The corpus a newcomer copies. `string` is the one deliberate exception
    and is named, so this fails the moment a second unknown spelling ships."""
    import json
    briefs = sorted((ROOT / "examples").rglob("*.json")) + \
        sorted((ROOT.parent / "docs" / "cold_runs").rglob("briefs/*.json"))
    if not briefs:
        pytest.skip("no briefs beside the checkout")
    unknown = []
    for b in briefs:
        try:
            d = json.loads(b.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "site_shape" not in d:
            continue
        if not sv.shape_known(d["site_shape"]):
            unknown.append((b.name, d["site_shape"]))
    assert all(s == "string" for _, s in unknown), unknown
