"""The Finished screen: what ran and how it ended, warnings worth reading, where the files are, how to install them.

See: docs/fork/fo4_gui.md#finished
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

#: Warnings shown at most.
MAX_WARNINGS = 200
INSTALL_NOTES = (
    'Install the output folder with any mod manager:\n'
    '- Mod Organizer 2: copy the folder into the instance\'s "mods" folder (or install the zip), then enable it '
    'and its plugins.\n'
    '- Vortex: install the zip (or the folder zipped) as a mod.\n'
    '- By hand: copy the folder\'s contents into Fallout 4\'s Data folder and enable the plugins.\n'
    'The plugins need F4SE, Address Library, Extended Dialogue Interface, LevelUpMenuEx and MCM installed.\n'
    'This alpha does not build the F3NV F4SE plugin (F3NV.dll, tes_runtime/fo4_condition) yet: install it '
    'separately.')


def summary(results: list) -> str:
    """One line per stage: its label, how it ended and how long it took."""
    if not results:
        return 'Nothing ran.'
    return '\n'.join(f'{r.label}: ' + ('stopped' if r.code is None else 'done' if r.code == 0 else f'failed ({r.code})')
                     + f' in {r.seconds:.0f}s' for r in results)


class FinishedView(QWidget):
    """The outcome of the last run."""

    def __init__(self, parent=None):
        """An empty Finished screen."""
        super().__init__(parent)
        self.folder = None
        self.headline, self.stages, self.where = QLabel('No conversion has run yet.'), QLabel(), QLabel()
        self.headline.setStyleSheet('font-size: 16px; font-weight: bold')
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.where.setWordWrap(True)
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.open = QPushButton('Open folder')
        self.open.clicked.connect(self._open)
        self.open.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.where, 1)
        row.addWidget(self.open)
        notes = QLabel(INSTALL_NOTES)
        notes.setWordWrap(True)
        box = QVBoxLayout(self)
        for widget in (self.headline, self.stages):
            box.addWidget(widget)
        box.addLayout(row)
        box.addWidget(QLabel('Warnings from the run:'))
        box.addWidget(self.warnings, 1)
        box.addWidget(notes)

    def show_outcome(self, results: list, warnings: list, folder: Path, made_zip: str = '') -> None:
        """Show a run's `results` and `warnings`, and the output `folder` (and zip, if one was made)."""
        ok = bool(results) and all(r.code == 0 for r in results)
        self.headline.setText('Conversion finished.' if ok else 'Conversion did not finish.')
        self.stages.setText(summary(results))
        self.folder = folder
        self.where.setText(f'Converted files: {folder}' + (f'\nZip: {made_zip}' if made_zip else ''))
        self.open.setEnabled(Path(folder).is_dir())
        unique = list(dict.fromkeys(warnings))
        self.warnings.setPlainText('\n'.join(unique[:MAX_WARNINGS]) or 'None.')

    def _open(self) -> None:
        """Open the output folder in the system's file browser."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))
