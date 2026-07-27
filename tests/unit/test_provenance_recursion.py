"""Provenance sidecars are records ABOUT artifacts, never artifacts.

Recording them as outputs compounds. `collect_outputs` rglobs a job's work
directory, and a job directory is reused across runs, so every run swept up the
previous run's sidecars and wrote a sidecar for each -- one extra level of
`site.tscn.provenance.json.provenance.json...` per run, forever.

It was carried as a cosmetic annoyance for eleven levels. At seventeen it
stopped being cosmetic: the path passed Windows' MAX_PATH and the run died with
`[Errno 22] Invalid argument` on a filename nobody had chosen, before any stage
had done any work. Growth that is merely ugly at one scale is a hard failure at
another, and nothing in between announces the change.
"""
from __future__ import annotations

from pathlib import Path

from packages.jobs.scheduler import PROVENANCE_SUFFIX, _without_provenance


def test_a_sidecar_is_not_an_artifact(tmp_path):
    scene = tmp_path / "site.tscn"
    sidecar = tmp_path / ("site.tscn" + PROVENANCE_SUFFIX)
    kept = _without_provenance([scene, sidecar])
    assert kept == [scene]


def test_the_nesting_that_actually_shipped_is_refused_at_every_depth(tmp_path):
    """Eleven deep was the recorded state; seventeen is what broke the run. No
    depth may re-enter the output set, or the next run adds another."""
    name = "site.site.gameplay.json"
    paths = [tmp_path / name]
    for _ in range(20):
        name += PROVENANCE_SUFFIX
        paths.append(tmp_path / name)
    kept = _without_provenance(paths)
    assert kept == [tmp_path / "site.site.gameplay.json"]


def test_a_file_merely_mentioning_provenance_is_still_an_artifact(tmp_path):
    """The filter keys on the suffix, not the substring. A real output called
    `provenance_report.json` is a deliverable and must survive."""
    real = tmp_path / "provenance_report.json"
    also = tmp_path / "site.provenance.json.tscn"
    kept = _without_provenance([real, also])
    assert kept == [real, also]


def test_the_filter_is_order_preserving_and_takes_any_iterable(tmp_path):
    """It is applied to a generator at the collect site and to a list when
    recording, so it must accept both and not reshuffle the outputs."""
    a, b, c = (tmp_path / n for n in ("z.tscn", "a.glb", "m.json"))
    sidecar = tmp_path / ("a.glb" + PROVENANCE_SUFFIX)
    assert _without_provenance(iter([a, sidecar, b, c])) == [a, b, c]
