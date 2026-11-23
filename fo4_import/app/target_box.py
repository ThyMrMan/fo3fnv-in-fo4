"""The Convert screen's "What to convert" list: the game, the DLC found in its Data folder, and the mod folders the
user adds, each with whether it is built (stages.row_state); for an add-on, where it builds and whether it builds
as a light plugin (fo4_import.app.light_plugins). Choices are written into the settings (fo4_import.app.addons).

See: docs/fork/fo4_gui.md#convert-screen
See: docs/fork/fo4_gui.md#light
"""

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from fo4_import.app import addons, light_plugins, stages
from fo4_import.app import settings as S
from fo4_import.app.widgets import PathRow

#: The tooltip of the add-mod button.
ADD_MOD_TIP = ('A mod made for the chosen game: pick the folder holding its .esm or .esp (unpacked, or in your old '
               'mod manager). It converts on top of the game, into a folder of its own.')


class TargetBox(QGroupBox):
    """The target list and an add-on's output folder; `on_change()` runs after the user changes the target."""

    def __init__(self, on_change, parent=None):
        """The box; `on_change` refreshes the screen."""
        super().__init__('2. What to convert', parent)
        self.on_change, self.settings = on_change, None
        self.choice, self.output = QListWidget(), PathRow()
        self.choice.setMinimumHeight(110)
        self.choice.setMaximumHeight(150)
        self.light, self.light_notes = QCheckBox('Build as a light plugin (ESL flag; takes no full plugin slot)'), QLabel()
        self.light_notes.setWordWrap(True)
        self.light_notes.setStyleSheet('color: gray')
        self.light.clicked.connect(self._light_clicked)
        add_mod = QPushButton('Add a mod folder...')
        add_mod.setToolTip(ADD_MOD_TIP)
        add_mod.clicked.connect(self._add_mod)
        self.choice.itemClicked.connect(self._chosen)
        hint = QLabel('Convert the game first; its DLC and mods build on it, each into its own folder.')
        hint.setStyleSheet('color: gray')
        side = QVBoxLayout()
        side.addWidget(add_mod)
        side.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.choice, 1)
        row.addLayout(side)
        self.addon = QWidget()
        form = QFormLayout(self.addon)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow('Output folder', self.output)
        form.addRow('Plugin type', self.light)
        form.addRow('', self.light_notes)
        box = QVBoxLayout(self)
        box.addWidget(hint)
        box.addLayout(row)
        box.addWidget(self.addon)

    def show_settings(self, settings: dict) -> None:
        """List the chosen game, its DLC and its added mods, each with its state, the current target selected."""
        self.settings = settings
        source = settings['source']
        master, block = stages.GAMES[source]['master'], settings['per_source'][source]
        game = S.game_dir(settings, source)
        rows = [('', f'{master}: the game')]
        rows += [(name, f'{name}: DLC') for name in (addons.dlc(game / 'Data', master) if game else [])]
        rows += [(e['plugin'], f"{e['plugin']}: mod ({Path(e['mod']).name})")
                 for e in addons.entries(settings, source) if e['mod']]
        self.choice.clear()
        for plugin, text in rows:
            item = QListWidgetItem(f'{text}  —  {stages.row_state(settings, source, plugin)}')
            item.setData(Qt.ItemDataRole.UserRole, plugin)
            self.choice.addItem(item)
        chosen = next((i for i, (plugin, _) in enumerate(rows) if plugin == block.get('target', '')), 0)
        self.choice.setCurrentRow(chosen)
        self._show_output()

    def current(self) -> str:
        """The chosen row's plugin ('' the game)."""
        item = self.choice.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ''

    def _show_output(self) -> None:
        """The chosen add-on's output folder and light opt-in (the game's output is set on the Setup screen)."""
        source, plugin = self.settings['source'], self.current()
        self.addon.setVisible(bool(plugin))
        if not plugin:
            return
        self.output.edit.setPlaceholderText(str(addons.default_output(self.settings, source, plugin)))
        self.output.set_text((addons.entry(self.settings, source, plugin) or {}).get('output', ''))
        self.light.setChecked(light_plugins.chosen(self.settings, source, plugin))
        self.light_notes.setText('\n'.join(light_plugins.warnings(stages.export_dir(self.settings, source),
                                                                   stages.plugin_path(self.settings, source))))

    def _light_clicked(self, light: bool) -> None:
        """Record the opt-in; switching an already built add-on's type asks first, since saves using it break."""
        source, plugin = self.settings['source'], self.current()
        built = stages.plugin_path(self.settings, source)
        switch = light_plugins.needs_confirming(built, light)
        if switch:
            asked = QMessageBox.warning(
                self, 'This breaks saves', f'{plugin} is already built as a {"full" if light else "light"} plugin. '
                f'Building it {"light" if light else "full"} moves {light_plugins.own_count(built):,} FormIDs: saves '
                'that use this mod break, and mods built on it must be rebuilt. Switch?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if asked != QMessageBox.StandardButton.Yes:
                self.light.setChecked(not light)
                return
        light_plugins.choose(self.settings, source, plugin, light, switch)

    def write(self) -> None:
        """Write the chosen target and the add-on's output folder into the settings."""
        if self.settings is None:
            return
        source, plugin = self.settings['source'], self.current()
        self.settings['per_source'][source]['target'] = plugin
        if plugin:
            addons.add(self.settings, source, plugin)['output'] = self.output.text()

    def _chosen(self) -> None:
        """The user picked a target: record it and refresh."""
        source, plugin = self.settings['source'], self.current()
        if plugin:
            addons.add(self.settings, source, plugin)
        self.settings['per_source'][source]['target'] = plugin
        self._show_output()
        self.on_change()

    def _add_mod(self) -> None:
        """Pick a mod folder and the plugin in it to convert; it becomes the target."""
        folder = QFileDialog.getExistingDirectory(self, 'Choose a mod folder')
        plugins = [p.name for p in addons.mod_plugins(Path(folder))] if folder else []
        if folder and not plugins:
            QMessageBox.information(self, 'No plugin', f'{folder} holds no .esm or .esp plugin.')
        if not plugins:
            return
        plugin, ok = (plugins[0], True) if len(plugins) == 1 else \
            QInputDialog.getItem(self, 'Which plugin', 'This mod has several plugins; convert:', plugins, 0, False)
        if ok:
            addons.add(self.settings, self.settings['source'], plugin, folder)
            self.settings['per_source'][self.settings['source']]['target'] = plugin
            self.show_settings(self.settings)
            self.on_change()
