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
#: The pin matches the VERSION file, and the VERSION file is older than the
#: code it names. Sits below DRIFT because the numbers still agree -- what has
#: gone stale is the claim that the number means anything.
STALE = "STALE"
#: The CHANGELOG documents versions the tool never claimed to be -- entries
#: exist above what VERSION says. `lot` carried nine of them, 0.33.0 through
#: 0.41.0, against a VERSION file reading 0.33.0. The record is right; VERSION
#: should follow it.
UNRELEASED = "UNRELEASED"
#: A release with no entry -- VERSION is ahead of the newest heading. `zoo`
#: shipped 0.32.0 while its CHANGELOG still stopped at 0.31.0. The version is
#: right; the record owes an entry.
UNDOCUMENTED = "UNDOCUMENTED"
#: Both outrank DRIFT. A pin being behind has an obvious fix; a tool that does
#: not know its own version cannot be pinned at all, so it has to be the
#: louder finding. `lot` was DRIFT and STALE and neither said the useful
#: thing.
_SEVERITY = {OK: 0, UNKNOWN: 1, STALE: 2, DRIFT: 3, UNDOCUMENTED: 4,
             UNRELEASED: 4, INCOMPATIBLE: 5}


LOCK_FILENAME = "tools.lock.json"
LOCK_SCHEMA = "level_factory.tools_lock.v0.1"

# The versions the current LF release's adapters were grounded against. `version`
# is the semver the tool actually reports at runtime; `source` documents where it
# comes from (some tools disagree between packaging metadata and runtime); a
# `contract` string is recorded where the tool publishes a machine-readable one.
GROUNDED: dict[str, dict] = {
    "deli_counter": {"version": "0.75.0", "source": "VERSION"},
    "lot":          {"version": "0.18.3", "source": "VERSION"},
    "laser_tag":    {"version": "0.8.0",  "source": "VERSION",
                     "note": "was unpinned until 0.8.0 -- the addon declared a "
                             "version in addons/laser_tag_tool/plugin.cfg but "
                             "the repo had no root VERSION file, which is the "
                             "only place installed_factory_versions looks. The "
                             "two are mirrors and the repo's lint job fails if "
                             "they disagree"},
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
    #: For STALE: the newest source file that outran VERSION. Naming it is the
    #: difference between a verdict and a place to look.
    stale_because: str | None = None
    #: The version in the newest CHANGELOG heading. None when the tool has no
    #: CHANGELOG, which is not a finding -- see `newest_changelog_entry`.
    documented: str | None = None

    def as_dict(self) -> dict:
        return {
            "adapter": self.adapter_id, "certified": self.certified,
            "installed": self.installed, "status": self.status,
            "certified_from": self.source,
            "stale_because": self.stale_because,
            "documented": self.documented,
        }

    @property
    def message(self) -> str:
        if self.status == OK:
            return f"{self.installed} matches certified {self.certified}"
        if self.status == STALE:
            return (f"{self.installed} matches certified {self.certified}, but "
                    f"VERSION is older than the code it names"
                    + (f" ({self.stale_because})" if self.stale_because else "")
                    + " -- bump the tool version, then re-certify")
        if self.status == UNRELEASED:
            return (f"the CHANGELOG documents {self.documented} but VERSION "
                    f"says {self.installed} -- the record is ahead of the "
                    f"version; bump VERSION to follow it, then re-pin")
        if self.status == UNDOCUMENTED:
            return (f"VERSION says {self.installed} but the newest CHANGELOG "
                    f"entry is {self.documented} -- this release has no "
                    f"entry; write one")
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
        from pathlib import Path as _P
        tool_dir = _P(str(factory_root)) / str(
            manifest["tools"][name].get("path", name))
        status = compare(pinned, installed.get(name))
        because = None
        documented = newest_changelog_entry(tool_dir)

        # THE THIRD NUMBER IS CHECKED FIRST, AND NOT ONLY FROM OK -- which
        # is the opposite of how STALE is reached, on purpose. STALE
        # escalates only from OK because if the numbers already disagree,
        # DRIFT's message is more useful. That does not survive `lot`: it
        # was DRIFT (pin 0.32.0, VERSION 0.33.0), and DRIFT says "re-run the
        # smoke and re-certify" -- which would have pinned 0.33.0, wrong by
        # eight releases, while its CHANGELOG said 0.41.0. A tool that does
        # not know its own version cannot be pinned, so that has to outrank
        # the pin being behind.
        disagreement = self_disagreement(installed.get(name), documented)
        if disagreement:
            status = disagreement
        elif status == OK:
            because = stale_source(tool_dir)
            if because:
                status = STALE
        results.append(ContractResult(
            adapter_id=name,
            certified=pinned,
            installed=installed.get(name),
            status=status,
            source="factory.manifest",
            stale_because=because,
            documented=documented,
        ))
    return results


def newest_changelog_entry(tool_dir) -> str | None:
    """The version in the newest CHANGELOG heading, or None.

    BOTH SHAPES IN USE HERE ARE ACCEPTED. `patina` writes `## [0.19.0] -
    2026-08-02`, `dispatch` writes `## v0.3.0 - 2026-07-11`, `pipeline`
    writes `## [v0.1.0] - 2026-07-17`. A reader that took only the bracketed
    form reported `dispatch` -- a tool in perfect agreement with itself -- as
    disagreeing. An instrument that misreads the record is the failure this
    module exists to catch.

    NEWEST MEANS FIRST, NOT HIGHEST. These files are written newest-first and
    the top entry is the claim being made. Taking the maximum instead would
    have hidden `zoo`, whose stray entry sat ABOVE the document title with a
    number already used further down.

    ``None`` when there is no CHANGELOG or no heading in it. That is not a
    finding: `laser_tag` is an addon directory holding VERSION and addons/,
    and may never want one. A missing file means no opinion, the same way a
    missing version degrades to UNKNOWN rather than to a false OK.
    """
    from pathlib import Path as _P
    p = _P(str(tool_dir)) / "CHANGELOG.md"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^##\s*\[?v?(\d+\.\d+\.\d+)\]?", text, re.M)
    return m.group(1) if m else None


def self_disagreement(installed: str | None,
                      documented: str | None) -> str | None:
    """UNRELEASED, UNDOCUMENTED, or None -- does the tool agree with itself?

    Compares the two numbers the TOOL owns. The manifest pin is not involved:
    a tool that does not know its own version cannot be pinned correctly by
    anyone, so this is answerable without asking what was certified.
    """
    i, d = parse_semver(installed), parse_semver(documented)
    if i is None or d is None or i == d:
        return None
    return UNDOCUMENTED if i > d else UNRELEASED


def stale_source(tool_dir) -> str | None:
    """Name a source file whose last commit is newer than VERSION's.

    ASKS GIT, NOT THE FILESYSTEM. The first version of this compared mtimes
    and reported six of ten tools stale, every one of them naming
    `.gitignore` -- a file that is repo configuration, not code. Excluding
    `.gitignore` would only have moved the problem to the next non-source
    file, because an exclusion list always trails whatever gets added next.
    `docs/CLEANUP.md` already settled this argument for artifact sweeping:
    allow-list, never guess. History is the allow-list that cannot fall
    behind -- it knows exactly which commit touched what.

    ``None`` when the answer is not knowable: no git, not a repo, no commit
    touching VERSION, or a shallow clone. An unknowable answer is reported as
    OK rather than as a warning nobody can act on.

    Robust to fresh clones, which is what killed the mtime version: cloning
    rewrites every mtime but not a single commit date.
    """
    import subprocess
    from pathlib import Path as _P
    root = _P(str(tool_dir))
    if not (root / ".git").exists():
        return None

    #: Files whose change is not a code change. VERSION and CHANGELOG move as
    #: part of the bump itself; the rest is repo furniture.
    skip = ["VERSION", "CHANGELOG.md", ".gitignore", ".gitattributes",
            ".editorconfig", "LICENSE", "LICENSE.md"]

    def _git(args):
        try:
            r = subprocess.run(["git", "-C", str(root)] + args,
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    when_version = _git(["log", "-1", "--format=%ct", "--", "VERSION"])
    if not (when_version or "").isdigit():
        return None

    pathspec = ["."] + [f":(exclude){s}" for s in skip]
    when_source = _git(["log", "-1", "--format=%ct", "--"] + pathspec)
    if not (when_source or "").isdigit():
        return None
    if int(when_source) <= int(when_version):
        return None

    sha = _git(["log", "-1", "--format=%H", "--"] + pathspec)
    if not sha:
        return "a commit newer than VERSION"
    names = (_git(["show", "--name-only", "--format=", sha]) or "").split()
    names = [n for n in names if n not in skip]
    if not names:
        return "a commit newer than VERSION"
    head = names[0]
    return head if len(names) == 1 else f"{head} +{len(names) - 1} more"
