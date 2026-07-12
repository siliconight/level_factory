"""Rich visual comparisons (TDD 27.7 compare before/after, Phase 5).

Pairs a mission's presentation preview states (calm / alarm / extraction, TDD
24.7) against a previous set and emits a side-by-side comparison report. The
diff metric is intentionally dependency-free: image dimensions when readable
(PNG header), byte size, and content-hash equality. A real pixel-diff can drop
into ``_image_metrics`` later without changing the report shape.

Automatic visual diffing inside the desktop UI is deferred (TDD 41.3); this
produces a standalone HTML/JSON artifact instead.
"""
from __future__ import annotations

import datetime as _dt
import struct
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_file

PREVIEW_STATES = ("calm", "alarm", "extraction")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _png_size(path: Path) -> tuple[int, int] | None:
    """Read a PNG's (width, height) from its header, or None if not a PNG."""
    try:
        with path.open("rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", head[16:24])
    except (OSError, struct.error):
        return None


def _image_metrics(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"present": False}
    size = _png_size(path)
    return {
        "present": True,
        "bytes": path.stat().st_size,
        "hash": hash_file(path),
        "dimensions": list(size) if size else None,
    }


@dataclass
class StateComparison:
    state: str
    before: dict
    after: dict

    @property
    def changed(self) -> bool:
        return self.before.get("hash") != self.after.get("hash")

    @property
    def status(self) -> str:
        if not self.before.get("present") and self.after.get("present"):
            return "added"
        if self.before.get("present") and not self.after.get("present"):
            return "removed"
        return "changed" if self.changed else "unchanged"

    def as_dict(self) -> dict:
        return {"state": self.state, "status": self.status,
                "before": self.before, "after": self.after}


@dataclass
class VisualReview:
    mission_id: str
    comparisons: list[StateComparison] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.visual_review.v0.1",
            "created_at": self.created_at, "mission_id": self.mission_id,
            "comparisons": [c.as_dict() for c in self.comparisons],
            "changed_states": [c.state for c in self.comparisons if c.changed],
        }

    def to_html(self) -> str:
        rows = []
        for c in self.comparisons:
            b = c.before.get("hash", "-")[:12] if c.before.get("present") else "(none)"
            a = c.after.get("hash", "-")[:12] if c.after.get("present") else "(none)"
            rows.append(
                f"<tr><td>{c.state}</td><td>{c.status}</td>"
                f"<td><code>{b}</code></td><td><code>{a}</code></td></tr>")
        return (
            "<!doctype html><meta charset='utf-8'>"
            f"<title>Visual review — {self.mission_id}</title>"
            "<style>body{font-family:system-ui;margin:2rem}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.4rem .8rem}"
            ".changed{background:#fff3cd}</style>"
            f"<h1>Visual review — {self.mission_id}</h1>"
            "<table><tr><th>State</th><th>Status</th><th>Before</th><th>After</th></tr>"
            + "".join(rows) + "</table>")


def compare_presentation(
    mission_id: str, *, before_dir: Path | None, after_dir: Path,
    states=PREVIEW_STATES,
) -> VisualReview:
    review = VisualReview(mission_id=mission_id)
    for state in states:
        after = after_dir / f"preview_{state}.png"
        before = (before_dir / f"preview_{state}.png") if before_dir else None
        # Skip states neither side has.
        if not after.exists() and not (before and before.exists()):
            continue
        review.comparisons.append(StateComparison(
            state=state,
            before=_image_metrics(before if before and before.exists() else None),
            after=_image_metrics(after if after.exists() else None)))
    return review
