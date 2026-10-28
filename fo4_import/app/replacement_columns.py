"""The Replacements screen's two columns: the source forms with what stands in for each (left), and the installed
plugins' records to pick from (right), each with a 3D preview and stats.

See: docs/fork/fo4_gui.md#replacements-screen
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QRadioButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from fo4_import.app.preview.viewer import PreviewWidget

#: Table rows shown at most (the most placed first), so a category opens quickly.
MAX_ROWS = 2000
#: Mode labels.
MODE_LABELS = {'item': 'Use the record as it is', 'stats': "Its model, with FNV's name and stats",
               'fnv': "FNV's own mesh on it", 'speaker': "An unseen speaker beside FNV's model (talking machines)"}


def stats_text(stats: dict) -> str:
    """Stats as 'label value' pairs on one line ('' for none)."""
    return ', '.join(f'{k} {v}' for k, v in stats.items())


def _table(headers: list) -> QTableWidget:
    """A read-only, row-selecting table with `headers`."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


def fill(table: QTableWidget, rows: list) -> None:
    """Show `rows` [(cells, color or None[, {column: tooltip}])] in `table` (at most MAX_ROWS)."""
    table.setRowCount(0)
    table.setRowCount(min(len(rows), MAX_ROWS))
    for r, (cells, color, *tips) in enumerate(rows[:MAX_ROWS]):
        for c, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            if color:
                item.setForeground(color)
            if tips and c in tips[0]:
                item.setToolTip(tips[0][c])
            table.setItem(r, c, item)


class Preview(QWidget):
    """A 3D preview, or a message in its place when there is nothing to show."""

    def __init__(self, parent=None):
        """An empty preview."""
        super().__init__(parent)
        self.view, self.message = PreviewWidget(), QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.message)
        self.stack.addWidget(self.view)
        QVBoxLayout(self).addWidget(self.stack)
        self.say('Pick a row to preview it.')

    def say(self, text: str) -> None:
        """Show `text` instead of a model."""
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def show_parts(self, parts: list, surfaces: list, empty: str) -> None:
        """Show `parts`, or `empty` when there are none."""
        if not parts:
            self.say(empty)
            return
        self.view.show_model(parts, surfaces)
        self.stack.setCurrentWidget(self.view)


class SourceColumn(QWidget):
    """Left: the source forms, what stands in for each, and a preview of FNV's mesh or the stand-in."""
    picked = Signal()

    def __init__(self, parent=None):
        """An empty column."""
        super().__init__(parent)
        self.table = _table(['Name', 'EditorID', 'Placed', 'Stand-in', 'Chosen by', 'Suggested'])
        self.table.itemSelectionChanged.connect(self.picked.emit)
        self.which = QButtonGroup(self)
        row = QHBoxLayout()
        for i, label in enumerate(("FNV's mesh (as converted)", 'Current stand-in')):
            radio = QRadioButton(label)
            radio.setChecked(i == 1)
            self.which.addButton(radio, i)
            row.addWidget(radio)
        self.which.idToggled.connect(lambda _id, on: on and self.picked.emit())
        self.preview, self.stats = Preview(), QLabel()
        self.stats.setWordWrap(True)
        box = QVBoxLayout(self)
        box.addWidget(QLabel('<b>Original / current</b>'))
        box.addWidget(self.table, 3)
        box.addLayout(row)
        box.addWidget(self.preview, 4)
        box.addWidget(self.stats)

    def show_fnv(self) -> bool:
        """Whether the preview should show FNV's mesh rather than the stand-in."""
        return self.which.checkedId() == 0


class TargetColumn(QWidget):
    """Right: a plugin picker, its records in the category, the mode, a preview, stats, Apply and Revert."""
    picked = Signal()

    def __init__(self, parent=None):
        """An empty column."""
        super().__init__(parent)
        self.plugin, self.search, self.mode = QComboBox(), QLineEdit(), QComboBox()
        self.search.setPlaceholderText('Search names and EditorIDs')
        self.browse = QCheckBox('Browse all records')
        self.browse.setToolTip("Off: a form with a suggestion lists its matches, the suggestion picked.\n"
                               "On: list the chosen plugin's records of the category.")
        self.table = _table(['Name', 'EditorID', 'Plugin', 'Stats'])
        self.table.itemSelectionChanged.connect(self.picked.emit)
        self.preview, self.stats, self.caption = Preview(), QLabel(), QLabel()
        self.stats.setWordWrap(True)
        top, bottom = QHBoxLayout(), QHBoxLayout()
        top.addWidget(QLabel('From'))
        top.addWidget(self.plugin, 1)
        top.addWidget(self.search, 1)
        top.addWidget(self.browse)
        bottom.addWidget(QLabel('Mode'))
        bottom.addWidget(self.mode, 1)
        box = QVBoxLayout(self)
        box.addWidget(QLabel('<b>Replacement</b>'))
        box.addLayout(top)
        box.addWidget(self.caption)
        box.addWidget(self.table, 3)
        box.addLayout(bottom)
        box.addWidget(self.preview, 4)
        box.addWidget(self.stats)

    def set_modes(self, modes: tuple) -> None:
        """Offer only `modes`."""
        self.mode.clear()
        for mode in modes:
            self.mode.addItem(MODE_LABELS[mode], mode)
