# Level Factory

Production/orchestration layer over the Siliconight level-building toolchain
(Deli Counter, Lot, Laser Tag, Pixelcoat, Zoo, Patina, Lux, Dispatch). It turns
mission briefs into reproducible, validated mission-shell handoffs. It does not
duplicate the tools; it orchestrates them (TDD 5.1, "orchestrate, do not
absorb").

**This package implements the full TDD delivery plan (Phases 1-5), grounded
against the real tool CLIs.** From a CLI and a PySide6 desktop app it produces a
**Graybox** base and two independent, optional layers — **Art** and **Gameplay** —
in any combination (see *Output layers* below). It runs the candidate pipeline
(Deli Counter x N -> Lot -> Laser Tag), the PS2 art pass (Pixelcoat -> Zoo ->
Patina -> Lux), and the Dispatch `shell-handoff`, with a parallel scheduler
(per-resource-class caps), caching, provenance, human gates, resume, a functional
lock with post-art regression, layer-aware portable `export` + a clean-project
`portability-test`, an application-service layer the UI binds to, cross-mission
batch runs with shared assets built once and batch reports, and the advanced-
review layer: team approvals with quorum, accepted exceptions with stale
detection, visual before/after comparison reports, CI templates, and a
source-control release helper.

## Output layers

The deliverable is a **Graybox** base plus optional layers, chosen per run. The
layers are independent — the models stay a shell the gameplay team fills.

```
run <mission>                  → graybox            DC greybox + collision, assembled by Lot (+ Laser Tag nav QA)
run <mission> --art            → graybox + art      Zoo swaps + props/dressing, Pixelcoat, Patina, Lux
run <mission> --gameplay       → graybox + gameplay Dispatch objective/nav/spawn suggestions (advisory)
run <mission> --art --gameplay → full stack         art pass + Dispatch over the art scene
```

- **Graybox** is always the base. Deli Counter builds the greybox building *with*
  functional collision on its own and emits per-piece swap slots; Lot assembles
  buildings into a walkable site with nav. No Zoo needed here.
- **Art** is the swap/decoration pass over the locked greybox: Zoo fills DC's slots
  with themed modules *at the same transform* (and adds non-collision props +
  dressing), Pixelcoat skins, Patina cohesion, Lux the runtime look. It never
  creates collision — swaps match or inherit DC's (`docs/ASSET_SWAP_CONTRACT.md`).
- **Gameplay** is Dispatch's advisory objective layer (spawns, objectives, nav
  hints, beat graph, ownership), built on the art scene when `--art` is on, else
  on the graybox directly.

`--art`/`--gameplay` are independent flags; bare `run` is graybox. The legacy
`--target` still works as an alias (`functional-lock` = graybox, `dispatch-handoff`
= +gameplay, `presentation` = +art+gameplay); `--art`/`--gameplay` take precedence.

Run a whole batch as one parallel DAG, then review, gate, and release it:

```
level-factory batch run <batch-id> --art --gameplay   # or bare for graybox; --target still works
level-factory review <mission-id>
level-factory team-sign <mission-id> handoff_approved --by <you>
level-factory batch report <batch-id>
level-factory ci-init
level-factory release <batch-id> --tag <tag>   # local tag; you push it
```

### Deferred by design (TDD 41.3)

Cloud/distributed workers (the worker seam ships; the network transport does
not), an embedded 3D viewport, multi-user web review, and PR automation are out
of scope for this build.

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

# 4. plan and run the graybox base
python apps/cli/main.py -C <ws> plan bank_block_001            # output=graybox
python apps/cli/main.py -C <ws> run  bank_block_001            # graybox base

# 5. approve the brief, walk the candidates, select one, then add layers
python apps/cli/main.py -C <ws> approve bank_block_001 brief_approved
python apps/cli/main.py -C <ws> approve bank_block_001 candidate_selected \
    --candidate bank_block_001.candidate.seed_1997
python apps/cli/main.py -C <ws> approve bank_block_001 functional_shell_locked
python apps/cli/main.py -C <ws> run bank_block_001 --art --gameplay   # add layers
python apps/cli/main.py -C <ws> export bank_block_001 --mode portable-godot
```

> PowerShell note: keep each command on one line (no `\` continuations).

## Layout

- `packages/` — orchestration core (core, project_store, adapters SDK, jobs,
  artifacts/cache, pipeline, validation, approvals, tools/doctor).
- `adapters/` — concrete tool adapters, each bound to its real CLI: deli_counter,
  lot, laser_tag, pixelcoat, zoo, patina, lux, dispatch.
- `packages/staging/` — input staging (e.g. DC/Lot -> Dispatch mission inputs).
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

A separate **real-tool smoke** drives the actual tool repos and is skipped unless
`LF_TOOLS_DIR` points at them (each adapter shares one code path across the stub
and real runs):

```
LF_TOOLS_DIR=/path/to/tools python -m pytest tests/real_tools -q
```
