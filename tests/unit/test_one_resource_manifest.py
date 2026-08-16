"""Roadmap 50: a package carries one resource manifest, and it is current.

`resource_manifest.json` is `dispatch.resource_manifest.v0.2`, written by the
handoff stage about the handoff. `export_mission` copies that directory in,
then overwrites `mission.tscn` with its own portable entry and adds the
composed building and its art -- so Dispatch's file ends up describing a
package that does not exist. Measured on unlit_probe_001, 2026-08-16: it
recorded `mission.tscn` at 16,246 bytes beside a 688-byte file, and listed 17
entries for a 56-file package, while `portable_resource_manifest.json` beside
it carried all 58 resources with a sha256 and size each.

Two manifests, and the stale one has the more authoritative name.

Run:  python -m pytest tests/unit/test_one_resource_manifest.py
"""
import inspect

from packages.exporting import export as E


def test_the_handoff_copy_skips_dispatch_manifest():
    src = inspect.getsource(E.export_mission)
    head = src[:src.index("_copy_tree(base_dir")]
    assert 'skip |= {"resource_manifest.json"}' in head, (
        "the handoff directory is copied with `skip`, so the exclusion has to "
        "be in the set BEFORE that copy runs")


def test_it_is_dropped_not_merely_renamed():
    """A rename would leave two manifests with one confusing name each."""
    src = inspect.getsource(E.export_mission)
    assert "resource_manifest.json" not in src.split(
        'skip |= {"resource_manifest.json"}')[1].split("_copy_tree(base_dir")[0]


def test_the_precedent_it_follows_is_still_there():
    """The composed-root copy skips the composer's own portable manifest for
    the same reason. If that ever goes away this exclusion is orphaned and
    somebody should notice here."""
    src = inspect.getsource(E.export_mission)
    assert '"portable_resource_manifest.json"' in src


def test_copy_tree_honours_a_basename_skip(tmp_path):
    """The mechanism itself, not just the spelling -- `skip` matches
    basenames, so a file of that name is dropped wherever it sits."""
    src = tmp_path / "src"
    (src / "nested").mkdir(parents=True)
    (src / "resource_manifest.json").write_text("{}")
    (src / "nested" / "resource_manifest.json").write_text("{}")
    (src / "keep.json").write_text("{}")
    dst = tmp_path / "dst"
    E._copy_tree(src, dst, skip={"resource_manifest.json"})
    landed = sorted(p.relative_to(dst).as_posix()
                    for p in dst.rglob("*") if p.is_file())
    assert landed == ["keep.json"], landed
