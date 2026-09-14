"""The consumer's freshness guard reads Deli Counter's rule, or says it cannot.

Cold run 9053, 2026-09-14: `building_library._geometry_sources` cut the
`GEOMETRY_SOURCES` tuple out of `build_freshness.py` with a regex that stopped at
the first ")". Deli Counter 0.116.0 had written a comment inside the tuple
ending "(0.116.0)", so `literal_eval` failed, the guard returned [] and printed
nothing over a library 130 of 132 shells stale. The export was refused by the
placement gate four stages later.
"""
import hashlib
import json
import os

from packages.pipeline import building_library as bl

# the shape Deli Counter's file has had since 0.116.0: a comment with a paren
_RULE = '''GEOMETRY_SOURCES = (
    "deli_counter.py",      # the builder itself
    "lights.py",            # the light manifest is a build output (0.116.0)
    "stairwell.py",
)
'''


def _library(tmp_path, rule=_RULE, shell_mtime=2000, source_mtime=1000):
    src = tmp_path / "deli_counter"
    (src / "build").mkdir(parents=True)
    (src / "build_freshness.py").write_text(rule, encoding="utf-8")
    for name in ("deli_counter.py", "lights.py", "stairwell.py"):
        p = src / name
        p.write_text("x")
        os.utime(p, (source_mtime, source_mtime))
    glb = src / "build" / "shop.glb"
    glb.write_bytes(b"glTF-built")
    os.utime(glb, (shell_mtime, shell_mtime))
    return src


def test_a_comment_with_a_parenthesis_inside_the_tuple_is_read(tmp_path):
    src = _library(tmp_path)
    got = bl._geometry_sources(src)
    assert got is not None
    assert sorted(p.name for p in got) == ["deli_counter.py", "lights.py", "stairwell.py"]


def test_a_shell_older_than_the_rule_is_named(tmp_path):
    src = _library(tmp_path, shell_mtime=1000, source_mtime=5000)
    names, worst = bl.stale_shells(src / "build")
    assert names == ["shop.glb"] and worst > 0


def test_an_unreadable_rule_is_unknown_not_fresh(tmp_path):
    src = _library(tmp_path, rule="GEOMETRY_SOURCES = tuple(sorted(NAMES))\n")
    assert bl.stale_shells(src / "build") == (None, 0.0)


def test_no_rule_at_all_is_nothing_to_apply(tmp_path):
    src = _library(tmp_path)
    (src / "build_freshness.py").unlink()
    assert bl.stale_shells(src / "build") == ([], 0.0)


def test_a_glb_that_is_not_its_manifests_build_is_stale(tmp_path):
    """Newer than every source, so mtime calls it fresh; the tracked manifest
    records a different build (the untracked shell a checkout leaves behind)."""
    src = _library(tmp_path, shell_mtime=9000, source_mtime=1000)
    other = hashlib.sha256(b"glTF-rebuilt").hexdigest()[:16]
    (src / "build" / "shop.manifest.json").write_text(
        json.dumps({"outputs_sha256_16": {"shop.glb": other}}))
    names, _ = bl.stale_shells(src / "build")
    assert names == ["shop.glb"]


def test_a_manifest_recording_this_glb_keeps_it_fresh(tmp_path):
    src = _library(tmp_path, shell_mtime=9000, source_mtime=1000)
    mine = hashlib.sha256(b"glTF-built").hexdigest()[:16]
    (src / "build" / "shop.manifest.json").write_text(
        json.dumps({"outputs_sha256_16": {"shop.glb": mine}}))
    assert bl.stale_shells(src / "build") == ([], 0.0)
