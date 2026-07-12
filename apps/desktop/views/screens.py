"""The eight desktop screens (TDD 27).

Each screen is a thin QWidget bound to one or more FactoryService methods. No
screen executes tool processes; they only call services and render results
(TDD 9.1). A `refresh()` method reloads from the service so the window can drive
updates centrally.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QPlainTextEdit, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from apps.desktop.models.table_models import DataclassTableModel


class _Screen(QWidget):
    status = Signal(str)

    def __init__(self, service, mission_getter=None) -> None:
        super().__init__()
        self.service = service
        self._mission_getter = mission_getter or (lambda: None)

    @property
    def mission_id(self):
        return self._mission_getter()

    def refresh(self) -> None:  # overridden per screen
        pass

    def _table(self) -> tuple[QTableView, DataclassTableModel]:
        view = QTableView()
        model = DataclassTableModel([])
        view.setModel(model)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        view.setSelectionBehavior(QTableView.SelectRows)
        return view, model


class SetupWizard(_Screen):
    """27.1 First-run setup: configure tools, run doctor."""

    def __init__(self, service) -> None:
        super().__init__(service)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Setup</b> — configure local tools, then run doctor."))
        form = QFormLayout()
        self.godot = QLineEdit()
        self.blender = QLineEdit()
        self.python = QLineEdit()
        form.addRow("Godot executable", self.godot)
        form.addRow("Blender executable", self.blender)
        form.addRow("Python executable", self.python)
        layout.addLayout(form)
        self.doctor_out = QPlainTextEdit(); self.doctor_out.setReadOnly(True)
        layout.addWidget(self.doctor_out)
        btns = QHBoxLayout()
        save = QPushButton("Save tools.local.json"); save.clicked.connect(self._save)
        run = QPushButton("Run doctor"); run.clicked.connect(self._doctor)
        btns.addWidget(save); btns.addWidget(run); btns.addStretch(1)
        layout.addLayout(btns)
        self.refresh()

    def refresh(self) -> None:
        tools = self.service.load_tools_local()
        self.godot.setText(tools.get("godot_executable", ""))
        self.blender.setText(tools.get("blender_executable", ""))
        self.python.setText(tools.get("python_executable", ""))

    def _save(self) -> None:
        tools = self.service.load_tools_local()
        tools["godot_executable"] = self.godot.text().strip()
        tools["blender_executable"] = self.blender.text().strip()
        tools["python_executable"] = self.python.text().strip()
        self.service.save_tools_local(tools)
        self.status.emit("Saved tools.local.json")

    def _doctor(self) -> None:
        report = self.service.doctor()
        lines = [f"worst: {report.get('worst')}"]
        for c in report.get("checks", []):
            lines.append(f"  {c.get('status',''):14} {c.get('name','')}  {c.get('detail','')}")
        self.doctor_out.setPlainText("\n".join(lines))
        self.status.emit(f"Doctor: {report.get('worst')}")


class Dashboard(_Screen):
    """27.2 Missions x stages, with the key status columns."""

    mission_activated = Signal(str)

    def __init__(self, service) -> None:
        super().__init__(service)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Factory Dashboard</b>"))
        self.filter = QComboBox()
        self.filter.addItems(["All", "Blocked", "Waiting for approval", "Handoff ready"])
        self.filter.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filter)
        self.view, self.model = self._table()
        self.view.doubleClicked.connect(self._activate)
        layout.addWidget(self.view)

    def refresh(self) -> None:
        rows = self.service.dashboard()
        f = self.filter.currentText()
        if f == "Blocked":
            rows = [r for r in rows if r.blocker_count > 0]
        elif f == "Waiting for approval":
            rows = [r for r in rows if len(r.approved_gates) < 6]
        elif f == "Handoff ready":
            rows = [r for r in rows if r.handoff_status == "ready"]
        self.model.set_rows(rows)

    def _activate(self, index) -> None:
        row = self.model.row_object(index.row())
        if row is not None:
            self.mission_activated.emit(row.mission_id)


class PipelineView(_Screen):
    """27.4 Mission DAG with per-node state; selecting a node shows detail."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Pipeline</b>"))
        self.view, self.model = self._table()
        self.view.clicked.connect(self._show_detail)
        left.addWidget(self.view)
        layout.addLayout(left, 3)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True)
        layout.addWidget(self.detail, 2)

    def refresh(self) -> None:
        if not self.mission_id:
            self.model.set_rows([]); return
        self.model.set_rows(self.service.pipeline(self.mission_id, "presentation"))

    def _show_detail(self, index) -> None:
        node = self.model.row_object(index.row())
        if node is None or not self.mission_id:
            return
        d = self.service.node_detail(self.mission_id, node.job_id, "presentation")
        text = (f"job: {d.job_id}\nstage: {d.stage_id}\nadapter: {d.adapter_id}\n"
                f"state: {d.state}\nattempts: {d.attempts}\nfingerprint: {d.fingerprint}\n"
                f"command: {d.command}\noutputs: {', '.join(d.outputs)}\n"
                f"dependents: {', '.join(d.dependents)}\n\n--- log tail ---\n"
                + "\n".join(d.log_tail))
        self.detail.setPlainText(text)


class CandidateGallery(_Screen):
    """27.5 Compare candidates (metrics, validation, launch)."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Candidate Gallery</b> (metrics compare; they do not select)"))
        self.view, self.model = self._table()
        layout.addWidget(self.view)
        btn = QPushButton("Select highlighted candidate")
        btn.clicked.connect(self._select)
        layout.addWidget(btn)

    def refresh(self) -> None:
        if not self.mission_id:
            self.model.set_rows([]); return
        self.model.set_rows(self.service.candidates(self.mission_id))

    def _select(self) -> None:
        idx = self.view.currentIndex()
        card = self.model.row_object(idx.row()) if idx.isValid() else None
        if card and self.mission_id:
            self.service.select_candidate(self.mission_id, card.candidate_id)
            self.status.emit(f"Selected {card.candidate_id}")


class ArtPassScreen(_Screen):
    """27.6 Presentation sections + progress."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Art Pass</b>"))
        self.list = QListWidget()
        layout.addWidget(self.list)
        run = QPushButton("Run presentation pipeline")
        run.clicked.connect(self._run)
        layout.addWidget(run)

    def refresh(self) -> None:
        self.list.clear()
        if not self.mission_id:
            return
        for s in self.service.art_pass(self.mission_id):
            self.list.addItem(f"{s.name:32} {s.status}")

    def _run(self) -> None:
        if not self.mission_id:
            return
        self.status.emit("Running presentation…")
        r = self.service.run(self.mission_id, "presentation")
        self.status.emit(f"Presentation exit {r.exit_code}")
        self.refresh()


class ValidationCenter(_Screen):
    """27.7 Unified normalized issue list."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Validation Center</b>"))
        self.severity = QComboBox()
        self.severity.addItems(["all", "blocker", "major", "moderate", "minor", "info"])
        self.severity.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.severity)
        self.view, self.model = self._table()
        layout.addWidget(self.view)

    def refresh(self) -> None:
        sev = self.severity.currentText()
        rows = self.service.validation(self.mission_id,
                                       None if sev == "all" else sev)
        self.model.set_rows(rows)


class JobConsole(_Screen):
    """27.8 Live command + logs for a selected job."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Job Console</b>"))
        self.picker = QComboBox()
        self.picker.currentIndexChanged.connect(self._show)
        layout.addWidget(self.picker)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        layout.addWidget(self.out)

    def refresh(self) -> None:
        self.picker.clear()
        if not self.mission_id:
            return
        for node in self.service.pipeline(self.mission_id, "presentation"):
            self.picker.addItem(node.job_id)

    def _show(self) -> None:
        job_id = self.picker.currentText()
        if not job_id:
            return
        jc = self.service.job_console(job_id)
        if jc is None:
            self.out.setPlainText(f"{job_id}: not run yet"); return
        self.out.setPlainText(
            f"state: {jc.state}\nresource: {jc.resource_class}\n"
            f"elapsed: {jc.elapsed_seconds:.2f}s\ncommand: {jc.command}\n"
            f"work: {jc.work_folder}\n\n--- log tail ---\n" + "\n".join(jc.log_tail))


class HandoffScreen(_Screen):
    """27.9 Readiness table + export/portability actions."""

    def __init__(self, service, mission_getter) -> None:
        super().__init__(service, mission_getter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Handoff</b>"))
        self.list = QListWidget()
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["portable-godot", "pure-shell", "source-authoring"])
        row.addWidget(QLabel("Export mode:")); row.addWidget(self.mode)
        exp = QPushButton("Export folder"); exp.clicked.connect(self._export)
        zp = QPushButton("Deterministic ZIP"); zp.clicked.connect(self._zip)
        port = QPushButton("Portability test"); port.clicked.connect(self._port)
        row.addWidget(exp); row.addWidget(zp); row.addWidget(port); row.addStretch(1)
        layout.addLayout(row)

    def refresh(self) -> None:
        self.list.clear()
        if not self.mission_id:
            return
        status = self.service.handoff(self.mission_id)
        for r in status.rows:
            self.list.addItem(f"{r.label:34} {r.status}")

    def _export(self) -> None:
        if not self.mission_id:
            return
        r = self.service.export(self.mission_id, self.mode.currentText(), "folder")
        self.status.emit("Export blocked by regression" if r.blocked
                         else f"Exported ({self.mode.currentText()})")

    def _zip(self) -> None:
        if not self.mission_id:
            return
        r = self.service.export(self.mission_id, self.mode.currentText(), "zip")
        self.status.emit("Export blocked by regression" if r.blocked else "ZIP created")

    def _port(self) -> None:
        if not self.mission_id:
            return
        r = self.service.portability_test(self.mission_id, self.mode.currentText())
        self.status.emit(f"Portability exit {r.exit_code}")
