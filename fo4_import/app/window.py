"""The app's main window (Setup, Convert, Replacements, Finished) and its start: the first-run wizard when no
settings are saved yet.

Settings are saved beside the app (portable) or in the OS's config folder, as the user picks; saving to one
place removes the copy in the other, so the app never reads a stale one.

See: docs/fork/fo4_gui.md#app-shape
"""

from pathlib import Path

from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QMainWindow, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from fo4_import.app import settings as S
from fo4_import.app.convert_view import ConvertView
from fo4_import.app.finished_view import FinishedView
from fo4_import.app.preview.viewer import surface_format
from fo4_import.app.replacements_view import ReplacementsView
from fo4_import.app.setup_view import SetupView
from fo4_import.app.wizard import FirstRunWizard

TITLE = 'FO3/FNV to Fallout 4'


def save_settings(settings: dict, portable: bool) -> Path:
    """Save `settings` beside the app or in the config folder; the file written (the other copy removed)."""
    here, there = (S.APP_DIR, S.config_dir()) if portable else (S.config_dir(), S.APP_DIR)
    written = S.save(settings, here / S.FILE_NAME)
    if (there / S.FILE_NAME).is_file():
        (there / S.FILE_NAME).unlink()
    return written


class MainWindow(QMainWindow):
    """Setup, Convert, Replacements and Finished, over one settings dict."""

    def __init__(self, settings: dict, settings_file: Path):
        """The window over `settings`, saved at `settings_file`."""
        super().__init__()
        self.setWindowTitle(TITLE)
        self.settings_file = settings_file
        self.setup, self.finished = SetupView(), FinishedView()
        self.setup.load(settings, str(settings_file), settings_file.parent == S.APP_DIR)
        self.convert = ConvertView(self.save)
        self.convert.finished.connect(self._finished)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._with_save(self.setup), 'Setup')
        self.tabs.addTab(self.convert, 'Convert')
        self.replacements = ReplacementsView()
        self.tabs.addTab(self.replacements, 'Replacements')
        self.tabs.addTab(self.finished, 'Finished')
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)
        self.resize(1000, 760)

    def _with_save(self, view: QWidget) -> QWidget:
        """`view` with a Save button under it."""
        holder, buttons, box = QWidget(), QHBoxLayout(), QVBoxLayout()
        save = QPushButton('Save settings')
        save.clicked.connect(self.save)
        buttons.addStretch(1)
        buttons.addWidget(save)
        box.addWidget(view, 1)
        box.addLayout(buttons)
        holder.setLayout(box)
        return holder

    def save(self) -> tuple:
        """Save the Setup screen's settings; (settings, the file written)."""
        settings = self.setup.collect()
        self.settings_file = save_settings(settings, self.setup.portable.isChecked())
        self.setup.saved_at.setText(f'Settings file: {self.settings_file}')
        return settings, self.settings_file

    def _tab_changed(self, index: int) -> None:
        """Refresh the Convert screen's stages, or load the Replacements screen, when it is shown."""
        if self.tabs.widget(index) is self.convert:
            self.convert.refresh(self.setup.collect())
        elif self.tabs.widget(index) is self.replacements:
            self.replacements.activate(self.setup.collect())

    def _finished(self, results: list, warnings: list, made_zip: str) -> None:
        """Show the run's outcome on the Finished screen."""
        settings = self.setup.collect()
        self.finished.show_outcome(results, warnings, S.output_dir(settings, settings['source']), made_zip)
        self.tabs.setCurrentWidget(self.finished)


def first_settings() -> 'tuple | None':
    """(settings, file) saved; the first-run wizard's when none are saved yet, None if it is cancelled."""
    path = S.settings_path()
    if path.is_file():
        return S.load(path), path
    wizard = FirstRunWizard()
    if wizard.exec() != QDialog.DialogCode.Accepted:
        return None
    settings, portable = wizard.result_settings()
    return settings, save_settings(settings, portable)


def main() -> int:
    """Start the app; its exit code."""
    surface_format()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(TITLE)
    started = first_settings()
    if started is None:
        return 0
    window = MainWindow(*started)
    window.show()
    return app.exec()
