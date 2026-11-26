"""The Convert screen, top to bottom: 1. the game (New Vegas or Fallout 3), 2. what to convert (the game, a DLC or
an added mod; fo4_import.app.target_box), then the next step in words (stages.next_step) over one Convert button,
Add to queue (fo4_import.app.queue_box: the targets that convert next), Stop, the build's estimated time and the
live log. Advanced options, folded away, hold the stages and what the
build covers (whole by default; a DLC or mod builds what it changes, so the test block is off for one).

A stage that cannot run here is shown disabled with the reason (stages.unavailable); beside each is what an earlier
run left (stages.found), and a stage already done starts unticked. The stages run on a QThread through
fo4_import.app.runner; a zip is made afterwards when the user chose zip output.

See: docs/fork/fo4_gui.md#convert-screen
"""

import time

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from fo4_import.app import stages
from fo4_import.app.mo2_setup import environment
from fo4_import.app.queue_box import Queued, QueueBox, named, settings_for
from fo4_import.app.runner import Runner, activity
from fo4_import.app.target_box import TargetBox
from fo4_import.pipeline import eta

#: Lines the log keeps.
LOG_LINES = 20000
SCOPES = (('world', 'Whole (the game: every worldspace a door or script reaches; a DLC or mod: all it changes)'),
          ('test', 'Test block (3x3 cells around the start, plus its interiors)'), ('region', 'Region (grid corners)'))
#: Milliseconds between activity line updates while a run goes.
ACTIVITY_MS = 2000
#: The advanced toggle's text, folded and open.
ADVANCED = ('Show advanced options (stages, what the build covers)', 'Hide advanced options')


class StageThread(QThread):
    """Runs a stage plan off the window's thread; `line` per output line, `done` with (Results, warnings, zip)."""
    line = Signal(str)
    done = Signal(list, list, str)

    def __init__(self, plan: list, settings: dict, source: str):
        """A thread running `plan` for `source` with `settings` (for zip output)."""
        super().__init__()
        name = stages.plugin_path(settings, source).name
        self.runner, self.settings, self.source = Runner(plan, environment(settings), name), settings, source

    def run(self) -> None:
        """Run the plan, then zip the output if every stage succeeded and zip was chosen."""
        results = self.runner.run(self.line.emit)
        ok = bool(results) and all(r.code == 0 for r in results)
        made = stages.package(self.settings, self.source) if ok else None
        self.done.emit(results, self.runner.warnings, str(made or ''))


class ConvertView(QWidget):
    """Game, target, next step, run controls, queue and log. `get_settings()` gives (settings, saved settings file);
    `game_changed` names the game the user picked; `finished` gives (results, warnings, zips, output folder)."""
    finished = Signal(list, list, str, str)
    game_changed = Signal(str)

    def __init__(self, get_settings, parent=None):
        """The screen; `get_settings` saves and returns the current settings when a run starts."""
        super().__init__(parent)
        self.get_settings, self.thread, self.batch, self.item = get_settings, None, [], None
        self.queue, self.enqueue = QueueBox(), QPushButton('Add to queue')
        self.queue.run_clicked.connect(self._run_queue)
        self.enqueue.clicked.connect(self._add_to_queue)
        self.checks = {key: QCheckBox(label) for key, label in stages.ORDER}
        self.found = {key: QLabel() for key, _label in stages.ORDER}
        self.done_before = {}
        self.games = QButtonGroup(self)
        self.scopes, self.corners = QButtonGroup(self), [QSpinBox() for _ in range(4)]
        self.workers = QSpinBox()
        self.workers.setRange(0, 256)
        self.workers.setSpecialValueText('as the resource setting allows')
        self.start, self.stop = QPushButton('Convert'), QPushButton('Stop')
        self.start.setStyleSheet('font-size: 15px; font-weight: bold; padding: 8px 24px')
        self.start.clicked.connect(self._start)
        self.stop.clicked.connect(self._stop)
        self.stop.setEnabled(False)
        self.target, self.settings = TargetBox(lambda: self.refresh(self.settings, relist=False)), None
        self.next, self.status, self.log, self.estimate = QLabel(), QLabel('Ready.'), QPlainTextEdit(), QLabel()
        self.next.setWordWrap(True)
        self.next.setStyleSheet('font-weight: bold')
        self.estimate.setWordWrap(True)
        self.status.setWordWrap(True)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LINES)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.advanced, self.more = QWidget(), QToolButton()
        self.alive, self.ticker, self.last_output = QLabel(), QTimer(self), 0.0
        self.alive.setStyleSheet('color: gray')
        self.ticker.setInterval(ACTIVITY_MS)
        self.ticker.timeout.connect(self._tick)
        self._layout()

    def _layout(self) -> None:
        """Arrange the game, the target, the next step and its buttons, the folded advanced options and the log."""
        controls = QHBoxLayout()
        for widget in (self.start, self.enqueue, self.stop):
            controls.addWidget(widget)
        controls.addWidget(self.status, 1)
        self.more.setText(ADVANCED[0])
        self.more.setCheckable(True)
        self.more.toggled.connect(self._fold)
        options = QHBoxLayout(self.advanced)
        options.setContentsMargins(0, 0, 0, 0)
        options.addWidget(self._stage_box())
        options.addWidget(self._scope_box(), 1)
        self.advanced.setVisible(False)
        box = QVBoxLayout(self)
        for widget in (self._game_box(), self.target, self.next):
            box.addWidget(widget)
        box.addLayout(controls)
        for widget in (self.queue, self.estimate, self.alive, self.more, self.advanced):
            box.addWidget(widget)
        box.addWidget(self.log, 1)

    def _game_box(self) -> QGroupBox:
        """1. Game: a choice per source game; picking one emits game_changed."""
        group, row = QGroupBox('1. Game'), QHBoxLayout()
        for source, game in stages.GAMES.items():
            radio = QRadioButton(game['label'] + (f" ({game['note']})" if game['note'] else ''))
            radio.setProperty('source', source)
            self.games.addButton(radio)
            row.addWidget(radio)
        row.addStretch(1)
        group.setLayout(row)
        self.games.buttonClicked.connect(lambda radio: self.game_changed.emit(radio.property('source')))
        return group

    def _stage_box(self) -> QGroupBox:
        """The stages, each ticked by default, with what an earlier run left beside it."""
        box = QGroupBox('Stages')
        grid = QGridLayout(box)
        for row, key in enumerate(self.checks):
            self.checks[key].setChecked(True)
            self.found[key].setStyleSheet('color: gray')
            grid.addWidget(self.checks[key], row, 0)
            grid.addWidget(self.found[key], row, 1)
        return box

    def _scope_box(self) -> QGroupBox:
        """What the build covers (whole by default), the region's corners and the workers."""
        box = QGroupBox('What the build covers')
        grid = QGridLayout(box)
        for row, (key, label) in enumerate(SCOPES):
            radio = QRadioButton(label)
            radio.setProperty('scope', key)
            radio.setChecked(key == 'world')
            self.scopes.addButton(radio)
            grid.addWidget(radio, row, 0, 1, 5)
        for col, (spin, name) in enumerate(zip(self.corners, ('X0', 'Y0', 'X1', 'Y1'))):
            spin.setRange(-128, 128)
            spin.setPrefix(f'{name} ')
            grid.addWidget(spin, len(SCOPES), col + 1)
        grid.addWidget(QLabel('Workers'), len(SCOPES) + 1, 0)
        grid.addWidget(self.workers, len(SCOPES) + 1, 1, 1, 2)
        return box

    def _fold(self, shown: bool) -> None:
        """Show or fold the advanced options."""
        self.advanced.setVisible(shown)
        self.more.setText(ADVANCED[shown])

    def refresh(self, settings: dict, relist: bool = True) -> None:
        """Show the games (one whose folder is not set disabled, with why), the targets (relisted unless the
        target list itself asked), the next step, and the stages that can run; a stage that became done (or
        stopped being done) is unticked (or ticked, unless OPTIONAL) once."""
        self.settings, source = settings, settings['source']
        for radio in self.games.buttons():
            game, problem = radio.property('source'), stages.game_problem(settings, radio.property('source'))
            radio.setEnabled(not problem or game == source)
            radio.setToolTip(problem)
            radio.setChecked(game == source)
        if relist:
            self.target.show_settings(settings)
        chosen = stages.target(settings, source)
        name = stages.GAMES[source]['master'] if chosen.game else chosen.plugin
        self.start.setText(f'Convert {name}')
        self.enqueue.setText(f'Add {name} to queue')
        self.next.setText(stages.next_step(settings, source))
        self._addon_scopes(not chosen.game)
        self._stages(settings, source)
        if not self.stop.isEnabled():
            self.estimate.setText(stages.estimate(settings, source))

    def _stages(self, settings: dict, source: str) -> None:
        """Enable the stages that can run, naming why the others cannot, and show what earlier runs left."""
        done = []
        for key, label in stages.ORDER:
            why = stages.unavailable(settings, source, key)
            self.checks[key].setEnabled(not why)
            found = stages.found(settings, source, key)
            self.found[key].setText(f'unavailable: {why}' if why else f'found: {found.text}' if found else '')
            now = bool(found and found.done)
            if self.done_before.get(key) != now:
                self.checks[key].setChecked(not now and key not in stages.OPTIONAL)
            self.done_before[key] = now
            done += [label] if now else []
        if done and not self.stop.isEnabled():
            self.status.setText(f"Already done, so skipped: {', '.join(done)}.")

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

    def _current(self) -> Queued:
        """The chosen target with its ticked stages and scope, the settings saved first."""
        self.target.write()
        settings, _file = self.get_settings()
        chosen = tuple(k for k, c in self.checks.items() if c.isChecked())
        plugin = settings['per_source'][settings['source']].get('target', '')
        return Queued(settings['source'], plugin, chosen, self.scope())

    def _start(self) -> None:
        """Convert the chosen target now; the queue follows it."""
        self.batch = []
        self.log.clear()
        if not self._launch(self._current()):
            self.status.setText('Nothing to run: no stage that can run is ticked (see the advanced options).')

    def _add_to_queue(self) -> None:
        """Queue the chosen target after the running build (or for Run queue)."""
        item = self._current()
        self.queue.add(item)
        after = 'after the running build' if self.stop.isEnabled() else 'when you click Run queue'
        self.status.setText(f'Queued {item.name()}: it converts {after}.')

    def _run_queue(self) -> None:
        """Convert the queued targets in order."""
        self.batch = []
        self.log.clear()
        self._next()

    def _next(self) -> bool:
        """Start the next queued target that has a stage to run, skipping (and noting) any without; False if none."""
        item = self.queue.take()
        while item is not None and not self._launch(item):
            self.log.appendPlainText(f'Queue: nothing to run for {item.name()} (no ticked stage can run); skipped.')
            item = self.queue.take()
        return item is not None

    def _launch(self, item: Queued) -> bool:
        """Run `item`'s ticked stages that can run now; False when none can."""
        settings, settings_file = self.get_settings()
        settings = settings_for(settings, item)
        plan = stages.plan(settings, item.source, list(item.chosen), item.scope, settings_file)
        if not plan:
            return False
        self.log.appendPlainText(f'===== Converting {item.name()} =====')
        self.thread, self.item = StageThread(plan, settings, item.source), (item, stages.target(settings, item.source))
        self.thread.line.connect(self._line)
        self.thread.done.connect(self._done)
        self._busy(True)
        self.status.setText(f'Converting {item.name()}: {len(plan)} stage(s)...')
        self.last_output = time.monotonic()
        self.ticker.start()
        self.thread.start()
        return True

    def _busy(self, busy: bool) -> None:
        """Enable Stop while a build runs, Convert and Run queue while none does."""
        self.start.setEnabled(not busy)
        self.stop.setEnabled(busy)
        self.queue.running(busy)

    def _tick(self) -> None:
        """Show how long the log has been quiet and whether the build is using the CPU."""
        if self.thread is not None:
            quiet = time.monotonic() - self.last_output
            self.alive.setText(activity(quiet, self.thread.runner.watch.sample()))

    def _line(self, line: str) -> None:
        """A build's progress line under the controls; any other line to the log, an 'estimate:' one under the
        controls too."""
        if line.startswith(eta.PROGRESS):
            self.estimate.setText(line.removeprefix(eta.PROGRESS))
            return
        self.last_output = time.monotonic()
        self.log.appendPlainText(line)
        if line.startswith('estimate: '):
            self.estimate.setText('Estimated: ' + line.removeprefix('estimate: '))

    def _stop(self) -> None:
        """Stop the running stage; the queue waits."""
        if self.thread is not None:
            self.thread.runner.stop()
            self.status.setText('Stopping; the queue waits until you click Run queue...')

    def _done(self, results: list, warnings: list, made_zip: str) -> None:
        """Record the target's outcome; on success start the next queued one, else hand on every outcome."""
        self.ticker.stop()
        self.alive.clear()
        item, chosen = self.item
        self.batch.append((item.name(), results, warnings, made_zip, chosen.output))
        ok = bool(results) and all(r.code == 0 for r in results)
        if ok and self._next():
            return
        self._busy(False)
        failed = [r for r in results if r.code != 0]
        waiting = f' {len(self.queue.items)} queued target(s) wait: Run queue continues.' if self.queue.items else ''
        self.status.setText((f'Stopped or failed at: {item.name()}, {failed[0].label}.' if failed else 'Finished.')
                            + waiting)
        self._report()

    def _report(self) -> None:
        """Hand on the outcome of every target this run converted, stage labels named by target when several."""
        several = len(self.batch) > 1
        results = [r for name, done, *_ in self.batch for r in (named(done, name) if several else done)]
        warnings = [w for _name, _done, said, *_ in self.batch for w in said]
        zips = '\n'.join(z for *_, z, _folder in self.batch if z)
        self.finished.emit(results, warnings, zips, str(self.batch[-1][4]))
