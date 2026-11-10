"""The Finished screen: what ran and how it ended, warnings worth reading, where the files are, how to install them,
and buttons for the install status (status_view), setting the output up in MO2 and playing (mo2_setup).

See: docs/fork/fo4_gui.md#finished
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from fo4_import.app import mo2_setup
from fo4_import.app.stages import target
from fo4_import.app.status_view import InstallStatusDialog, install_checks

#: Warnings shown at most.
MAX_WARNINGS = 200
INSTALL_NOTES = (
    'Install the output folder with any mod manager:\n'
    '- Mod Organizer 2: with the output folder in the instance\'s "mods" folder, "Set up in MO2" enables it and '
    'its plugins; otherwise copy the folder there (or install the zip) and enable them.\n'
    '- Vortex: install the zip (or the folder zipped) as a mod.\n'
    '- By hand: copy the folder\'s contents into Fallout 4\'s Data folder and enable the plugins.\n'
    'The plugins need F4SE, Address Library, Extended Dialogue Interface, LevelUpMenuEx, MCM and '
    'Black Landscape Fix installed ("Install status" checks them). The "Install the F4SE plugin" stage puts '
    'F3NV.dll in the game\'s output.')


def summary(results: list) -> str:
    """One line per stage: its label, how it ended and how long it took."""
    if not results:
        return 'Nothing ran.'
    return '\n'.join(f'{r.label}: ' + ('stopped' if r.code is None else 'done' if r.code == 0 else f'failed ({r.code})')
                     + f' in {r.seconds:.0f}s' for r in results)


class FinishedView(QWidget):
    """The outcome of the last run."""

    def __init__(self, get_settings, parent=None):
        """An empty Finished screen; `get_settings()` gives the current settings for its buttons."""
        super().__init__(parent)
        self.folder, self.get_settings = None, get_settings
        self.headline, self.stages, self.where = QLabel('No conversion has run yet.'), QLabel(), QLabel()
        self.headline.setStyleSheet('font-size: 16px; font-weight: bold')
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.where.setWordWrap(True)
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.open = QPushButton('Open folder')
        self.open.clicked.connect(self._open)
        self.open.setEnabled(False)
        row, actions, self.result = QHBoxLayout(), QHBoxLayout(), QLabel()
        row.addWidget(self.where, 1)
        row.addWidget(self.open)
        for label, slot in (('Install status', self._status), ('Set up in MO2', self._set_up), ('Play', self._play)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addWidget(self.result, 1)
        self.result.setWordWrap(True)
        notes = QLabel(INSTALL_NOTES)
        notes.setWordWrap(True)
        box = QVBoxLayout(self)
        for widget in (self.headline, self.stages):
            box.addWidget(widget)
        box.addLayout(row)
        box.addLayout(actions)
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

    def _status(self) -> None:
        """Show the install status for the current settings."""
        InstallStatusDialog(install_checks(self.get_settings()), self).exec()

    def _set_up(self) -> None:
        """Enable the chosen target's mod and plugins in the MO2 profile, after the user agrees."""
        settings = self.get_settings()
        source, why = settings['source'], mo2_setup.blocker(settings, settings['source'])
        if why:
            self.result.setText(f'Not set up: {why}.')
            return
        found, names = mo2_setup.instance(settings), mo2_setup.plugins(settings, source)
        ask = (f'Enable "{target(settings, source).output.name}" in MO2 profile "{found.profile}" '
               f'and its plugins {", ".join(names)}? The profile\'s lists are backed up first.')
        if QMessageBox.question(self, 'Set up in MO2', ask) == QMessageBox.StandardButton.Yes:
            self.result.setText('Set up: ' + '; '.join(mo2_setup.set_up(settings, source)) + '.')

    def _play(self) -> None:
        """Start the game through F4SE."""
        why = mo2_setup.play(self.get_settings())
        self.result.setText(f'Not started: {why}.' if why else 'Starting Fallout 4 through F4SE...')

    def _open(self) -> None:
        """Open the output folder in the system's file browser."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))
