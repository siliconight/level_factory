# Changelog

All notable changes to Level Factory are documented here. Commit messages stay
short (< 200 chars); detail lives here.

## [0.1.0] - 2026-07-12

First package. Phase 1: Headless Orchestration Core (TDD 42, Phase 1).

### Added
- Workspace format and source-control-friendly layout (`factory.project.json`,
  `tools.local.json` / `tools.lock.json`, per-mission tree), rebuildable
  per-workspace SQLite index (`.level_factory/index.sqlite`).
- Canonical/deterministic JSON + SHA-256 hashing as the determinism foundation.
- Domain model (project, batch, brief, candidate, job, artifact, issue,
  approval) and mission/job state machines (TDD 12, 13, 14).
- Adapter SDK: `ToolProbe`, `PlannedCommand`, `ToolAdapter` protocol,
  `BaseAdapter`, and a `run_contract_probe` helper that reads a tool's
  machine-readable `contract` command (the Dispatch D12 pattern) instead of
  scraping prose.
- Tool registry + `doctor` (per-tool PASS/WARN/FAIL/NOT_CONFIGURED; a missing
  tool blocks only its own stages).
- Subprocess runner: argument-array execution (never `shell=True`), streamed
  per-attempt logs, process-tree termination on cancel/timeout, POSIX + Windows.
- Content-addressed cache keyed by build fingerprint (adapter+tool versions,
  commit, input digest, seed, output-contract version); immutable blobs,
  hard-link-or-copy materialization, `cache inspect` / `cache prune`.
- Provenance sidecars per artifact + final `build.lock.json` shape.
- DAG planner for the functional pipeline (deli x N -> lot -> laser_tag) plus
  the Dispatch shell-handoff tail (gated on a selected candidate), with
  deterministic seed derivation and a topological scheduler that resumes after
  a restart.
- Normalized validation model (severities/categories, aggregation) with a
  no-false-completion guarantee: a passing run is never labeled fun / balanced /
  multiplayer-verified / network-ready / shipping-ready.
- Approval gates and functional lock with fingerprint-based staleness.
- Adapters bound to current tool contracts: Deli Counter (v0.74.0 /
  gameplay 1.21.0), Lot (v0.17.x), Laser Tag (v0.7.x), Dispatch (v0.3.0 /
  `dispatch.mission.v0.2`, shell-handoff default). Dispatch adapter enforces the
  shell-only handoff (no production controller node, no leaked network ids).
- CLI: `init`, `doctor`, `batch create`, `plan`, `run`, `resume` (via re-run),
  `status`, `validate`, `approve`, `reject`, `cache`, `diagnostics`, with the
  TDD 28.1 exit-code scheme.
- Tests: unit (core, fingerprint/cache, planner/graph, approvals/validation,
  blocking gate), shared adapter contract suite, and a stub-tool end-to-end
  integration proving brief -> handoff, cache reuse, and resume.

### Deviations from TDD v0.2
- Adapters are bound against the documented tool contracts and exercised via
  stub CLIs; the private tool repos were not reachable at build time, so the
  real-tool smoke suite (TDD 37.5) is developer-only and unrun here.
- Phase 2 (presentation adapters: Pixelcoat/Zoo/Patina/Lux, regression) and
  Phase 3 (PySide6 desktop) are out of scope for this package.
- Pure standard library (no third-party runtime deps), matching the rest of the
  Siliconight tooling; `pytest` is a dev-only dependency.
