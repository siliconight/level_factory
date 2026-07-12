"""Workspace layout and paths (TDD 11).

A workspace is designed to live in source control. Human-authored JSON is
canonical; everything under ``.level_factory/`` is a rebuildable local index and
can be deleted safely.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.errors import WorkspaceError

GITIGNORE = """\
# Level Factory local state (rebuildable)
tools.local.json
.level_factory/
"""

DEFAULT_TOOLS_LOCK = {
    "schema": "level_factory.tools_lock.v0.1",
    "python": ">=3.11",
    "godot": "4.7",
    "tools": {
        "deli_counter": {"required_schema": "compatible", "commit": None},
        "lot": {"required_schema": "compatible", "commit": None},
        "laser_tag": {"required_schema": "compatible", "commit": None},
        "dispatch": {"required_contract": "dispatch.mission.v0.2"},
    },
}

DEFAULT_TOOLS_LOCAL = {
    "blender_executable": "",
    "godot_executable": "",
    "python_executable": "",
    "repositories": {
        "deli_counter": "",
        "lot": "",
        "laser_tag": "",
        "pixelcoat": "",
        "zoo": "",
        "patina": "",
        "lux": "",
        "dispatch": "",
    },
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class Workspace:
    root: Path

    # ---- canonical files -------------------------------------------------
    @property
    def project_file(self) -> Path:
        return self.root / "factory.project.json"

    @property
    def tools_local(self) -> Path:
        return self.root / "tools.local.json"

    @property
    def tools_lock(self) -> Path:
        return self.root / "tools.lock.json"

    @property
    def batches_dir(self) -> Path:
        return self.root / "batches"

    @property
    def shared_dir(self) -> Path:
        return self.root / "shared"

    # ---- local, rebuildable state ---------------------------------------
    @property
    def internal_dir(self) -> Path:
        return self.root / ".level_factory"

    @property
    def index_db(self) -> Path:
        return self.internal_dir / "index.sqlite"

    @property
    def jobs_dir(self) -> Path:
        return self.internal_dir / "jobs"

    @property
    def temp_dir(self) -> Path:
        return self.internal_dir / "temp"

    # ---- per-mission paths ----------------------------------------------
    def batch_dir(self, batch_id: str) -> Path:
        return self.batches_dir / batch_id

    def mission_dir(self, batch_id: str, mission_id: str) -> Path:
        return self.batch_dir(batch_id) / "missions" / mission_id

    def mission_subdir(self, batch_id: str, mission_id: str, name: str) -> Path:
        return self.mission_dir(batch_id, mission_id) / name

    # ---- io helpers ------------------------------------------------------
    def exists(self) -> bool:
        return self.project_file.exists()

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pretty_dumps(obj), encoding="utf-8")

    def load_project(self) -> dict:
        if not self.exists():
            raise WorkspaceError(f"no Level Factory workspace at {self.root}")
        return self.read_json(self.project_file)

    def load_tools_local(self) -> dict:
        if self.tools_local.exists():
            return self.read_json(self.tools_local)
        return dict(DEFAULT_TOOLS_LOCAL)

    def load_tools_lock(self) -> dict:
        if self.tools_lock.exists():
            return self.read_json(self.tools_lock)
        return dict(DEFAULT_TOOLS_LOCK)


def init_workspace(root: Path, *, project_id: str, name: str) -> Workspace:
    ws = Workspace(root=root.resolve())
    if ws.exists():
        raise WorkspaceError(f"workspace already initialized at {ws.root}")

    ws.root.mkdir(parents=True, exist_ok=True)
    ws.batches_dir.mkdir(exist_ok=True)
    ws.shared_dir.mkdir(exist_ok=True)
    for sub in ("pixelcoat", "zoo", "patina", "lux"):
        (ws.shared_dir / sub).mkdir(exist_ok=True)
    ws.internal_dir.mkdir(exist_ok=True)
    ws.jobs_dir.mkdir(exist_ok=True)
    ws.temp_dir.mkdir(exist_ok=True)

    project = {
        "schema": "level_factory.project.v0.1",
        "project_id": project_id,
        "name": name,
        "created_at": _now(),
        "defaults": {
            "candidate_count": 3,
            "preferred_players": 4,
            "target_minutes": [25, 35],
            "godot_version": "4.7",
        },
        "batches": [],
    }
    ws.write_json(ws.project_file, project)
    ws.write_json(ws.tools_lock, DEFAULT_TOOLS_LOCK)
    if not ws.tools_local.exists():
        ws.write_json(ws.tools_local, DEFAULT_TOOLS_LOCAL)
    (ws.root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    return ws


def find_workspace(start: Path) -> Workspace:
    """Walk upward from ``start`` looking for a factory.project.json."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / "factory.project.json").exists():
            return Workspace(root=candidate)
    raise WorkspaceError(f"no Level Factory workspace found at or above {start}")
