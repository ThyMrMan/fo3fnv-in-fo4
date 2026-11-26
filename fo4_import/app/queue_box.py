"""The Convert screen's queue: targets waiting to convert after the running one, in order, each with the stages
ticked and the scope chosen when it was added. Which stages can run is decided when its turn comes (stages.plan), so
a DLC queued behind its game builds once the game is built.

See: docs/fork/fo4_gui.md#queue
"""

import copy
from dataclasses import dataclass, replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout

from fo4_import.app import stages


@dataclass(frozen=True)
class Queued:
    """One waiting conversion: game `source`, `plugin` ('' the game itself), its ticked `chosen` stages, `scope`."""
    source: str
    plugin: str
    chosen: tuple
    scope: stages.Scope

    def name(self) -> str:
        """The plugin it converts."""
        return self.plugin or stages.GAMES[self.source]['master']

    def text(self) -> str:
        """Its row: the plugin, its game and what the build covers."""
        return f"{self.name()} ({stages.GAMES[self.source]['label']}; {self.scope.kind})"


def settings_for(settings: dict, item: Queued) -> dict:
    """A copy of `settings` converting `item`: its game and target chosen."""
    out = copy.deepcopy(settings)
    out['source'] = item.source
    out['per_source'][item.source]['target'] = item.plugin
    return out


def named(results: list, name: str) -> list:
    """`results`, each stage label led by the plugin `name`."""
    return [replace(r, label=f'{name}: {r.label}') for r in results]


class QueueBox(QGroupBox):
    """The waiting targets with Run queue, Remove and Clear; `run_clicked` asks the screen to start the queue."""
    run_clicked = Signal()

    def __init__(self, parent=None):
        """An empty, hidden queue."""
        super().__init__('Queue: converts next, in order', parent)
        self.items, self.rows = [], QListWidget()
        self.rows.setMaximumHeight(110)
        self.run, remove, clear = QPushButton('Run queue'), QPushButton('Remove'), QPushButton('Clear')
        self.run.clicked.connect(self.run_clicked.emit)
        remove.clicked.connect(self._remove)
        clear.clicked.connect(lambda: self._set([]))
        side = QVBoxLayout()
        for button in (self.run, remove, clear):
            side.addWidget(button)
        side.addStretch(1)
        row = QHBoxLayout(self)
        row.addWidget(self.rows, 1)
        row.addLayout(side)
        self.setVisible(False)

    def add(self, item: Queued) -> None:
        """Queue `item` last."""
        self._set([*self.items, item])

    def take(self) -> 'Queued | None':
        """The first waiting item, removed; None when the queue is empty."""
        if not self.items:
            return None
        first = self.items[0]
        self._set(self.items[1:])
        return first

    def running(self, busy: bool) -> None:
        """Offer Run queue only while nothing runs."""
        self.run.setEnabled(not busy)

    def _remove(self) -> None:
        """Drop the selected row."""
        row = self.rows.currentRow()
        if row >= 0:
            self._set(self.items[:row] + self.items[row + 1:])

    def _set(self, items: list) -> None:
        """Show `items`; the box hides when empty."""
        self.items = items
        self.rows.clear()
        self.rows.addItems([item.text() for item in items])
        self.setVisible(bool(items))
