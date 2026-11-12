"""The Convert screen: which stages run, what the build covers, Start and Stop, and the live log.

What it converts is chosen above the stages (fo4_import.app.target_box): the game, a DLC or an added mod; a DLC
or mod builds what it changes, so the test block is off for one. A stage that cannot run here is shown disabled
with the reason (fo4_import.app.stages.unavailable). Beside each
stage is what an earlier run (the app's or the command line's) left (stages.found); the export and up-to-date
scripts start unticked. The stages
run on a QThread through fo4_import.app.runner; a zip is made afterwards when the user chose zip output. Under the
controls is the build's estimated time (stages.estimate), replaced while it runs by the build's own 'estimate:' lines.

See: docs/fork/fo4_gui.md#app-shape
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget)

from fo4_import.app import stages
from fo4_import.app.mo2_setup import environment
from fo4_import.app.runner import Runner
from fo4_import.app.target_box import TargetBox

#: Lines the log keeps.
LOG_LINES = 20000
SCOPES = (('test', 'Test block (3x3 cells around the start, plus its interiors)'), ('region', 'Region (grid corners)'),
          ('world', 'Whole (the game: every worldspace a door or script reaches; a DLC or mod: all it changes)'))


class StageThread(QThread):
    """Runs a stage plan off the window's thread; `line` per output line, `done` with (Results, warnings, zip)."""
    line = Signal(str)
    done = Signal(list, list, str)

    def __init__(self, plan: list, settings: dict, source: str):
        """A thread running `plan` for `source` with `settings` (for zip output)."""
        super().__init__()
        self.runner, self.settings, self.source = Runner(plan, environment(settings)), settings, source

    def run(self) -> None:
        """Run the plan, then zip the output if every stage succeeded and zip was chosen."""
        results = self.runner.run(self.line.emit)
        ok = bool(results) and all(r.code == 0 for r in results)
        made = stages.package(self.settings, self.source) if ok else None
        self.done.emit(results, self.runner.warnings, str(made or ''))


class ConvertView(QWidget):
    """Stage choices, scope, run controls and log. `get_settings()` gives (settings, saved settings file)."""
    finished = Signal(list, list, str)

    def __init__(self, get_settings, parent=None):
        """The screen; `get_settings` saves and returns the current settings when a run starts."""
        super().__init__(parent)
        self.get_settings, self.thread = get_settings, None
        self.checks = {key: QCheckBox(label) for key, label in stages.ORDER}
        self.found = {key: QLabel() for key, _label in stages.ORDER}
        self.done_before = {}
        self.scopes, self.corners = QButtonGroup(self), [QSpinBox() for _ in range(4)]
        self.workers = QSpinBox()
        self.workers.setRange(0, 256)
        self.workers.setSpecialValueText('as the resource setting allows')
        self.start, self.stop = QPushButton('Start'), QPushButton('Stop')
        self.start.clicked.connect(self._start)
        self.stop.clicked.connect(self._stop)
        self.stop.setEnabled(False)
        self.target, self.settings = TargetBox(lambda: self.refresh(self.settings)), None
        self.status, self.log, self.estimate = QLabel('Ready.'), QPlainTextEdit(), QLabel()
        self.estimate.setWordWrap(True)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LINES)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._layout()

    def _layout(self) -> None:
        """Arrange stages, scope, controls and log."""
        stage_box = QGroupBox('Stages')
        stage_layout = QGridLayout(stage_box)
        for row, key in enumerate(self.checks):
            self.checks[key].setChecked(True)
            self.found[key].setStyleSheet('color: gray')
            stage_layout.addWidget(self.checks[key], row, 0)
            stage_layout.addWidget(self.found[key], row, 1)
        scope_box = QGroupBox('What the build covers')
        grid = QGridLayout(scope_box)
        for row, (key, label) in enumerate(SCOPES):
            radio = QRadioButton(label)
            radio.setProperty('scope', key)
            radio.setChecked(key == 'test')
            self.scopes.addButton(radio)
            grid.addWidget(radio, row, 0, 1, 5)
        for col, (spin, name) in enumerate(zip(self.corners, ('X0', 'Y0', 'X1', 'Y1'))):
            spin.setRange(-128, 128)
            spin.setPrefix(f'{name} ')
            grid.addWidget(spin, len(SCOPES), col + 1)
        grid.addWidget(QLabel('Workers'), len(SCOPES) + 1, 0)
        grid.addWidget(self.workers, len(SCOPES) + 1, 1, 1, 2)
        top, controls = QHBoxLayout(), QHBoxLayout()
        top.addWidget(stage_box)
        top.addWidget(scope_box, 1)
        for widget in (self.start, self.stop, self.status):
            controls.addWidget(widget)
        controls.addStretch(1)
        box = QVBoxLayout(self)
        box.addWidget(self.target)
        box.addLayout(top)
        box.addLayout(controls)
        box.addWidget(self.estimate)
        box.addWidget(self.log, 1)

    def refresh(self, settings: dict) -> None:
        """Enable the stages that can run for the chosen game, naming why the others cannot, and show what earlier
        runs left; a stage that became done (or stopped being done) is unticked (or ticked, unless OPTIONAL) once."""
        if settings is not self.settings:
            self.settings = settings
            self.target.show_settings(settings)
        self._addon_scopes(not stages.target(settings, settings['source']).game)
        done = []
        for key, label in stages.ORDER:
            why = stages.unavailable(settings, settings['source'], key)
            self.checks[key].setEnabled(not why)
            self.checks[key].setText(label + (f'  (unavailable: {why})' if why else ''))
            found = stages.found(settings, settings['source'], key)
            self.found[key].setText(f'found: {found.text}' if found else '')
            now = bool(found and found.done)
            if self.done_before.get(key) != now:
                self.checks[key].setChecked(not now and key not in stages.OPTIONAL)
            self.done_before[key] = now
            done += [label] if now else []
        if done and not self.stop.isEnabled():
            self.status.setText(f"Already done, so unticked: {', '.join(done)}. Tick a stage to run it again.")
        if not self.stop.isEnabled():
            self.estimate.setText(stages.estimate(settings, settings['source']))

    def _addon_scopes(self, addon: bool) -> None:
        """Turn the test block off for a DLC or mod (it builds what it changes), choosing the whole scope."""
        test = next(b for b in self.scopes.buttons() if b.property('scope') == 'test')
        test.setEnabled(not addon)
        if addon and test.isChecked():
            next(b for b in self.scopes.buttons() if b.property('scope') == 'world').setChecked(True)

    def scope(self) -> stages.Scope:
        """The chosen scope."""
        kind = self.scopes.checkedButton().property('scope')
        return stages.Scope(kind, tuple(s.value() for s in self.corners), self.workers.value())

    def _start(self) -> None:
        """Save the settings and run the chosen stages that can run."""
        self.target.write()
        settings, settings_file = self.get_settings()
        chosen = [k for k, c in self.checks.items() if c.isChecked() and c.isEnabled()]
        plan = stages.plan(settings, settings['source'], chosen, self.scope(), settings_file)
        if not plan:
            self.status.setText('Nothing to run: no stage that can run is ticked.')
            return
        self.log.clear()
        self.thread = StageThread(plan, settings, settings['source'])
        self.thread.line.connect(self.log.appendPlainText)
        self.thread.line.connect(self._estimate_line)
        self.thread.done.connect(self._done)
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.status.setText(f'Running {len(plan)} stage(s)...')
        self.thread.start()

    def _estimate_line(self, line: str) -> None:
        """Show a build's 'estimate:' line under the controls."""
        if line.startswith('estimate: '):
            self.estimate.setText('Estimated: ' + line.removeprefix('estimate: '))

    def _stop(self) -> None:
        """Stop the running stage."""
        if self.thread is not None:
            self.thread.runner.stop()
            self.status.setText('Stopping...')

    def _done(self, results: list, warnings: list, made_zip: str) -> None:
        """Re-enable Start and hand the outcome on."""
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        failed = [r for r in results if r.code != 0]
        self.status.setText(f'Stopped or failed at: {failed[0].label}' if failed else 'Finished.')
        self.finished.emit(results, warnings, made_zip)
