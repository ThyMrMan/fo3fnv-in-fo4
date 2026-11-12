"""The Convert screen's "What to convert" box: the game, a DLC found in its Data folder, or a mod folder the user
adds, where an add-on builds and whether it builds as a light plugin (fo4_import.app.light_plugins). Choices are
written into the settings (fo4_import.app.addons).

See: docs/fork/fo4_gui.md#addons
See: docs/fork/fo4_gui.md#light
"""

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QWidget)

from fo4_import.app import addons, light_plugins, stages
from fo4_import.app import settings as S
from fo4_import.app.widgets import PathRow


class TargetBox(QGroupBox):
    """The target choice and an add-on's output folder; `on_change()` runs after the user changes the target."""

    def __init__(self, on_change, parent=None):
        """The box; `on_change` refreshes the screen."""
        super().__init__('What to convert', parent)
        self.on_change, self.settings = on_change, None
        self.choice, self.output = QComboBox(), PathRow()
        self.light, self.light_notes = QCheckBox('Build as a light plugin (ESL flag; takes no full plugin slot)'), QLabel()
        self.light_notes.setWordWrap(True)
        self.light_notes.setStyleSheet('color: gray')
        self.light.clicked.connect(self._light_clicked)
        add_mod = QPushButton('Add a mod folder...')
        add_mod.clicked.connect(self._add_mod)
        self.choice.activated.connect(self._chosen)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.choice, 1)
        row.addWidget(add_mod)
        holder = QWidget()
        holder.setLayout(row)
        form = QFormLayout(self)
        form.addRow('Convert', holder)
        form.addRow('Output folder', self.output)
        form.addRow('Plugin type', self.light)
        form.addRow('', self.light_notes)

    def show_settings(self, settings: dict) -> None:
        """List the game, its DLC and its added mods for the chosen source game, the current target selected."""
        self.settings = settings
        source = settings['source']
        master, block = stages.GAMES[source]['master'], settings['per_source'][source]
        game = S.game_dir(settings, source)
        found = addons.dlc(game / 'Data', master) if game else []
        mods = [e for e in addons.entries(settings, source) if e['mod']]
        self.choice.clear()
        self.choice.addItem(f'{master} (the game)', '')
        for name in found:
            self.choice.addItem(f'{name} (DLC)', name)
        for e in mods:
            self.choice.addItem(f"{e['plugin']} (mod: {Path(e['mod']).name})", e['plugin'])
        index = self.choice.findData(block.get('target', ''))
        self.choice.setCurrentIndex(max(index, 0))
        self._show_output()

    def _show_output(self) -> None:
        """The chosen add-on's output folder (the game's is set on the Setup screen)."""
        source, plugin = self.settings['source'], self.choice.currentData()
        self.output.setEnabled(bool(plugin))
        default = addons.default_output(self.settings, source, plugin) if plugin else 'set on the Setup screen'
        self.output.edit.setPlaceholderText(str(default))
        chosen = addons.entry(self.settings, source, plugin) if plugin else None
        self.output.set_text((chosen or {}).get('output', ''))
        self._show_light()

    def _show_light(self) -> None:
        """The chosen add-on's light opt-in and its warnings (the game is always full)."""
        source, plugin = self.settings['source'], self.choice.currentData()
        self.light.setEnabled(bool(plugin))
        self.light.setChecked(bool(plugin) and light_plugins.chosen(self.settings, source, plugin))
        notes = light_plugins.warnings(stages.export_dir(self.settings, source), stages.plugin_path(
            self.settings, source)) if plugin else ['The game is always a full plugin']
        self.light_notes.setText('\n'.join(notes))

    def _light_clicked(self, light: bool) -> None:
        """Record the opt-in; switching an already built add-on's type asks first, since saves using it break."""
        source, plugin = self.settings['source'], self.choice.currentData()
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
        source, plugin = self.settings['source'], self.choice.currentData() or ''
        self.settings['per_source'][source]['target'] = plugin
        if plugin:
            addons.add(self.settings, source, plugin)['output'] = self.output.text()

    def _chosen(self) -> None:
        """The user picked a target: record it and refresh."""
        source = self.settings['source']
        plugin = self.choice.currentData() or ''
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
