"""`--force` does what its name promises (roadmap 93, the residue).

Its help text read "accepted and ignored: every stage is now always
re-evaluated against the cache", and the scheduler's docstring agreed. That is
a flag whose name promises exactly what a stuck user wants and whose body does
nothing -- two full pipeline runs were spent on it on 2026-08-30 before
`cache forget <job_id>` was found by reading the CLI.

This is that command applied to the whole plan. The digest comes from each
job's own receipt, `fingerprint.last.json`, the same way `cmd_cache` reads it:
naming the JOB rather than computing a digest by hand.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.cli import commands  # noqa: E402


class _Cache:
    def __init__(self):
        self.forgotten = []

    def forget(self, digest):
        self.forgotten.append(digest)
        return True


def _plan(*job_ids):
    jobs = [SimpleNamespace(job_id=j) for j in job_ids]
    return SimpleNamespace(graph=SimpleNamespace(jobs=lambda: jobs))


def _ws(tmp_path):
    return SimpleNamespace(jobs_dir=tmp_path / "jobs")


def _receipt(ws, job_id, digest):
    d = ws.jobs_dir / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "fingerprint.last.json").write_text(json.dumps({"digest": digest}),
                                              encoding="utf-8")


def test_every_planned_job_with_a_receipt_is_forgotten(tmp_path, monkeypatch):
    """THE POINT."""
    cache = _Cache()
    monkeypatch.setattr(commands, "_cache", lambda ws: cache)
    ws = _ws(tmp_path)
    _receipt(ws, "m.deli_generate.candidate.seed_1", "aaa")
    _receipt(ws, "m.presentation_compose", "bbb")
    forgotten, missing = commands._forget_plan(
        ws, _plan("m.deli_generate.candidate.seed_1", "m.presentation_compose"))
    assert forgotten == 2 and missing == 0
    assert sorted(cache.forgotten) == ["aaa", "bbb"]


def test_a_job_never_evaluated_here_is_counted_not_raised(tmp_path, monkeypatch):
    """A fresh workspace has no receipts at all, and `--force` on a first run
    must not be an error -- there is simply nothing to forget yet."""
    cache = _Cache()
    monkeypatch.setattr(commands, "_cache", lambda ws: cache)
    ws = _ws(tmp_path)
    _receipt(ws, "m.a", "aaa")
    forgotten, missing = commands._forget_plan(ws, _plan("m.a", "m.never_ran"))
    assert (forgotten, missing) == (1, 1)
    assert cache.forgotten == ["aaa"]


def test_an_unreadable_receipt_is_missing_not_fatal(tmp_path, monkeypatch):
    cache = _Cache()
    monkeypatch.setattr(commands, "_cache", lambda ws: cache)
    ws = _ws(tmp_path)
    d = ws.jobs_dir / "m.broken"
    d.mkdir(parents=True)
    (d / "fingerprint.last.json").write_text("{not json", encoding="utf-8")
    assert commands._forget_plan(ws, _plan("m.broken")) == (0, 1)
    assert cache.forgotten == []


def test_the_help_text_no_longer_says_ignored():
    """The defect was a flag that said it did nothing and was reached for
    anyway. Pinned on the text, because that is where the promise is made."""
    main = (ROOT / "apps" / "cli" / "main.py").read_text(encoding="utf-8")
    assert "accepted and ignored" not in main
    assert "forget every planned job" in main
