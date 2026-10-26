"""Where a level stands, read back when it is opened (the factory's roadmap 318: save and reopen).

Every step the panel runs leaves a record beside the design -- the layouts' build record, the choice in the
workspace's approvals, the walk and export records -- and the worker reads them for its next step. Opening a level
reads the same records so the panel can show them: the newest layouts with their plans and which one is chosen, the
last walk and the last export. Each says whether it is of the design as it stands now, because a level reopened after
a change must not show the old walk as this revision's.

Nothing here builds or decides: a missing record is ``None``, and a record that cannot be read is reported, not
skipped.
"""
from __future__ import annotations

import json
from pathlib import Path

from packages.service import design as design_mod


def _newest(folder: Path, suffix: str) -> tuple[int, Path] | None:
    """The highest-revision ``builds/revision_<n><suffix>``, or None."""
    best = None
    for p in (folder / "builds").glob("revision_*%s" % suffix):
        middle = p.name[len("revision_"):-len(suffix)]
        if middle.isdigit() and (best is None or int(middle) > best[0]):
            best = (int(middle), p)
    return best


def _read(path: Path, problems: list) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append("%s cannot be read: %s" % (path.name, exc))
        return None
    if not isinstance(data, dict):
        problems.append("%s is not a record" % path.name)
        return None
    return data


def standing(folder: Path, doc: dict) -> dict:
    """``{"layouts", "layouts_stale", "chosen", "walk", "export", "problems"}`` for the design ``doc`` saved in
    ``folder``. ``layouts`` is the newest build record's answer as `generate_layouts` gave it; ``layouts_stale`` names
    the controls that rebuild the layout and changed since; ``walk`` and ``export`` are the newest records, each with
    ``current`` true only when it is of this revision."""
    folder = Path(folder)
    problems: list[str] = []
    out = {"layouts": None, "layouts_stale": [], "chosen": None, "walk": None, "export": None,
           "problems": problems}
    built = _newest(folder, ".json")
    if built is not None:
        record = _read(built[1], problems)
        if record is not None:
            out["layouts"] = {k: record.get(k) for k in ("candidates", "recommended", "every_out", "recommendation",
                                                         "plan_key")}
            out["layouts"]["design_revision"] = record.get("design_revision")
            now = design_mod.brief_from_design(doc)
            brief = record.get("brief") or {}
            out["layouts_stale"] = [c["label"] for c in design_mod.capabilities(doc["template"])
                                    if c.get("rebuilds") == "layout" and brief.get(c["key"]) != now.get(c["key"])]
    marker = folder / "workspace" / ".level_factory" / "approvals" / ("%s.selected" % design_mod.mission_id(doc))
    try:
        out["chosen"] = marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    for key, suffix in (("walk", ".walk.json"), ("export", ".export.json")):
        found = _newest(folder, suffix)
        if found is not None:
            record = _read(found[1], problems)
            if record is not None:
                out[key] = dict(record, current=found[0] == doc["revision"])
    # a snapshot is the designer's to move or delete: say when the folder the record names is gone
    if out["export"] is not None:
        snap = out["export"].get("snapshot")
        out["export"]["snapshot_present"] = bool(snap) and Path(str(snap)).is_dir()
    return out
