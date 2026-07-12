"""Selective rebuild / invalidation classification (TDD 30).

Classifies a changed input as functional, presentation, or ambiguous so the
scheduler reruns the minimum necessary work. Ambiguous changes (a Zoo asset
with collision, a Patina op that moves geometry) are treated as FUNCTIONAL until
proven otherwise (30.3) -- the conservative default.
"""
from __future__ import annotations

FUNCTIONAL = "functional"
PRESENTATION = "presentation"
AMBIGUOUS = "ambiguous"

# Change kinds that invalidate a functional lock (30.1).
_FUNCTIONAL_CHANGES = frozenset({
    "deli_spec", "lot_spec", "building_transform", "collision",
    "doorway_width", "cover_collision", "anchor_move", "nav_hint",
    "objective_route",
})

# Change kinds that normally preserve a functional lock (30.2).
_PRESENTATION_CHANGES = frozenset({
    "pixelcoat_material", "zoo_noncolliding_prop", "patina_palette",
    "patina_decal", "lux_preset", "lux_weather", "lux_post",
})

# Reruns triggered by a functional change (30.1).
_FUNCTIONAL_RERUNS = (
    "deli_or_lot", "laser_tag", "functional_approval",
    "presentation_compose", "regression", "dispatch",
)
# Reruns triggered by a presentation change (30.2).
_PRESENTATION_RERUNS = (
    "presentation_build", "lux_validation", "performance_regression",
    "visual_review", "dispatch_presentation",
)


def classify_change(change_kind: str) -> str:
    if change_kind in _FUNCTIONAL_CHANGES:
        return FUNCTIONAL
    if change_kind in _PRESENTATION_CHANGES:
        return PRESENTATION
    return AMBIGUOUS  # conservative: treat unknown as functional-worthy


def required_reruns(change_kind: str) -> tuple[str, ...]:
    kind = classify_change(change_kind)
    if kind == PRESENTATION:
        return _PRESENTATION_RERUNS
    # functional and ambiguous both take the safe, larger rerun set.
    return _FUNCTIONAL_RERUNS


def invalidates_functional_lock(change_kind: str) -> bool:
    return classify_change(change_kind) in (FUNCTIONAL, AMBIGUOUS)
