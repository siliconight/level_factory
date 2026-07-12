"""Level Factory desktop entry point (PySide6).

Usage:
    python -m apps.desktop [workspace_dir]

The desktop is a thin shell over FactoryService (TDD 9.1): it configures and
drives the same orchestration the CLI uses, but never runs tool processes
itself.
"""
from __future__ import annotations

import sys
from pathlib import Path


def build_window(service):
    """Construct the main window for a service (importable for offscreen tests)."""
    from apps.desktop.windows.main_window import MainWindow
    return MainWindow(service)


def self_check(root: Path) -> int:
    """Headless GUI sanity check: build the window offscreen, drive every
    screen, and print a summary. Used by the desktop test (run in a subprocess
    so Qt never loads into the pytest process) and handy as a smoke command."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from packages.service.facade import FactoryService

    app = QApplication.instance() or QApplication([])
    service = FactoryService.open(root)
    window = build_window(service)
    rows = service.dashboard()
    mission = rows[0].mission_id if rows else None
    if mission:
        window._on_mission_selected(mission)
    counts = {}
    for i, (name, screen) in enumerate(window._screens):
        window.nav.setCurrentRow(i)
    counts = {
        "dashboard": window.dashboard.model.rowCount(),
        "pipeline": window.pipeline.model.rowCount(),
        "candidates": window.gallery.model.rowCount(),
        "art": window.art.list.count(),
        "handoff": window.handoff.list.count(),
        "console": window.console.picker.count(),
    }
    print("SELFCHECK OK " + " ".join(f"{k}={v}" for k, v in counts.items()))
    app.quit()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--self-check":
        return self_check(Path(argv[1]) if len(argv) > 1 else Path.cwd())
    root = Path(argv[0]) if argv else Path.cwd()

    from PySide6.QtWidgets import QApplication
    from packages.service.facade import FactoryService

    service = FactoryService.open(root)
    app = QApplication.instance() or QApplication([])
    window = build_window(service)
    window.resize(1100, 720)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
