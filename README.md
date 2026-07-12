# Level Factory

Production/orchestration layer over the Siliconight level-building toolchain
(Deli Counter, Lot, Laser Tag, Pixelcoat, Zoo, Patina, Lux, Dispatch). It turns
mission briefs into reproducible, validated mission-shell handoffs. It does not
duplicate the tools; it orchestrates them (TDD 5.1, "orchestrate, do not
absorb").

**This package is Phases 1-3: the headless orchestration core, the presentation
pipeline and portable export, and the PySide6 desktop MVP.** It runs the
*functional* pipeline (Deli x N -> Lot -> Laser Tag) and the Dispatch
`shell-handoff` tail, plus the PS2 art pass (Pixelcoat -> Zoo -> Patina -> Lux),
from a CLI and a desktop app, with caching, provenance, human gates, resume, a
functional lock with post-art regression, portable `export` + a clean-project
`portability-test`, and an application-service layer the UI binds to (the UI
never runs tools itself). Batch production (Phase 4) and advanced review/CI
(Phase 5) come later.

The desktop app is an optional extra:

```
pip install -e '.[desktop]'
python -m apps.desktop <workspace-dir>
```

## Authority statement

Level Factory and Dispatch package *shell intent*. The production game remains
authoritative for gameplay, mission state, AI, replication, persistence,
reconnection, and online correctness. A passing structural score is never
labeled fun, balanced, multiplayer-verified, network-ready, or shipping-ready.

## Install / run

Pure standard library at runtime (Python 3.11+). No install required:

```
python apps/cli/main.py --help
```

Or install the console script:

```
pip install -e .
level-factory --help
```

## Quick start

```
# 1. create a workspace
python apps/cli/main.py init C:/Projects/delco-level-factory

# 2. point tools.local.json at your repos + Blender/Godot, then:
python apps/cli/main.py -C C:/Projects/delco-level-factory doctor

# 3. create a batch (see examples/delco_batch)
python apps/cli/main.py -C <ws> batch create examples/delco_batch/batch.json

# 4. plan and run the functional pipeline
python apps/cli/main.py -C <ws> plan bank_block_001 --target functional-lock
python apps/cli/main.py -C <ws> run  bank_block_001 --target functional-lock

# 5. approve the brief, walk the candidates, select one, then package
python apps/cli/main.py -C <ws> approve bank_block_001 brief_approved
python apps/cli/main.py -C <ws> approve bank_block_001 candidate_selected \
    --candidate bank_block_001.candidate.seed_1997
python apps/cli/main.py -C <ws> run bank_block_001 --target dispatch-handoff
```

> PowerShell note: keep each command on one line (no `\` continuations).

## Layout

- `packages/` — orchestration core (core, project_store, adapters SDK, jobs,
  artifacts/cache, pipeline, validation, approvals, tools/doctor).
- `adapters/` — concrete tool adapters (deli_counter, lot, laser_tag, dispatch).
- `apps/cli/` — the command-line interface.
- `schemas/` — canonical JSON schema descriptors.
- `examples/delco_batch/` — a runnable example batch + briefs.
- `tests/` — unit, adapter-contract, and stub-tool integration suites.

## Determinism & cache

Every job has a build fingerprint (adapter + tool versions, repo commit, a
digest of all declared inputs, seed, output-contract version). Identical
fingerprints reuse cached, content-addressed outputs. `run` after a crash skips
finished jobs; the SQLite index is a rebuildable accelerator, never the source
of truth.

## Testing

```
pip install pytest
python -m pytest
```

The integration suite uses stub tool CLIs under `tests/fixtures/`, so it runs
without Blender, Godot, or the real tool repos.
