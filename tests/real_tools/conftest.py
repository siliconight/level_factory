"""Real-tool smoke fixtures (TDD 37.5).

Gated on the LF_TOOLS_DIR environment variable pointing at a directory that
contains the real Siliconight tool repos. When it's absent (normal CI / the
stub-only suite), every test here is skipped — the fast suite never depends on
Blender, Godot, or the private repos being present.

LF_TOOLS_DIR may point either at a dir of repos or their parent; each tool's
real root is resolved by locating its package/entry inside.
"""
import os
from pathlib import Path

import pytest

TOOLS_DIR = os.environ.get("LF_TOOLS_DIR")


def _find_root(base: Path, marker_rel: str) -> Path | None:
    """Find the deepest dir under base that contains marker_rel."""
    if (base / marker_rel).exists():
        return base
    for cand in base.rglob(marker_rel):
        # marker_rel may be nested; return its containing repo root.
        root = cand
        for _ in range(marker_rel.count("/") + 1):
            root = root.parent
        if (root / marker_rel).exists():
            return root
    return None


@pytest.fixture(scope="session")
def tools_base():
    if not TOOLS_DIR:
        pytest.skip("LF_TOOLS_DIR not set; real-tool smoke skipped")
    base = Path(TOOLS_DIR)
    if not base.exists():
        pytest.skip(f"LF_TOOLS_DIR does not exist: {base}")
    return base


@pytest.fixture(scope="session")
def tool_root(tools_base):
    def resolve(marker: str) -> Path:
        root = _find_root(tools_base, marker)
        if root is None:
            pytest.skip(f"tool with marker '{marker}' not found under {tools_base}")
        return root
    return resolve
