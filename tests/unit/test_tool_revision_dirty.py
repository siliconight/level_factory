"""The tool revision a build runs on -- HEAD plus uncommitted tracked edits.

Regression cover for a silent staleness bug: a Deli Counter fix to the ladder
slab-hole (bias the cut onto the approach side so a climbing capsule fits)
never reached a shipped package, because the fix was on disk but not yet
committed. ``git rev-parse HEAD`` was unchanged, so the build fingerprint was
unchanged, so every rebuild cache-hit the pre-fix shell and the ladder stayed
unclimbable. Nothing failed; the pipeline just kept handing back the old
artifact.

The contract these tests pin:
  - clean tree            -> the bare HEAD sha (cheap, unchanged behaviour)
  - tracked file edited   -> a DIFFERENT revision string
  - edit reverted         -> back to the original revision (content, not mtime)
  - untracked file added  -> revision UNCHANGED (pipelines write generated
                             specs and work dirs into tool repos; folding
                             those in would break caching on every run)
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.sdk import BaseAdapter


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "toolrepo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "ladder_geom.py").write_text("HOLE_ALONG = 1.1\n", encoding="utf-8")
    _git(r, "add", "ladder_geom.py")
    _git(r, "commit", "-qm", "initial")
    return r


def test_clean_tree_is_the_bare_head_sha(repo: Path):
    rev = BaseAdapter._read_git_commit(repo)
    assert rev is not None and "+dirty" not in rev
    assert len(rev) == 40


def test_uncommitted_tracked_edit_changes_the_revision(repo: Path):
    before = BaseAdapter._read_git_commit(repo)
    (repo / "ladder_geom.py").write_text("HOLE_ALONG = 1.3\n", encoding="utf-8")
    after = BaseAdapter._read_git_commit(repo)
    assert after != before, "an uncommitted fix must invalidate the cache"
    assert after.startswith(before + "+dirty.")


def test_reverting_the_edit_restores_the_revision(repo: Path):
    clean = BaseAdapter._read_git_commit(repo)
    (repo / "ladder_geom.py").write_text("HOLE_ALONG = 1.3\n", encoding="utf-8")
    dirty = BaseAdapter._read_git_commit(repo)
    # different content -> different marker
    (repo / "ladder_geom.py").write_text("HOLE_ALONG = 9.9\n", encoding="utf-8")
    assert BaseAdapter._read_git_commit(repo) != dirty
    # back to the committed content -> back to the clean sha
    (repo / "ladder_geom.py").write_text("HOLE_ALONG = 1.1\n", encoding="utf-8")
    assert BaseAdapter._read_git_commit(repo) == clean


def test_untracked_files_do_not_churn_the_revision(repo: Path):
    clean = BaseAdapter._read_git_commit(repo)
    specs = repo / "specs"
    specs.mkdir()
    (specs / "lf_mission_5017.json").write_text("{}", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "shell.glb").write_bytes(b"glb")
    assert BaseAdapter._read_git_commit(repo) == clean, (
        "generated inputs written into a tool repo must not defeat the cache")


def test_non_git_directory_reports_no_revision(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert BaseAdapter._read_git_commit(plain) is None


def test_probe_carries_the_dirty_revision(repo: Path):
    (repo / "VERSION").write_text("0.88.0\n", encoding="utf-8")
    _git(repo, "add", "VERSION")
    _git(repo, "commit", "-qm", "version")
    clean = BaseAdapter().probe({"repository": str(repo)})
    (repo / "ladder_geom.py").write_text("HOLE_ALONG = 1.3\n", encoding="utf-8")
    dirty = BaseAdapter().probe({"repository": str(repo)})
    assert clean.tool_version == dirty.tool_version == "0.88.0"
    assert dirty.repository_commit != clean.repository_commit, (
        "the probe feeds the fingerprint; it must see the working tree")
