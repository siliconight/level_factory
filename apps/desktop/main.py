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


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
