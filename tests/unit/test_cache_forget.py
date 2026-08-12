"""`cache forget` — drop a cached answer that was recorded from a bad build.

A cache entry records the outputs a build produced. When a build produced the
WRONG outputs, the entry is not stale, it is POISONED: the fingerprint covers
the inputs, the inputs did not change, so re-running cannot notice. Measured
2026-08-09 — a leftover in a reused work dir was swept up by `collect_outputs`,
published as a legitimate output and recorded in the manifest. Clearing the
work dir stopped new adoptions and did nothing for the entry already written; a
cache hit materialized the leftover straight back.

Removing the manifest by hand was the only way through, and a step that must be
done by hand is a step that gets skipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.artifacts.cache import ContentCache


def _published(tmp_path: Path):
    cache = ContentCache(tmp_path / "cache")
    root = tmp_path / "out"
    root.mkdir()
    (root / "wall.glb").write_bytes(b"glb")
    fp = "sha256:" + "a" * 64
    cache.publish(fingerprint=fp, adapter_id="zoo", job_id="j1",
                  output_root=root, output_files=[root / "wall.glb"],
                  validation_status="PASS")
    return cache, fp


def test_forget_makes_the_next_lookup_a_miss(tmp_path):
    """The falsifier: the point is that the job runs again."""
    cache, fp = _published(tmp_path)
    assert cache.lookup(fp) is not None
    assert cache.forget(fp) is True
    assert cache.lookup(fp) is None


def test_forget_leaves_the_blobs_for_prune(tmp_path):
    """Blobs are content-addressed and SHARED. Another fingerprint may
    reference the same bytes, so forgetting one entry must not reach past it."""
    cache, fp = _published(tmp_path)
    before = cache.inspect()["blob_count"]
    cache.forget(fp)
    assert cache.inspect()["blob_count"] == before
    # ...and prune is what collects them, once nothing refers to them.
    assert cache.prune()["removed_blobs"] == before


def test_forgetting_what_was_never_cached_is_not_an_error(tmp_path):
    """A caller clearing a suspect job should not have to know whether it had
    an entry; 'there was nothing to drop' is an answer, not a failure."""
    cache = ContentCache(tmp_path / "cache")
    assert cache.forget("sha256:" + "b" * 64) is False


def test_forget_does_not_disturb_other_entries(tmp_path):
    cache, fp = _published(tmp_path)
    root = tmp_path / "out2"
    root.mkdir()
    (root / "roof.glb").write_bytes(b"other")
    other = "sha256:" + "c" * 64
    cache.publish(fingerprint=other, adapter_id="zoo", job_id="j2",
                  output_root=root, output_files=[root / "roof.glb"],
                  validation_status="PASS")
    cache.forget(fp)
    assert cache.lookup(other) is not None
