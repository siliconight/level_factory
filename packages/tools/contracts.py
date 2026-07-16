"""Tool-contract verification (integration-drift guard).

Level Factory orchestrates eight independently-versioned tool repos. When one is
updated, its CLI or output contract can drift out from under the adapter that was
grounded against it. This module is the compatibility matrix + the comparison
logic that turns silent drift into a loud, actionable signal.

Three layers work together:
  1. GROUNDED (here) — the version each adapter was certified against when the
     current LF release was grounded (see REAL_TOOL_RECONCILIATION + the
     tests/real_tools smoke). Ships with LF.
  2. A per-workspace lockfile (tools.lock.json) — a human assertion "I re-ran the
     real-tool smoke against these versions and they pass." Overrides GROUNDED
     for the tools it lists.
  3. `verify-contracts` / `doctor` — probe the installed tools and compare their
     version to the certified one (lock, else GROUNDED), reporting OK / DRIFT /
     INCOMPATIBLE / UNKNOWN.

Tool version strings are heterogeneous ("Deli Counter 0.74.2", "0.27.0", a
runtime-only value, or absent), so comparison is on the extracted semver, and a
missing version degrades to UNKNOWN rather than a false OK.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Status values, ordered by severity for aggregation.
OK = "OK"
DRIFT = "DRIFT"            # same major, different minor/patch — re-certify
INCOMPATIBLE = "INCOMPATIBLE"  # different major — adapter likely broken
UNKNOWN = "UNKNOWN"        # no version to compare (unpinned tool / no source)
_SEVERITY = {OK: 0, UNKNOWN: 1, DRIFT: 2, INCOMPATIBLE: 3}

LOCK_FILENAME = "tools.lock.json"
LOCK_SCHEMA = "level_factory.tools_lock.v0.1"

# The versions the current LF release's adapters were grounded against. `version`
# is the semver the tool actually reports at runtime; `source` documents where it
# comes from (some tools disagree between packaging metadata and runtime); a
# `contract` string is recorded where the tool publishes a machine-readable one.
GROUNDED: dict[str, dict] = {
    "deli_counter": {"version": "0.75.0", "source": "VERSION"},
    "lot":          {"version": "0.18.3", "source": "VERSION"},
    "laser_tag":    {"version": None,     "source": None,
                     "note": "Godot addon exposes no version string; unpinned"},
    "pixelcoat":    {"version": "0.9.0",  "source": "version.py",
                     "note": "re-grounded 0.2.0->0.9.0; CLI/output contract "
                             "(pixelcoat-pack/1) verified unchanged by the smoke"},
    "zoo":          {"version": "0.30.2", "source": "VERSION"},
    "patina":       {"version": "0.18.0", "source": "CLI banner",
                     "note": "pyproject reports 0.1.1; runtime/CLI is authoritative"},
    "lux":          {"version": "0.15.4", "source": "VERSION"},
    "dispatch":     {"version": "0.3.0",  "source": "contract probe",
                     "contract": "dispatch.mission.v0.2"},
}

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_semver(raw: str | None) -> tuple[int, int, int] | None:
    """Extract (major, minor, patch) from any version string, or None."""
    if not raw:
        return None
    m = _SEMVER.search(str(raw))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def compare(certified: str | None, installed: str | None) -> str:
    """Compare a certified version against an installed one -> status."""
    c, i = parse_semver(certified), parse_semver(installed)
    if c is None or i is None:
        return UNKNOWN
    if c == i:
        return OK
    if c[0] != i[0]:
        return INCOMPATIBLE
    return DRIFT


@dataclass
class ContractResult:
    adapter_id: str
    certified: str | None
    installed: str | None
    status: str
    source: str  # "lock" or "grounded"

    def as_dict(self) -> dict:
        return {
            "adapter": self.adapter_id, "certified": self.certified,
            "installed": self.installed, "status": self.status,
            "certified_from": self.source,
        }

    @property
    def message(self) -> str:
        if self.status == OK:
            return f"{self.installed} matches certified {self.certified}"
        if self.status == DRIFT:
            return (f"installed {self.installed} != certified {self.certified} "
                    f"(same major) — re-run the real-tool smoke and re-certify")
        if self.status == INCOMPATIBLE:
            return (f"installed {self.installed} is a major bump over certified "
                    f"{self.certified} — the adapter is likely broken; re-ground it")
        return (f"no comparable version (certified={self.certified}, "
                f"installed={self.installed}) — cannot verify this tool")


def certified_version(adapter_id: str, lock_tools: dict) -> tuple[str | None, str]:
    """The version to hold a tool to: the lock's ``certified_version`` if set,
    else GROUNDED. Returns (version, source-label). ``lock_tools`` is the nested
    ``tools`` section of tools.lock.json ({adapter: {certified_version: ...}})."""
    entry = lock_tools.get(adapter_id, {}) if isinstance(lock_tools, dict) else {}
    if isinstance(entry, dict) and entry.get("certified_version"):
        return entry["certified_version"], "lock"
    return GROUNDED.get(adapter_id, {}).get("version"), "grounded"


def verify(installed_versions: dict[str, str | None],
           lock_tools: dict | None = None) -> list[ContractResult]:
    """Compare installed tool versions against certified ones.

    `installed_versions` maps adapter_id -> the version string the probe read
    (or None). `lock_tools` is the nested ``tools`` section of the lock. Only
    adapters present in GROUNDED are checked.
    """
    lock_tools = lock_tools or {}
    results: list[ContractResult] = []
    for adapter_id in sorted(GROUNDED):
        certified, source = certified_version(adapter_id, lock_tools)
        installed = installed_versions.get(adapter_id)
        results.append(ContractResult(
            adapter_id=adapter_id, certified=certified, installed=installed,
            status=compare(certified, installed), source=source,
        ))
    return results


def worst_status(results: list[ContractResult]) -> str:
    return max((r.status for r in results), key=lambda s: _SEVERITY.get(s, 0), default=OK)


def certify(full_lock: dict, installed_versions: dict[str, str | None]) -> dict:
    """Return an updated full lock dict recording the currently-installed
    versions as ``certified_version`` on each tool entry, preserving every other
    field. The caller asserts these have passed the real-tool smoke."""
    lock = dict(full_lock) if full_lock else {"schema": LOCK_SCHEMA}
    tools = dict(lock.get("tools", {}))
    for adapter_id in GROUNDED:
        installed = installed_versions.get(adapter_id)
        if not installed:
            continue
        entry = dict(tools.get(adapter_id, {}))
        entry["certified_version"] = installed
        tools[adapter_id] = entry
    lock["tools"] = tools
    return lock


# ---------------------------------------------------------------------------
# Factory manifest (two-layer versioning): the gabagool_factory checkout is
# itself versioned as a certified SET of tool versions. Tools stay standalone
# repos with their own semver; the factory manifest pins the combination that
# was verified together. The manifest is DATA and lives at the factory root
# (factory.manifest.json); the checking CODE lives here, in a tool — per the
# standing rule that code never lands at the factory level.

FACTORY_MANIFEST = "factory.manifest.json"


def strip_version_prefix(raw: str | None) -> str | None:
    """VERSION files carry display prefixes ("Lux 0.15.2", "Deli Counter
    0.75.0"); the comparable version is the last whitespace token."""
    if not raw:
        return None
    return str(raw).strip().split()[-1] if str(raw).strip() else None


def read_factory_manifest(factory_root) -> dict:
    import json
    from pathlib import Path
    p = Path(str(factory_root)) / FACTORY_MANIFEST
    if not p.exists():
        raise FileNotFoundError(f"no {FACTORY_MANIFEST} at {factory_root}")
    return json.loads(p.read_text(encoding="utf-8"))


def installed_factory_versions(factory_root, manifest: dict) -> dict:
    """Read each manifest tool's VERSION file relative to the factory root."""
    from pathlib import Path
    root = Path(str(factory_root))
    out: dict[str, str | None] = {}
    for name, entry in manifest.get("tools", {}).items():
        vf = root / str(entry.get("path", name)) / "VERSION"
        try:
            out[name] = strip_version_prefix(vf.read_text(encoding="utf-8"))
        except OSError:
            out[name] = None
    return out


def verify_manifest(factory_root) -> list:
    """Lockstep check: every tool's installed VERSION vs the factory
    manifest's pin. Reuses the OK/DRIFT/INCOMPATIBLE/UNKNOWN semantics."""
    manifest = read_factory_manifest(factory_root)
    installed = installed_factory_versions(factory_root, manifest)
    results: list[ContractResult] = []
    for name in sorted(manifest.get("tools", {})):
        pinned = strip_version_prefix(
            str(manifest["tools"][name].get("version", "")))
        if str(manifest["tools"][name].get("version", "")) == "unpinned":
            pinned = None
        results.append(ContractResult(
            adapter_id=name,
            certified=pinned,
            installed=installed.get(name),
            status=compare(pinned, installed.get(name)),
            source="factory.manifest",
        ))
    return results
