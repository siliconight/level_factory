"""CI templates (TDD 42 Phase 5).

Generates a GitHub Actions workflow and a portable shell runner that drive the
headless pipeline as a gate: doctor -> batch run -> portability-test -> report.
Exit-code gating uses the CLI's documented codes (0 ok / 1 findings / 2 blocked /
3 config / 4 tool / 5 internal).
"""
from __future__ import annotations

GITHUB_WORKFLOW = """\
name: Level Factory
on:
  workflow_dispatch:
    inputs:
      batch_id:
        description: Batch id to build
        required: true
jobs:
  build-batch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: pip install -e .
      - name: Doctor
        run: level-factory -C "$WORKSPACE" doctor
        env:
          WORKSPACE: ${{ github.workspace }}/workspace
      - name: Build batch
        run: level-factory -C "$WORKSPACE" batch run "${{ inputs.batch_id }}" --target presentation
        env:
          WORKSPACE: ${{ github.workspace }}/workspace
      - name: Portability gate
        run: |
          set -e
          for m in $(level-factory -C "$WORKSPACE" batch report "${{ inputs.batch_id }}" --json | python -c "import sys,json;print(' '.join(json.load(sys.stdin)['handoff_ready_missions']))"); do
            level-factory -C "$WORKSPACE" export "$m" --mode portable-godot
            level-factory -C "$WORKSPACE" portability-test "$m" --mode portable-godot
          done
        env:
          WORKSPACE: ${{ github.workspace }}/workspace
      - name: Batch report
        run: level-factory -C "$WORKSPACE" batch report "${{ inputs.batch_id }}"
        env:
          WORKSPACE: ${{ github.workspace }}/workspace
      - uses: actions/upload-artifact@v4
        with:
          name: batch-reports
          path: workspace/batches/**/reports/**
"""

SHELL_RUNNER = """\
#!/usr/bin/env bash
# Portable CI runner for a Level Factory batch.
# Usage: ci/run.sh <workspace-dir> <batch-id>
set -euo pipefail
WS="${1:?workspace dir}"
BATCH="${2:?batch id}"
LF="level-factory -C $WS"

$LF doctor
$LF batch run "$BATCH" --target presentation
for m in $($LF batch report "$BATCH" --json \\
    | python -c "import sys,json;print(' '.join(json.load(sys.stdin)['handoff_ready_missions']))"); do
  $LF export "$m" --mode portable-godot
  $LF portability-test "$m" --mode portable-godot
done
$LF batch report "$BATCH"
"""


def render_templates() -> dict[str, str]:
    """Map of relative path -> file content."""
    return {
        ".github/workflows/level-factory.yml": GITHUB_WORKFLOW,
        "ci/run.sh": SHELL_RUNNER,
    }
