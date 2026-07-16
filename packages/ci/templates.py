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
  push:
  pull_request:
  workflow_dispatch:
    inputs:
      batch_id:
        description: Batch id to build
        required: true
jobs:
  contract-guard:
    # Fails a tool-pin bump loudly instead of letting drift surface as a broken
    # output later. Set LF_TOOLS_DIR (e.g. check the tool repos out) to also run
    # the real-tool smoke; without it, the smoke self-skips.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: pip install -e . && pip install pytest
      - name: Fast suite (stub tools)
        run: python -m pytest -q
      - name: Verify tool contracts (strict)
        run: level-factory -C "$WORKSPACE" verify-contracts   # add --strict to also flag unpinned tools
        env:
          WORKSPACE: ${{ github.workspace }}/workspace
      - name: Real-tool smoke (runs only when LF_TOOLS_DIR is set)
        run: |
          if [ -n "${LF_TOOLS_DIR:-}" ]; then
            python -m pytest tests/real_tools -q
          else
            echo "LF_TOOLS_DIR not set; skipping real-tool smoke"
          fi
  build-batch:
    if: github.event_name == 'workflow_dispatch'
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
$LF verify-contracts   # add --strict to also flag version-less tools
if [ -n "${LF_TOOLS_DIR:-}" ]; then python -m pytest tests/real_tools -q; fi
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
