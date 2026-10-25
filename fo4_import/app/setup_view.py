"""The Setup screen: every choice in the app's settings, each with its detected or default value shown.

Per source game (FNV, FO3) it keeps its own output, replacement file and profile; switching the source shows
that game's. collect() writes the fields back into the settings dict.

See: docs/fork/fo4_gui.md#choices
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QScrollArea,
                               QVBoxLayout, QWidget)

from fo4_import.app import settings as S
from fo4_import.app.stages import GAMES
from fo4_import.app.widgets import ModSourcesTable, PathRow

GAME_LABELS = {'fallout4': 'Fallout 4', 'falloutnv': 'Fallout: New Vegas', 'fallout3': 'Fallout 3'}
SOURCE_LABELS = {source: GAME_LABELS[source] + ('' if game['built'] else ' (build not supported yet)')
                 for source, game in GAMES.items()}
OUTPUT_LABELS = {'folder': 'A folder of loose files', 'zip': 'A zip of that folder'}
PLACE_LABELS = {'app': 'Beside the app', 'output': 'In the output folder', 'custom': 'A path I choose'}


def _combo(labels: dict) -> QComboBox:
    """A combo box of `labels` {value: text}, the value as item data."""
    box = QComboBox()
    for value, text in labels.items():
        box.addItem(text, value)
    return box


class SetupView(QWidget):
    """Edits a settings dict (fo4_import.app.settings) in place."""

    def __init__(self, parent=None):
        """An empty Setup screen; load() fills it."""
        super().__init__(parent)
        self.settings, self.shown_source = S.defaults(), 'falloutnv'
        self.source = _combo(SOURCE_LABELS)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.games = {game: PathRow() for game in GAME_LABELS}
        self.mods = ModSourcesTable()
        self.output_kind, self.output = _combo(OUTPUT_LABELS), PathRow()
        self.place, self.replacements = _combo(PLACE_LABELS), PathRow(file_filter='JSON (*.json)')
        self.scripts = PathRow()
        self.scripts.setToolTip("Where converted scripts go. Point it at an earlier run's folder (for example the "
                                "command line's temp/fo4_scripts/FalloutNV.esm) to reuse its scripts.")
        self.profile = QLineEdit()
        self.profile.setPlaceholderText('none (the converter defaults)')
        self.work, self.nifskope = PathRow(), PathRow(file_filter='NifSkope (*.exe);;All files (*)')
        self.portable = QCheckBox('Keep the settings beside the app (portable)')
        self.saved_at = QLabel()
        self.saved_at.setStyleSheet('color: gray')
        self.saved_at.setWordWrap(True)
        self._layout()

    def _layout(self) -> None:
        """Arrange the fields in groups inside a scroll area."""
        body = QWidget()
        box = QVBoxLayout(body)
        box.addWidget(self._group('Game', [('Convert from', self.source)]))
        box.addWidget(self._group('Game folders', [(GAME_LABELS[g], row) for g, row in self.games.items()]))
        mods = QGroupBox('Mods to pick replacements from')
        QVBoxLayout(mods).addWidget(self.mods)
        box.addWidget(mods)
        box.addWidget(self._group('This game\'s files', [
            ('Output', self.output_kind), ('Output folder', self.output), ('Scripts folder', self.scripts),
            ('Replacement file', self.place),
            ('Custom replacement file', self.replacements), ('Replacement profile', self.profile)]))
        box.addWidget(self._group('Other', [('Work folder (caches, default scripts)', self.work),
                                            ('NifSkope (optional)', self.nifskope), ('', self.portable),
                                            ('', self.saved_at)]))
        box.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        QVBoxLayout(self).addWidget(scroll)

    @staticmethod
    def _group(title: str, rows: list) -> QGroupBox:
        """A titled group of (label, widget) rows."""
        group = QGroupBox(title)
        form = QFormLayout(group)
        for label, widget in rows:
            form.addRow(label, widget)
        return group

    def load(self, settings: dict, saved_at: str, portable: bool) -> None:
        """Show `settings`, saved at `saved_at` (portable: beside the app)."""
        self.settings = settings
        for game, row in self.games.items():
            found = S.game_dir(S.defaults(), game)
            row.edit.setPlaceholderText(str(found) if found else 'not found: choose the game folder')
            row.set_text(settings['games'][game], f'detected: {found}' if found else '')
        self.mods.set_entries(settings['mod_sources'])
        self.work.edit.setPlaceholderText(str(S.work_dir(S.defaults())))
        self.work.set_text(settings['work_dir'])
        self.nifskope.set_text(settings['tools']['nifskope'])
        self.portable.setChecked(portable)
        self.saved_at.setText(f'Settings file: {saved_at}')
        self.shown_source = settings['source']
        self.source.blockSignals(True)
        self.source.setCurrentIndex(list(GAMES).index(settings['source']))
        self.source.blockSignals(False)
        self._show_source(settings['source'])

    def _show_source(self, source: str) -> None:
        """Fill the per-game fields from `source`'s block."""
        block = self.settings['per_source'][source]
        self.output_kind.setCurrentIndex(list(OUTPUT_LABELS).index(block['output']['kind']))
        self.output.edit.setPlaceholderText(str(S.default_output_dir(self.settings, source)))
        self.output.set_text(block['output']['path'])
        self.scripts.edit.setPlaceholderText(str(S.default_scripts_dir(self.settings, source)))
        self.scripts.set_text(block['scripts'])
        self.place.setCurrentIndex(list(PLACE_LABELS).index(block['replacements']['where']))
        self.replacements.set_text(block['replacements']['path'])
        self.profile.setText(block['profile'])

    def _source_changed(self) -> None:
        """Keep the shown game's fields, then show the newly chosen game's."""
        self._collect_source(self.shown_source)
        self.shown_source = self.source.currentData()
        self._show_source(self.shown_source)

    def _collect_source(self, source: str) -> None:
        """Write the per-game fields into `source`'s block."""
        block = self.settings['per_source'][source]
        block['output'] = {'kind': self.output_kind.currentData(), 'path': self.output.text()}
        block['replacements'] = {'where': self.place.currentData(), 'path': self.replacements.text()}
        block['scripts'] = self.scripts.text()
        block['profile'] = self.profile.text().strip()

    def collect(self) -> dict:
        """The settings with every field written back."""
        self._collect_source(self.shown_source)
        self.settings['source'] = self.source.currentData()
        self.settings['games'] = {game: row.text() for game, row in self.games.items()}
        self.settings['mod_sources'] = self.mods.entries()
        self.settings['work_dir'] = self.work.text()
        self.settings['tools']['nifskope'] = self.nifskope.text()
        return self.settings
