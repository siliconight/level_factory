"""Why a job ran again: its fingerprint receipts, read back.

THE RECEIPT IS THE WHOLE DECISION. The scheduler writes ``fingerprint.last.json`` beside every job it evaluates,
cache hit or not, and since 0.254.0 its ``fingerprint`` holds every component the cache digest hashes
(`BuildFingerprint.as_dict`). Before, it recorded the adapter's inputs and versions but not the executable
versions, the normalised arguments, the declared environment, the upstream hashes, the seed or the output contract
-- six of the digest's twelve components -- so a job could re-run with every recorded input identical and nothing on
disk saying why. The Level Factory panel's trial level did exactly that (the factory's
`docs/findings/rerun_receipts/`).

THE PREVIOUS RECEIPT IS KEPT as ``fingerprint.previous.json`` whenever the digest moves, so `differences` can name
what changed between the evaluation that built the cached output and the one that rebuilt it.
"""
from __future__ import annotations

import json
from pathlib import Path

LAST = "fingerprint.last.json"
PREVIOUS = "fingerprint.previous.json"


def read(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _flat(value, prefix: str, out: dict) -> dict:
    if isinstance(value, dict):
        for k, v in value.items():
            _flat(v, "%s/%s" % (prefix, k), out)
    else:
        out[prefix or "/"] = value
    return out


def differences(job_dir: Path) -> list[str] | None:
    """What moved in the digest between the previous receipt and the last: ``["/executable_versions/python: 3.14.0
    -> 3.13.9", ...]``, empty when they agree. ``None`` when either receipt is missing, unreadable, or written before
    receipts carried the whole fingerprint (0.254.0): then the question cannot be answered from disk."""
    prev, last = read(Path(job_dir) / PREVIOUS), read(Path(job_dir) / LAST)
    if not prev or not last or "fingerprint" not in prev or "fingerprint" not in last:
        return None
    a, b = _flat(prev["fingerprint"], "", {}), _flat(last["fingerprint"], "", {})
    return ["%s: %s -> %s" % (k, a.get(k, "(absent)"), b.get(k, "(absent)"))
            for k in sorted(set(a) | set(b)) if k != "/digest" and a.get(k) != b.get(k)]
