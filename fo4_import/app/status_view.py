"""The install status dialog: tools.validate.fo4_install_check's lines for the app's settings, problems in red.

What the README's "What you need" lists (the game and its version, F4SE, the Creation Kit, MO2 and its F4SE and
Creation Kit executables, each required mod where the game sees it) and, after a conversion, each converted plugin
in its own enabled MO2 mod with F3NV.dll beside the game's.

See: docs/fork/fo4_gui.md#install-status
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QVBoxLayout)

from fo4_import.app import settings as S
from fo4_import.app.replacement_columns import fill
from tools.validate.fo4_install_check import PASSING, checks, free_bytes, machine_from

PROBLEM = QColor(200, 40, 40)
HEADERS = ['Check', 'Status', 'What to do']


def install_checks(settings: dict) -> list:
    """The install check's Checks for `settings`."""
    return checks(machine_from(settings), free_bytes(S.work_dir(settings)))


def summary(report: list) -> str:
    """One line: all OK, or how many checks need attention."""
    todo = [c for c in report if c.status not in PASSING]
    return f'{len(todo)} of {len(report)} checks need attention.' if todo else f'All {len(report)} checks are OK.'


class InstallStatusDialog(QDialog):
    """The Checks of `report`, problems in red, the summary above."""

    def __init__(self, report: list, parent=None):
        """A dialog listing `report`."""
        super().__init__(parent)
        self.setWindowTitle('Install status')
        self.resize(1000, 560)
        text, self.table = QLabel(summary(report)), QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        fill(self.table, [((c.name, c.status, c.detail), None if c.status in PASSING else PROBLEM) for c in report])
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        box.addWidget(text)
        box.addWidget(self.table, 1)
        box.addWidget(close)
