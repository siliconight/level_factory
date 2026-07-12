"""Main window: left navigation over the eight screens (TDD 27).

Holds the current mission selection centrally; the dashboard sets it, the
mission-scoped screens read it via a getter. Nothing here executes tools — it
only wires screens to the FactoryService.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QListWidget, QMainWindow, QSplitter, QStackedWidget, QStatusBar, QWidget,
)
from PySide6.QtCore import Qt

from apps.desktop.views.screens import (
    ArtPassScreen, CandidateGallery, Dashboard, HandoffScreen, JobConsole,
    PipelineView, SetupWizard, ValidationCenter,
)


class MainWindow(QMainWindow):
    def __init__(self, service) -> None:
        super().__init__()
        self.service = service
        self._current_mission: str | None = None
        self.setWindowTitle("Level Factory")
        self.setStatusBar(QStatusBar())

        getter = lambda: self._current_mission
        self.dashboard = Dashboard(service)
        self.setup = SetupWizard(service)
        self.pipeline = PipelineView(service, getter)
        self.gallery = CandidateGallery(service, getter)
        self.art = ArtPassScreen(service, getter)
        self.validation = ValidationCenter(service, getter)
        self.console = JobConsole(service, getter)
        self.handoff = HandoffScreen(service, getter)

        self._screens = [
            ("Dashboard", self.dashboard),
            ("Setup", self.setup),
            ("Pipeline", self.pipeline),
            ("Candidates", self.gallery),
            ("Art Pass", self.art),
            ("Validation", self.validation),
            ("Job Console", self.console),
            ("Handoff", self.handoff),
        ]

        self.nav = QListWidget()
        self.stack = QStackedWidget()
        for name, widget in self._screens:
            self.nav.addItem(name)
            self.stack.addWidget(widget)
            widget.status.connect(self._on_status)

        self.dashboard.mission_activated.connect(self._on_mission_selected)
        self.nav.currentRowChanged.connect(self._on_nav)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 5)
        container = QWidget()
        from PySide6.QtWidgets import QHBoxLayout
        layout = QHBoxLayout(container); layout.addWidget(splitter)
        self.setCentralWidget(container)
        self.nav.setCurrentRow(0)

    def _on_nav(self, row: int) -> None:
        if 0 <= row < len(self._screens):
            self.stack.setCurrentIndex(row)
            self._screens[row][1].refresh()

    def _on_mission_selected(self, mission_id: str) -> None:
        self._current_mission = mission_id
        self.statusBar().showMessage(f"Mission: {mission_id}")
        # Jump to the pipeline view for the chosen mission.
        self.nav.setCurrentRow(2)

    def _on_status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)
