"""The first-run wizard: the game, the game folders, mods (none, an MO2 instance, or any folder of mods) and where
files go, saved as the app's settings. The Setup screen edits the same settings later.

See: docs/fork/fo4_gui.md#choices
"""

from pathlib import Path

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QLabel, QRadioButton, QVBoxLayout,
                               QWizard, QWizardPage)

from core.mod_sources import mo2_profiles
from fo4_import.app import settings as S
from fo4_import.app.setup_view import GAME_LABELS, OUTPUT_LABELS, PLACE_LABELS, SOURCE_LABELS
from fo4_import.app.stages import GAMES
from fo4_import.app.widgets import PathRow

MOD_CHOICES = (('none', 'No mods: Fallout 4 and its DLC only'), ('mo2', 'A Mod Organizer 2 instance'),
               ('folder', 'A folder of mods (Vortex staging, or any folder with one folder per mod)'))


def _radios(page: QWizardPage, choices, layout) -> QButtonGroup:
    """Radio buttons for `choices` [(value, label)] on `page`, the first checked; their group."""
    group = QButtonGroup(page)
    for i, (value, label) in enumerate(choices):
        radio = QRadioButton(label)
        radio.setProperty('value', value)
        radio.setChecked(i == 0)
        group.addButton(radio)
        layout.addWidget(radio)
    return group


def _detected_row(game: str) -> PathRow:
    """A game folder row with the detected folder filled in."""
    found = S.game_dir(S.defaults(), game)
    row = PathRow('not found: choose the game folder')
    row.set_text(str(found) if found else '', 'detected' if found else 'not detected')
    return row


class FirstRunWizard(QWizard):
    """Collects the first settings; result() gives (settings, keep beside the app)."""

    def __init__(self, parent=None):
        """The wizard's pages."""
        super().__init__(parent)
        self.setWindowTitle('Set up the FO3/FNV to Fallout 4 converter')
        self.games = {game: _detected_row(game) for game in GAME_LABELS}
        self.mo2, self.profile, self.mod_folder = PathRow(), QComboBox(), PathRow()
        self.mo2.edit.textChanged.connect(self._profiles)
        self.output, self.output_kind, self.place = PathRow(str(S.default_output_dir(S.defaults(), 'falloutnv'))), \
            QComboBox(), QComboBox()
        for box, labels in ((self.output_kind, OUTPUT_LABELS), (self.place, PLACE_LABELS)):
            for value, text in labels.items():
                box.addItem(text, value)
        self.work, self.portable = PathRow(str(S.work_dir(S.defaults()))), QCheckBox('Keep the settings beside the app')
        self.source_group = self._page('Which game?', 'Pick the game to convert to Fallout 4.',
                                       lambda layout: _radios(self, list(SOURCE_LABELS.items()), layout))
        self._form_page('Game folders', 'The folders holding each game (the one with Data inside).',
                        [(GAME_LABELS[g], row) for g, row in self.games.items()])
        self.mod_group = self._page('Mods', 'Replacements can come from mods you have installed. A mod manager is '
                                    'optional.', lambda layout: _radios(self, MOD_CHOICES, layout))
        self._form_page('Where mods are', 'Fill in the one you picked.', [
            ('MO2 instance folder', self.mo2), ('MO2 profile', self.profile), ('Folder of mods', self.mod_folder)])
        self._form_page('Where files go', 'Every location can be changed later on the Setup screen.', [
            ('Converted files', self.output), ('Output as', self.output_kind), ('Replacement file', self.place),
            ('Work folder (scripts, caches)', self.work), ('', self.portable)])

    def _page(self, title: str, text: str, fill) -> object:
        """Add a page of `text` that `fill(layout)` fills; what fill returns."""
        page, layout = QWizardPage(), QVBoxLayout()
        page.setTitle(title)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        made = fill(layout)
        page.setLayout(layout)
        self.addPage(page)
        return made

    def _form_page(self, title: str, text: str, rows: list) -> None:
        """Add a page of `text` and labeled `rows`."""
        def fill(layout):
            """The rows as a form."""
            form = QFormLayout()
            for label, widget in rows:
                form.addRow(label, widget)
            layout.addLayout(form)
        self._page(title, text, fill)

    def _profiles(self) -> None:
        """List the MO2 instance's profiles once its folder is typed or picked."""
        self.profile.clear()
        self.profile.addItems(mo2_profiles(Path(self.mo2.text())) if self.mo2.text() else [])

    def validateCurrentPage(self) -> bool:
        """Refuse to leave the folders page while a needed game folder lacks its master file."""
        if self.currentId() == 1:
            source = self.source_group.checkedButton().property('value')
            for game, master in (('fallout4', 'Fallout4.esm'), (source, GAMES[source]['master'])):
                if not (Path(self.games[game].text()) / 'Data' / master).is_file():
                    self.games[game].set_text(self.games[game].text(), f'no Data/{master} in this folder')
                    return False
        return super().validateCurrentPage()

    def result_settings(self) -> tuple:
        """(the settings the wizard collected, whether to keep them beside the app)."""
        made = S.defaults()
        source = self.source_group.checkedButton().property('value')
        made['source'] = source
        made['games'] = {game: row.text() for game, row in self.games.items()}
        made['mod_sources'] = self._mod_sources()
        made['work_dir'] = self.work.text()
        block = made['per_source'][source]
        block['output'] = {'kind': self.output_kind.currentData(), 'path': self.output.text()}
        block['replacements']['where'] = self.place.currentData()
        return made, self.portable.isChecked()

    def _mod_sources(self) -> list:
        """The settings' mod sources for the mods choice."""
        choice = self.mod_group.checkedButton().property('value')
        if choice == 'mo2' and self.mo2.text():
            return [{'folder': self.mo2.text(), 'kind': 'mo2_profile', 'profile': self.profile.currentText(),
                     'enabled': True}]
        if choice == 'folder' and self.mod_folder.text():
            return [{'folder': self.mod_folder.text(), 'kind': 'folder_of_mods', 'profile': '', 'enabled': True}]
        return []
