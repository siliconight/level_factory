"""`walk` must open the assembled site, not the compose intermediate.

Measured 2026-08-08 on `lot_demo_001`, a five-building themed lot. The run
succeeded end to end -- five fixture bakes, five dressing bakes, five distinct
composed scenes, `themed_site_assemble` placing them -- and then `walk` wrapped
`presentation_compose/out/presentation/site.tscn`: 47,272 bytes referencing one
`site_base.glb`. The review frame shows ONE BUILDING against 86.7% void.

The five-building scene was 26,731 bytes in the next job's output directory and
nothing opened it. `cmd_walk` predates the varied lot; its docstring says it
wraps "the composed themed level", which for a varied lot is not one scene.

Both self-checks passed. `walk_bot` reported `ok: true` with the note "no
ladder_area3d in scene; traversal vacuous". `shot_bot` reported `[OK]` because
`st["ok"] = jitter <= JITTER_FAIL_PCT` -- the void fraction is measured, stored,
printed beside the word OK, and never enters the verdict.

THE RULE IS NOT "IF THE LOT IS VARIED". `themed_site_assemble` is the last
stage that makes a PLACE: it puts buildings on ground. Compose makes a content
package for one building. That is true for a single-shell mission too, so this
prefers the site whenever there is one and does not branch on lot size -- a
branch here would be a second derivation of "is this a varied lot" living
somewhere new.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli.commands import walk_content_dir      # noqa: E402


def _site(jobs: Path, mission: str, *, scene=True) -> Path:
    d = jobs / f"{mission}.themed_site_assemble" / "out"
    d.mkdir(parents=True, exist_ok=True)
    if scene:
        (d / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
        (d / "site_walk.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return d


def _compose(jobs: Path, mission: str) -> Path:
    d = jobs / f"{mission}.presentation_compose" / "out" / "presentation"
    d.mkdir(parents=True, exist_ok=True)
    (d / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return d


def test_the_assembled_site_wins_over_the_compose_output(tmp_path):
    """The one that was wrong. Both directories exist after every --art run,
    and the old code named the compose one unconditionally."""
    site = _site(tmp_path, "lot_demo_001")
    _compose(tmp_path, "lot_demo_001")
    chosen, stage = walk_content_dir(tmp_path, "lot_demo_001")
    assert chosen == site
    assert stage == "themed_site_assemble"


def test_it_falls_back_to_compose_when_the_site_stage_never_ran(tmp_path):
    """A gameplay-only or greybox run has no themed site. Walking the compose
    output is right there, and is what this always did."""
    compose = _compose(tmp_path, "m1")
    chosen, stage = walk_content_dir(tmp_path, "m1")
    assert chosen == compose
    assert stage == "presentation_compose"


def test_a_site_directory_with_no_scene_is_not_chosen(tmp_path):
    """The job dir exists the moment the scheduler creates it, before the tool
    writes anything. Existence of the DIRECTORY is not evidence of a scene --
    that distinction is the whole of `resolve_layer`'s docstring."""
    _site(tmp_path, "m2", scene=False)
    compose = _compose(tmp_path, "m2")
    chosen, stage = walk_content_dir(tmp_path, "m2")
    assert chosen == compose
    assert stage == "presentation_compose"


def test_neither_present_answers_none_rather_than_a_path(tmp_path):
    chosen, stage = walk_content_dir(tmp_path, "never_ran")
    assert chosen is None
    assert stage == ""


def test_the_walk_scene_is_not_mistaken_for_the_level(tmp_path):
    """`themed_site_assemble` publishes `site_walk.tscn` beside `site.tscn`.
    `_find_level_scene` skips `*_walk.tscn`; this pins that the directory this
    function hands over still contains the real scene to find."""
    from packages.preview.walk_preview import _find_level_scene
    site = _site(tmp_path, "m3")
    chosen, _ = walk_content_dir(tmp_path, "m3")
    assert chosen == site
    assert _find_level_scene(chosen) == "site.tscn"
