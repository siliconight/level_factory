"""The Layer 3 chain, as level_factory jobs.

Three tools, three jobs, each producing what the next consumes:

    zoo   --measure_shapes        -> <name>.metrics.json   (measured GLBs)
    lot   (site_surfaces)         -> surfaces.json         (dressable zones)
    patina --mode surface_dressing-> <site>.surface_dressing.json

These tests are about the WIRING, not the planning -- Patina's own suite covers
the gates. What can go wrong here is different in kind: a command that is never
planned, an input that is not in the fingerprint, or a version that was not
bumped when the commands changed. Each of those is silent, and each produces a
cache hit that ships the wrong thing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.patina import PatinaAdapter
from adapters.zoo import SHAPE_METRICS, ZooAdapter


def ctx(tmp_path, repo=None):
    return {"work_dir": str(tmp_path),
            "repository": str(repo or tmp_path),
            "python_executable": "python"}


# --- Zoo measures what it built --------------------------------------------

def test_shape_metrics_is_where_the_adapter_thinks_it_is():
    """The path is walked up from the adapter's own location. If the repo
    layout moves, this fails here rather than by silently never measuring."""
    assert SHAPE_METRICS.is_file(), SHAPE_METRICS
    assert SHAPE_METRICS.name == "shape_metrics.py"


def test_measure_adds_a_second_command(tmp_path):
    a = ZooAdapter()
    spec = {"mode": "dress", "manifest_path": str(tmp_path / "m.json"),
            "measure_shapes": True}
    (tmp_path / "m.json").write_text("{}", encoding="utf-8")
    cmds = a.plan_commands(spec, ctx(tmp_path))
    assert len(cmds) == 2
    assert "shape_metrics.py" in " ".join(cmds[-1].arguments)
    assert cmds[-1].expected_outputs == ("shapes.metrics.json",)


def test_no_measure_flag_means_no_extra_command(tmp_path):
    """Falsification: the step must be opt-in, or every existing zoo job grows
    a command it never asked for."""
    a = ZooAdapter()
    (tmp_path / "m.json").write_text("{}", encoding="utf-8")
    cmds = a.plan_commands(
        {"mode": "dress", "manifest_path": str(tmp_path / "m.json")},
        ctx(tmp_path))
    assert len(cmds) == 1


def test_the_measure_command_writes_to_a_file_not_stdout(tmp_path):
    """A PlannedCommand is argv without a shell. A tool that only writes to
    stdout cannot be a pipeline step, which is why shape_metrics grew --out."""
    a = ZooAdapter()
    (tmp_path / "m.json").write_text("{}", encoding="utf-8")
    cmds = a.plan_commands({"mode": "dress",
                            "manifest_path": str(tmp_path / "m.json"),
                            "measure_shapes": True}, ctx(tmp_path))
    args = cmds[-1].arguments
    assert "--out" in args
    assert ">" not in " ".join(args)


def test_measuring_changes_the_fingerprint(tmp_path):
    """Otherwise a job that starts measuring cache-hits the entry from before
    it did, and the metrics sidecar is never produced."""
    a = ZooAdapter()
    base = {"mode": "dress", "manifest_path": str(tmp_path / "m.json")}
    (tmp_path / "m.json").write_text("{}", encoding="utf-8")
    plain = a.fingerprint_inputs(base, ctx(tmp_path))
    measured = a.fingerprint_inputs({**base, "measure_shapes": True},
                                    ctx(tmp_path))
    assert plain != measured
    assert "shape_metrics_hash" in measured


def test_the_measuring_tools_own_source_is_an_input(tmp_path):
    """A change to how a footprint is computed changes the catalogue the
    planner is built from, with every other input byte-identical. That is the
    executes-a-sub-tool problem test_presentation_fingerprint documents."""
    a = ZooAdapter()
    (tmp_path / "m.json").write_text("{}", encoding="utf-8")
    fp = a.fingerprint_inputs({"mode": "dress",
                               "manifest_path": str(tmp_path / "m.json"),
                               "measure_shapes": True}, ctx(tmp_path))
    assert fp["shape_metrics_hash"]


def test_zoo_adapter_version_was_bumped():
    """The commands an adapter plans are not otherwise in the fingerprint.
    Without the bump, every existing entry cache-hits."""
    assert ZooAdapter.adapter_version >= "0.4.0"
    assert "measure_shapes" in ZooAdapter.capabilities


# --- Patina plans the dressing ---------------------------------------------

def _dress_spec(tmp_path):
    for name in ("surfaces.json", "metrics.json", "sets.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    return {
        "mode": "surface_dressing",
        "surfaces_path": str(tmp_path / "surfaces.json"),
        "metrics_path": str(tmp_path / "metrics.json"),
        "asset_sets_path": str(tmp_path / "sets.json"),
        "site_id": "coldrun_pawn_job",
        "source": "coldrun_pawn_job.site.tscn",
    }


def test_dressing_mode_plans_the_planner(tmp_path):
    a = PatinaAdapter()
    cmds = a.plan_commands(_dress_spec(tmp_path), ctx(tmp_path))
    assert len(cmds) == 1
    args = " ".join(cmds[0].arguments)
    assert "patina.surface_dressing" in args
    assert "patina.cli" not in args
    assert cmds[0].expected_outputs == \
        ("coldrun_pawn_job.surface_dressing.json",)


def test_dressing_mode_always_audits(tmp_path):
    """An illegal plan must fail the JOB, not travel downstream to be
    discovered by a level that does not walk right."""
    a = PatinaAdapter()
    cmds = a.plan_commands(_dress_spec(tmp_path), ctx(tmp_path))
    assert "--audit" in cmds[0].arguments


def test_dressing_mode_wants_no_input_glb(tmp_path):
    """Layer 3 dresses an assembled site, not a shell. Requiring an input_glb
    here would be the Layer 2 job wearing a Layer 3 name."""
    a = PatinaAdapter()
    assert a.validate_configuration(_dress_spec(tmp_path), ctx(tmp_path)) == []


def test_dressing_mode_requires_the_source_it_was_planned_against(tmp_path):
    spec = _dress_spec(tmp_path)
    del spec["source"]
    problems = PatinaAdapter().validate_configuration(spec, ctx(tmp_path))
    assert any("source" in p for p in problems)


def test_a_missing_upstream_artifact_is_a_configuration_error(tmp_path):
    spec = _dress_spec(tmp_path)
    spec["surfaces_path"] = str(tmp_path / "nope.json")
    problems = PatinaAdapter().validate_configuration(spec, ctx(tmp_path))
    assert any("surfaces_path" in p for p in problems)


def test_budgets_reach_the_command_as_strings(tmp_path):
    """"auto" and "none" are meaningful values. int()-ing them in the adapter
    would turn a legitimate setting into a crash at job time instead of a
    choice at configuration time."""
    a = PatinaAdapter()
    spec = {**_dress_spec(tmp_path), "instance_budget": "auto",
            "tri_budget": "none"}
    args = a.plan_commands(spec, ctx(tmp_path))[0].arguments
    assert "--instance-budget" in args and "auto" in args
    assert "--tri-budget" in args and "none" in args


def test_the_budgets_are_in_the_fingerprint(tmp_path):
    """Two plans that differ only by budget are two different plans."""
    a = PatinaAdapter()
    spec = _dress_spec(tmp_path)
    lo = a.fingerprint_inputs({**spec, "instance_budget": 500}, ctx(tmp_path))
    hi = a.fingerprint_inputs({**spec, "instance_budget": 5000}, ctx(tmp_path))
    assert lo != hi


def test_every_upstream_artifact_is_hashed(tmp_path):
    fp = PatinaAdapter().fingerprint_inputs(_dress_spec(tmp_path),
                                            ctx(tmp_path))
    for key in ("surfaces_path_hash", "metrics_path_hash",
                "asset_sets_path_hash"):
        assert key in fp, key


def test_dressing_and_art_modes_fingerprint_differently(tmp_path):
    """Falsification: if the mode were not in the fingerprint, a site dressing
    job could serve a shell art job's cached entry."""
    a = PatinaAdapter()
    glb = tmp_path / "shell.glb"
    glb.write_bytes(b"glTF stub")
    art = a.fingerprint_inputs({"input_glb": str(glb)}, ctx(tmp_path))
    dress = a.fingerprint_inputs(_dress_spec(tmp_path), ctx(tmp_path))
    assert art != dress
    assert dress["mode"] == "surface_dressing"


def test_patina_adapter_version_was_bumped():
    assert PatinaAdapter.adapter_version >= "0.4.0"
    assert "surface_dressing" in PatinaAdapter.capabilities


def test_the_art_path_is_untouched(tmp_path):
    """Everything above is additive. A job with no mode must plan exactly what
    it planned before."""
    a = PatinaAdapter()
    glb = tmp_path / "shell.glb"
    glb.write_bytes(b"glTF stub")
    cmds = a.plan_commands({"input_glb": str(glb)}, ctx(tmp_path))
    assert len(cmds) == 1
    assert "patina.cli" in " ".join(cmds[0].arguments)
