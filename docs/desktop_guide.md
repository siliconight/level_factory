# Desktop Guide (Phase 3)

The desktop app is a thin PySide6 shell over `FactoryService`. It drives the
same orchestration the CLI does; per TDD 9.1 it calls application services and
never executes tool processes itself.

## Install & launch

```
pip install -e '.[desktop]'
python -m apps.desktop <workspace-dir>     # or the level-factory-desktop script
```

The core, CLI, and service layer never import Qt, so a headless machine can run
everything except the desktop window.

## Screens (TDD 27)

- **Setup** — edit Godot/Blender/Python paths, save `tools.local.json`, run
  `doctor`.
- **Dashboard** — one row per mission with state, running job, latest validation
  summary, approved gates, selected candidate, presentation status, and handoff
  status. Filter by blocked / waiting-for-approval / handoff-ready. Double-click
  a mission to open its pipeline.
- **Pipeline** — the mission DAG with per-node state; select a node to see its
  command, fingerprint, outputs, dependents, and log tail.
- **Candidates** — compare candidates by metrics and validation; select one
  (metrics compare, they never auto-select).
- **Art Pass** — the five presentation sections and their progress; run the
  presentation pipeline.
- **Validation** — the unified normalized issue list, filterable by severity.
- **Job Console** — command, resource class, elapsed time, work folder, and log
  tail for any job.
- **Handoff** — the readiness table (functional geometry / collision / anchors /
  shell IDs / beat graph / ownership / nav / presentation, plus the
  Not-Implemented-by-Design rows), export-mode selection, folder/ZIP export, and
  the portability test. Export is blocked here too if a functional regression is
  detected after the art pass.

## Architecture

`apps/desktop/` holds only view code (`views/`, `windows/`, `models/`). All
logic and state live in `packages/service/facade.py`, which is fully covered by
headless tests. The Qt views are declarative bindings over the service's
view-model dataclasses; the generic `DataclassTableModel` is the single seam
where Qt reads service data.
