"""pure-shell keeps the graybox site once a mission gains a handoff.

Written after 0.37.0's entry guard fired on pure-shell. `base_dir` chose the
Dispatch handoff OR the graybox, and Dispatch's handoff carries no
`site.tscn` -- so a mission that grew a `dispatch_handoff` silently stopped
shipping the only scene a pure-shell package had to instance.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.export import (  # noqa: E402
    MODE_PURE_SHELL, ExportProfile, export_mission,
)
from packages.exporting.localize import ExportContentError  # noqa: E402


def _mission(root, *, with_handoff=True):
    """A graybox with a site, and a Dispatch handoff that has none.

    Shaped from the real lot_demo_001: `dispatch_handoff/out` holds
    mission.tscn and the gameplay JSON, and no site.tscn at all.
    """
    graybox = root / "graybox"
    graybox.mkdir(parents=True)
    (graybox / "site.tscn").write_text("[gd_scene]\n")
    (graybox / "site_base.glb").write_bytes(b"glTF")

    handoff = None
    if with_handoff:
        handoff = root / "handoff"
        handoff.mkdir(parents=True)
        (handoff / "mission_manifest.json").write_text("{}")
        (handoff / "gameplay_anchors.json").write_text("{}")
        # Dispatch's own entry, which the export replaces with its stub.
        (handoff / "mission.tscn").write_text("[gd_scene] dispatch\n")
    return graybox, handoff


def _export(root, *, with_handoff=True):
    graybox, handoff = _mission(root, with_handoff=with_handoff)
    return export_mission(
        mission_id="m1", out_root=root / "exports",
        profile=ExportProfile(mode=MODE_PURE_SHELL),
        handoff_dir=handoff, presentation_dir=None, composed_root=None,
        themed_site_dir=None, graybox_dir=graybox,
        source_dir=None, tool_versions={}, layers=frozenset(),
    )


def test_pure_shell_without_a_handoff_still_works(tmp_path):
    """The path that never broke: graybox IS the base."""
    result = _export(tmp_path, with_handoff=False)
    assert (result.export_dir / "site.tscn").is_file()


def test_pure_shell_with_a_handoff_keeps_the_graybox_site(tmp_path):
    """THE REGRESSION. The handoff used to REPLACE the graybox."""
    result = _export(tmp_path)
    assert (result.export_dir / "site.tscn").is_file()


def test_the_handoff_content_still_lands(tmp_path):
    """A base, not a substitution -- both are in the package."""
    result = _export(tmp_path)
    names = {p.name for p in result.export_dir.rglob("*") if p.is_file()}
    assert "gameplay_anchors.json" in names
    assert "site_base.glb" in names


def test_the_entry_instances_the_graybox_site(tmp_path):
    result = _export(tmp_path)
    body = (result.export_dir / "mission.tscn").read_text()
    assert "res://site.tscn" in body
    assert "add_child" in body


def test_a_pure_shell_export_with_no_graybox_at_all_refuses(tmp_path):
    """The guard still guards. Nothing to instance is still an error."""
    handoff = tmp_path / "h"
    handoff.mkdir()
    (handoff / "mission_manifest.json").write_text("{}")
    with pytest.raises(ExportContentError):
        export_mission(
            mission_id="m1", out_root=tmp_path / "exports",
            profile=ExportProfile(mode=MODE_PURE_SHELL),
            handoff_dir=handoff, presentation_dir=None, composed_root=None,
            themed_site_dir=None, graybox_dir=None,
            source_dir=None, tool_versions={}, layers=frozenset(),
        )
