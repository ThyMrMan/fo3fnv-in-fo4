"""Widgets the app's screens share: a path row with a Browse button, and the mod sources table.

See: docs/fork/fo4_gui.md#choices
"""

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QVBoxLayout, QWidget)

from core.mod_sources import KINDS, mo2_profiles

#: Mod source kinds as the table shows them.
KIND_LABELS = {'folder_of_mods': 'Folder of mods (one folder per mod)', 'flat': 'One Data-like folder',
               'mo2_profile': 'Mod Organizer 2 instance'}
FOLDER, KIND, PROFILE, ENABLED = range(4)


class PathRow(QWidget):
    """A path field with Browse (a folder, or a file when `file_filter` is given) and a hint under it."""

    def __init__(self, placeholder: str = '', file_filter: str = '', parent=None):
        """A row whose empty field shows `placeholder` (what is used when it is left empty)."""
        super().__init__(parent)
        self.file_filter = file_filter
        self.edit, self.hint = QLineEdit(), QLabel()
        self.edit.setPlaceholderText(placeholder)
        self.hint.setStyleSheet('color: gray')
        self.hint.setWordWrap(True)
        browse = QPushButton('Browse...')
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(row)
        box.addWidget(self.hint)
        self.hint.hide()

    def _browse(self) -> None:
        """Let the user pick the folder or file."""
        start = self.edit.text() or self.edit.placeholderText()
        chosen = QFileDialog.getSaveFileName(self, 'Choose a file', start, self.file_filter)[0] if self.file_filter \
            else QFileDialog.getExistingDirectory(self, 'Choose a folder', start)
        if chosen:
            self.edit.setText(chosen)

    def text(self) -> str:
        """The path typed or picked ('' when empty)."""
        return self.edit.text().strip()

    def set_text(self, text: str, hint: str = '') -> None:
        """Show `text`, and `hint` under it when given."""
        self.edit.setText(text)
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))


class ModSourcesTable(QWidget):
    """The ordered mod sources: folder, kind, MO2 profile, enabled; later rows win."""

    def __init__(self, parent=None):
        """An empty table with Add, Remove and Move buttons."""
        super().__init__(parent)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Folder', 'Kind', 'MO2 profile', 'Use'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(FOLDER, QHeaderView.ResizeMode.Stretch)
        for column in (KIND, PROFILE, ENABLED):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        buttons = QHBoxLayout()
        for label, action in (('+ Mods folder', 'folder_of_mods'), ('+ Data folder', 'flat'),
                              ('+ MO2 instance', 'mo2_profile')):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, kind=action: self._add(kind))
            buttons.addWidget(button)
        for label, step in (('Up', -1), ('Down', 1)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, s=step: self._move(s))
            buttons.addWidget(button)
        remove = QPushButton('Remove')
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        buttons.addWidget(remove)
        note = QLabel('Lower rows win over higher ones. MO2 is optional: any folder of mods works.')
        note.setStyleSheet('color: gray')
        note.setWordWrap(True)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.table)
        box.addLayout(buttons)
        box.addWidget(note)

    def _add(self, kind: str) -> None:
        """Pick a folder and add it as a source of `kind`."""
        folder = QFileDialog.getExistingDirectory(self, KIND_LABELS[kind])
        if folder:
            self.add_row({'folder': folder, 'kind': kind, 'profile': '', 'enabled': True})

    def add_row(self, entry: dict) -> None:
        """Append one settings entry ({folder, kind, profile, enabled})."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, FOLDER, QLineEdit(entry['folder']))
        kind = QComboBox()
        for key in KINDS:
            kind.addItem(KIND_LABELS[key], key)
        kind.setCurrentIndex(KINDS.index(entry['kind']))
        self.table.setCellWidget(row, KIND, kind)
        profile = QComboBox()
        profiles = mo2_profiles(entry['folder']) if entry['kind'] == 'mo2_profile' else []
        profile.addItems(['(selected in MO2)', *profiles] if profiles else ['-'])
        if entry.get('profile') in profiles:
            profile.setCurrentText(entry['profile'])
        self.table.setCellWidget(row, PROFILE, profile)
        use = QCheckBox()
        use.setChecked(entry.get('enabled', True))
        self.table.setCellWidget(row, ENABLED, use)

    def _move(self, step: int) -> None:
        """Move the current row up or down."""
        row, entries = self.table.currentRow(), self.entries()
        target = row + step
        if 0 <= row < len(entries) and 0 <= target < len(entries):
            entries[row], entries[target] = entries[target], entries[row]
            self.set_entries(entries)
            self.table.setCurrentCell(target, FOLDER)

    def entries(self) -> list:
        """The rows as settings entries."""
        out = []
        for row in range(self.table.rowCount()):
            profile = self.table.cellWidget(row, PROFILE).currentText()
            out.append({'folder': self.table.cellWidget(row, FOLDER).text().strip(),
                        'kind': self.table.cellWidget(row, KIND).currentData(),
                        'profile': '' if profile in ('-', '(selected in MO2)') else profile,
                        'enabled': self.table.cellWidget(row, ENABLED).isChecked()})
        return out

    def set_entries(self, entries: list) -> None:
        """Show `entries` (settings `mod_sources`)."""
        self.table.setRowCount(0)
        for entry in entries:
            self.add_row(entry)
