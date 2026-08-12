"""A content layer is resolved when it EXISTS, not when the spec is written.

The regression this exists to stop happened on 2026-08-06, AFTER the fan-out
landed and with a green suite over it. `probe_dressing.tscn` reported no
Dressing and no Fixtures node on any of five buildings, and the compose job's
log carried neither `--dressing` nor `--fixtures`.

`_layer_paths` globbed the producing job's out dir. `_job_specs_for_plan` runs
BEFORE ANY JOB EXECUTES, so for the new per-building job ids every glob came
back empty and every flag was silently dropped.

`test_fanout.py` passed throughout, because its fixture PRE-CREATES those files
(`_specs(..., publish=True)`) -- its own docstring says the bug is only visible
once they exist, "which is the state every run after the first is in". That is
exactly the assumption that was wrong: for a job id that has never run, it is
always the first run.

So every test here builds specs with `publish=False`. That is the real
condition at spec time, and it is the one the old suite never exercised.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.presentation import PresentationAdapter  # noqa: E402
from test_fanout import (  # noqa: E402
    LOT, _brief, _compose_args, _flag, _library, _plan, _specs,
)


# ---------------------------------------------------------------------------
# resolve_layer, on its own
# ---------------------------------------------------------------------------
def test_one_file_resolves(tmp_path):
    from adapters.presentation import resolve_layer
    (tmp_path / "final_stand_dressing.glb").write_bytes(b"glb")
    path, problem = resolve_layer(str(tmp_path), "_dressing.glb")
    assert problem == ""
    assert path.endswith("final_stand_dressing.glb")


def test_an_empty_directory_is_a_problem_not_an_empty_answer(tmp_path):
    """The old code returned "" here and composed a bare building, exit 0."""
    from adapters.presentation import resolve_layer
    path, problem = resolve_layer(str(tmp_path), "_dressing.glb")
    assert path == ""
    assert "no '*_dressing.glb'" in problem
    assert "reported success without publishing one" in problem


def test_a_missing_directory_says_so(tmp_path):
    from adapters.presentation import resolve_layer
    path, problem = resolve_layer(str(tmp_path / "never"), "_dressing.glb")
    assert path == ""
    assert "layer directory missing" in problem


def test_two_layers_are_refused_rather_than_chosen_between(tmp_path):
    from adapters.presentation import resolve_layer
    (tmp_path / "a_dressing.glb").write_bytes(b"glb")
    (tmp_path / "b_dressing.glb").write_bytes(b"glb")
    path, problem = resolve_layer(str(tmp_path), "_dressing.glb")
    assert path == ""
    assert "no basis for choosing" in problem


def test_the_sidecar_json_is_not_mistaken_for_the_layer(tmp_path):
    """Zoo publishes `<bid>_dressing.built.json` beside `<bid>_dressing.glb`."""
    from adapters.presentation import resolve_layer
    (tmp_path / "final_stand_dressing.glb").write_bytes(b"glb")
    (tmp_path / "final_stand_dressing.built.json").write_text("{}")
    path, problem = resolve_layer(str(tmp_path), "_dressing.glb")
    assert problem == ""
    assert path.endswith(".glb")


# ---------------------------------------------------------------------------
# the ordering property -- the one that was actually wrong
# ---------------------------------------------------------------------------
def test_the_spec_names_a_directory_that_need_not_exist_yet(tmp_path, monkeypatch):
    """Spec time cannot see any job's output. It may only construct."""
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    compose_jid = [j for j in plan.graph.jobs()
                   if j.stage_id == "presentation_compose"][0].job_id

    layers = specs[compose_jid]["dressing_glb"]
    assert isinstance(layers, dict) and len(layers) == LOT
    for aid, value in layers.items():
        assert value, f"{aid} got an empty layer value at spec time"
        assert not str(value).endswith(".glb"), (
            f"{aid}: the spec named a FILE ({value}). Spec time runs before "
            f"the job that writes it, so a filename here can only have been "
            f"guessed or found stale.")


def test_layers_resolve_after_the_bakes_run_not_before(tmp_path, monkeypatch):
    """The whole defect, as one assertion.

    Build the specs while the out dirs are EMPTY -- the real state at plan
    time. Then let the bakes 'run'. Only then may the layer resolve.
    """
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    compose_jid = [j for j in plan.graph.jobs()
                   if j.stage_id == "presentation_compose"][0].job_id
    spec = specs[compose_jid]

    # nothing has run: every layer is unresolvable, and the adapter says so
    problems = PresentationAdapter().validate_configuration(
        spec, {"repository": ""})
    assert any("dressing_glb" in p for p in problems), (
        "a compose whose dressing has not been baked must be refused, not "
        "quietly composed without props")

    # the bakes run
    for aid, directory in spec["dressing_glb"].items():
        d = Path(directory); d.mkdir(parents=True, exist_ok=True)
        (d / f"{aid or 'shell'}_dressing.glb").write_bytes(b"glb")
    for aid, directory in spec["fixtures_glb"].items():
        d = Path(directory); d.mkdir(parents=True, exist_ok=True)
        (d / f"{aid or 'shell'}_fixtures.glb").write_bytes(b"glb")

    # now every building composes with its own, and they are all different
    dressings = [_flag(a, "--dressing") for a in _compose_args(spec, tmp_path)]
    attached = [d for d in dressings if d]
    assert len(attached) == LOT, (
        f"{len(attached)} of {LOT} buildings got a --dressing flag")
    assert len(set(attached)) == LOT, (
        f"{LOT} buildings share {len(set(attached))} bake(s): "
        + ", ".join(sorted({Path(d).name for d in attached})))


def test_a_bake_that_published_nothing_fails_the_job(tmp_path, monkeypatch):
    """Four of five is not a smaller version of the brief."""
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    compose_jid = [j for j in plan.graph.jobs()
                   if j.stage_id == "presentation_compose"][0].job_id
    spec = specs[compose_jid]

    items = sorted(spec["dressing_glb"].items())
    for aid, directory in items[1:]:          # all but the first publish
        d = Path(directory); d.mkdir(parents=True, exist_ok=True)
        (d / f"{aid or 'shell'}_dressing.glb").write_bytes(b"glb")
    for aid, directory in spec["fixtures_glb"].items():
        d = Path(directory); d.mkdir(parents=True, exist_ok=True)
        (d / f"{aid or 'shell'}_fixtures.glb").write_bytes(b"glb")

    problems = PresentationAdapter().validate_configuration(
        spec, {"repository": ""})
    missing = [p for p in problems if "dressing_glb" in p]
    assert len(missing) == 1, (
        "exactly the one unbaked building should be refused, and by name")
    assert items[0][0] in missing[0]


def test_the_fingerprint_does_not_open_a_directory(tmp_path, monkeypatch):
    """[Errno 13] Permission denied, on Windows, mid-run.

    The spec names a layer DIRECTORY. `fingerprint_inputs` hashed the value
    directly, and `Path(a_directory).exists()` is True, so it opened a
    directory as a file. Every reader of a spec key has to agree about what
    that key means.
    """
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    spec = specs[[j for j in plan.graph.jobs()
                  if j.stage_id == "presentation_compose"][0].job_id]
    for key, kind in (("dressing_glb", "dressing"), ("fixtures_glb", "fixtures")):
        for aid, directory in spec[key].items():
            d = Path(directory); d.mkdir(parents=True, exist_ok=True)
            (d / f"{aid or 'shell'}_{kind}.glb").write_bytes(b"glb")

    fp = PresentationAdapter().fingerprint_inputs(spec, {"repository": ""})
    hashed = [k for k in fp if k.startswith("dressing_glb_hash")]
    assert len(hashed) == LOT, f"hashed {len(hashed)} of {LOT} dressing layers"
    assert len(set(fp[k] for k in hashed)) >= 1


def test_the_fingerprint_survives_an_unbaked_layer(tmp_path, monkeypatch):
    """validate_configuration reports it; hashing must not crash first."""
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    spec = specs[[j for j in plan.graph.jobs()
                  if j.stage_id == "presentation_compose"][0].job_id]
    fp = PresentationAdapter().fingerprint_inputs(spec, {"repository": ""})
    assert not [k for k in fp if k.startswith("dressing_glb_hash")]
