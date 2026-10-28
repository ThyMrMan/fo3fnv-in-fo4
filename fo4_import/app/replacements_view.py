"""The Replacements screen: pick what stands in for each source form from the installed plugins, in two columns.

Left, the source game's forms of a category (fo4_import.app.standins) with what stands in now and why; right, the
records of Fallout 4, its DLC or one installed plugin (fo4_import.app.catalog). Apply writes the pick to the user's
replacement file at the chosen place (fo4_import.app.user_table) and Revert drops it, so the profile or default
applies again; the next Build uses the file. Both columns preview in 3D: FNV's mesh as the last build converted
it, or the stand-in (a gun assembled from its default parts).

Match by name suggests a record per form (fo4_import.app.matching), shown in the Suggested column with "1 of N"
when others matched. Picking a form with a suggestion lists its candidates on the right, the suggestion picked and
previewed; Browse all records (or choosing a plugin) lists the plugin's records instead. Enter applies the right
pick and moves on, Delete reverts. Accept all shown takes every suggestion the left list shows (after asking). Show
filters the left list: everything, the user's picks, rough FO4 stand-ins, unaccepted suggestions, profile, skipped.

See: docs/fork/fo4_gui.md#replacements-screen
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from core.mod_sources import ModSource, data_dirs, plugins
from fo4_import.app import catalog as C
from fo4_import.app import required_mods as RM
from fo4_import.app import settings as S
from fo4_import.app import standins as SI
from fo4_import.app import user_table
from fo4_import.app.files import Files
from fo4_import.app.matching import Matcher
from fo4_import.app.preview.assembly import assemble, entry_parts
from fo4_import.app.preview.materials import Materials
from fo4_import.app.replacement_columns import SourceColumn, TargetColumn, fill, stats_text
from fo4_import.app.stages import GAMES, export_dir
from fo4_import.nif.creature import PAIRS
from fo4_import.rig.table import rigs
from fo4_import.spike import replacements as RP
from fo4_import.spike.creatures import skeleton_folder
from script_convert.constants import FALLOUT4_HELPER_PLUGIN

CATEGORY_LABELS = {'weapon': 'Weapons', 'armor': 'Armor and clothing', 'consumable': 'Consumables', 'ammo': 'Ammo',
                   'misc': 'Misc items', 'creature': 'Creatures'}
SKIPPED = QColor(200, 40, 40)
#: The Show filter's choices: a Current.kind, 'all', or 'suggested' (an unaccepted suggestion).
SHOW = {'all': 'All', 'mine': 'Mine (my replacement file)', 'rough': 'Still on a rough FO4 stand-in',
        'suggested': 'Suggested, not yet accepted', 'profile': 'From the profile', 'skipped': 'Skipped (no stand-in)'}


# ---------------------------------------------------------------------------
#  The Show filter
# ---------------------------------------------------------------------------

def shown(choice: str, now, match) -> bool:
    """Whether a form whose stand-in is `now` (standins.Current) and suggestion `match` passes Show `choice`."""
    if choice == 'all':
        return True
    if choice == 'suggested':
        return match is not None and now.kind != 'mine'
    return now.kind == choice


# ---------------------------------------------------------------------------
#  The screen
# ---------------------------------------------------------------------------

class ReplacementsView(QWidget):
    """The two-column screen over the chosen game's export, the installed plugins and the user's file."""

    def __init__(self, parent=None):
        """An empty screen; activate() loads it."""
        super().__init__(parent)
        self.data, self.forms, self.targets, self.suggestions, self.following = None, [], [], {}, False
        self.category, self.search, self.show_filter = QComboBox(), QLineEdit(), QComboBox()
        for box, labels in ((self.category, CATEGORY_LABELS), (self.show_filter, SHOW)):
            for key, label in labels.items():
                box.addItem(label, key)
        self.search.setPlaceholderText('Search names and EditorIDs')
        self.match, self.required = QPushButton('Match by name'), QPushButton('Required mods')
        self.required.setToolTip('The plugins your replacement table names, and which are not enabled or are '
                                 'missing masters (their entries fall back).')
        self.left, self.right = SourceColumn(), TargetColumn()
        self.apply, self.revert, self.status = QPushButton('Apply'), QPushButton('Revert to default'), QLabel()
        self.accept_one, self.accept_all = QPushButton('Accept suggestion'), QPushButton('Accept all shown')
        self.status.setWordWrap(True)
        self._layout()
        self._connect()

    def _layout(self) -> None:
        """Top bar, the two columns side by side, the buttons under them."""
        top, bottom = QHBoxLayout(), QHBoxLayout()
        for widget in (QLabel('Category'), self.category, self.search, QLabel('Show'), self.show_filter, self.match,
                       self.required):
            top.addWidget(widget)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.left)
        split.addWidget(self.right)
        bottom.addWidget(self.status, 1)
        for button in (self.accept_one, self.accept_all, self.revert, self.apply):
            bottom.addWidget(button)
        box = QVBoxLayout(self)
        box.addLayout(top)
        box.addWidget(split, 1)
        box.addLayout(bottom)

    def _connect(self) -> None:
        """Wire the controls."""
        self.category.currentIndexChanged.connect(self._category_changed)
        self.search.textChanged.connect(self._show_forms)
        self.show_filter.currentIndexChanged.connect(self._show_forms)
        self.match.clicked.connect(self._match_by_name)
        self.required.clicked.connect(self._show_required)
        self.left.picked.connect(self._form_picked)
        self.right.picked.connect(self._target_picked)
        self.right.plugin.currentIndexChanged.connect(self._plugin_changed)
        self.right.search.textChanged.connect(self._show_targets)
        self.right.browse.toggled.connect(self._show_targets)
        self.apply.clicked.connect(self._apply)
        self.revert.clicked.connect(self._revert)
        self.accept_one.clicked.connect(self._accept_picked)
        self.accept_all.clicked.connect(self._accept_shown)
        keys = [(table, key, self._apply_and_next) for table in (self.left.table, self.right.table)
                for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)]
        for table, key, slot in [*keys, (self.left.table, Qt.Key.Key_Delete, self._revert)]:
            shortcut = QShortcut(QKeySequence(key), table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(slot)
        self.left.table.setToolTip('Up and Down move through the list; Enter applies the pick on the right and moves '
                                   'to the next form; Delete reverts the form to the profile or default.')

    # ---------------------------------------------------------------------------
    #  Loading
    # ---------------------------------------------------------------------------

    def activate(self, settings: dict) -> None:
        """Load (or reload, when the game, mods or output changed) for `settings`."""
        stamp = (settings['source'], repr(settings['mod_sources']), repr(settings['per_source']), repr(settings['games']))
        if self.data is None or self.data['stamp'] != stamp:
            self.status.setText('Loading the export and your plugins...')
            QApplication.processEvents()
            self.data, self.suggestions = load(settings), {}
            self.data['stamp'] = stamp
            self._fill_plugins()
            self._show_forms()
            self._show_targets()
            self._required_changed()
            self.status.setText(f"Replacement file: {self.data['user_path']}")

    def _fill_plugins(self) -> None:
        """Offer Fallout 4 + DLC, every installed plugin together, then each plugin alone."""
        combo = self.right.plugin
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('Fallout 4 + DLC', C.BASE_GAME)
        combo.addItem('All installed plugins', None)
        for name in sorted(self.data['found'], key=str.lower):
            combo.addItem(name, (name,))
        combo.blockSignals(False)

    def _required_changed(self) -> None:
        """Label the Required mods button with the count to fix, red when any."""
        self.required.setText(RM.button_text(self.data['required']))
        broken = any(not m.installed for m in self.data['required'])
        self.required.setStyleSheet(f'color: {RM.PROBLEM.name()}; font-weight: bold' if broken else '')

    def _show_required(self) -> None:
        """Open the required-mods list for the current table."""
        if self.data is not None:
            RM.RequiredModsDialog(self.data['required'], self.data['table'].warnings, self).exec()

    # ---------------------------------------------------------------------------
    #  Left: the source forms
    # ---------------------------------------------------------------------------

    def _category_changed(self) -> None:
        """Show the new category's forms and records."""
        self._show_forms()
        self._show_targets()

    def _show_forms(self) -> None:
        """Fill the left table with the category's forms, filtered."""
        if self.data is None:
            return
        wanted, data, category = self.search.text().strip().lower(), self.data, self.category.currentData()
        forms = SI.source_forms(data['export'], category, data['placed']) if data['export'] else []
        rows, self.forms = [], []
        for form in forms:
            now, match = SI.current(data['table'], form), self.suggestions.get((category, form.edid))
            if (wanted and wanted not in f'{form.name} {form.edid}'.lower()) or \
                    not shown(self.show_filter.currentData(), now, match):
                continue
            self.forms.append(form)
            tips = {5: '\n'.join([match.entry.use, *(['Also matched:'] if match.others else []),
                                  *(f'{o.name or o.edid} ({o.use})' for o in match.others)])} if match else {}
            rows.append(((form.name, form.edid, form.placed, now.entry.use if now.entry else '-', now.label,
                          match.label if match else ''), SKIPPED if now.how == 'none' else None, tips))
        fill(self.left.table, rows)
        if not data['export']:
            self.status.setText(f"No export of {GAMES[data['source']]['master']} yet: run Export on the Convert screen.")

    def _form(self):
        """The picked source form, or None."""
        row = self.left.table.currentRow()
        return self.forms[row] if 0 <= row < len(self.forms) else None

    def _match(self, form):
        """The suggestion for `form`, or None."""
        return self.suggestions.get((form.category, form.edid)) if form else None

    def _form_picked(self) -> None:
        """Preview and describe the picked form; on the right, its candidates or the modes the pick allows it."""
        form = self._form()
        if form is None:
            return
        data, now = self.data, SI.current(self.data['table'], self._form())
        target = data['index'].get((now.entry.plugin.lower(), now.entry.edid.lower())) if now.entry else None
        self.left.stats.setText(f'FNV: {stats_text(SI.stats(form)) or "-"}\n'
                                f'Stand-in: {stats_text(target.stats) if target else now.label}')
        if self.left.show_fnv():
            parts = assemble(data['files'], [SI.converted_mesh(form)])[0] if SI.converted_mesh(form) else []
            self._preview(self.left.preview, parts, "FNV's mesh is not in the output folder: a build converts it only "
                                                    "for forms shown on FNV's own mesh (mode fnv), and only once built.")
        elif target is None:
            self._preview(self.left.preview, [], f'No stand-in model to show ({now.label}).')
        else:
            parts, why = entry_parts(target, data['files'], data['known'])
            self._preview(self.left.preview, parts, f'No stand-in model to show: {why}.')
        if self.following or (self._match(form) and not self.right.browse.isChecked()):
            self._show_targets()
        else:
            self._target_picked()

    def _preview(self, preview, parts: list, empty: str) -> None:
        """Show `parts` with their surfaces in `preview`, or `empty`."""
        preview.show_parts(parts, [self.data['materials'].surface(p) for p in parts], empty)

    # ---------------------------------------------------------------------------
    #  Right: the records to pick from
    # ---------------------------------------------------------------------------

    def _show_targets(self) -> None:
        """Fill the right table, filtered: the picked form's candidates with the suggestion picked (unless browsing),
        else the chosen plugins' records of the category."""
        if self.data is None:
            return
        wanted, form = self.right.search.text().strip().lower(), self._form()
        match = self._match(form)
        self.following = match is not None and not self.right.browse.isChecked()
        if self.following:
            entries = [match.entry, *match.others]
            self.right.caption.setText(f'Suggested for {form.name or form.edid}: '
                                       + (f'{match.count} matches, the first picked' if match.others else '1 match'))
        else:
            entries = C.in_category(self.data['found'], self.category.currentData(), self.right.plugin.currentData())
            self.right.caption.setText('Browsing all records' if self.right.browse.isChecked() or form is None else
                                       f'No suggestion for {form.name or form.edid}: browsing all records')
        self.targets = [e for e in entries if not wanted or wanted in f'{e.name} {e.edid}'.lower()]
        fill(self.right.table, [((e.name, e.edid, e.plugin, stats_text(e.stats)), None) for e in self.targets])
        self.right.stats.clear()
        self.right.mode.clear()
        self.right.preview.say('Pick a record to preview it.')
        if self.following and self.targets:
            self.right.table.selectRow(0)

    def _plugin_changed(self) -> None:
        """Choosing a plugin means browsing it."""
        self.right.browse.blockSignals(True)
        self.right.browse.setChecked(True)
        self.right.browse.blockSignals(False)
        self._show_targets()

    def _target(self):
        """The picked record, or None."""
        row = self.right.table.currentRow()
        return self.targets[row] if 0 <= row < len(self.targets) else None

    def _target_picked(self) -> None:
        """Preview the picked record and offer the modes it allows."""
        target, form = self._target(), self._form()
        if target is None:
            return
        self.right.set_modes(allowed_modes(target, form))
        self.right.stats.setText(f'{target.use}\n{stats_text(target.stats) or "-"}')
        parts, why = entry_parts(target, self.data['files'], self.data['known'])
        self._preview(self.right.preview, parts, f'Nothing to show: {why}.')

    # ---------------------------------------------------------------------------
    #  Suggestions
    # ---------------------------------------------------------------------------

    def _match_by_name(self) -> None:
        """Suggest a record for every form of every category; show how many and switch Show to the suggestions."""
        if self.data is None or not self.data['export']:
            return
        self.suggestions = suggest_all(self.data)
        several = sum(1 for m in self.suggestions.values() if m.others)
        self.status.setText(f'{len(self.suggestions)} suggestions, {several} picked from several matches. Pick a '
                            'form to compare its suggestion on the right; Enter applies it and moves on.')
        self.right.browse.setChecked(False)
        self.show_filter.setCurrentIndex(list(SHOW).index('suggested'))
        self._show_forms()
        self.left.table.selectRow(0)
        self.left.table.setFocus()

    def _accept_picked(self) -> None:
        """Accept the picked form's suggestion."""
        form = self._form()
        match = self._match(form)
        if match is None:
            self.status.setText('The picked form has no suggestion: run Match by name first.')
            return
        self._accept([(form, match)])

    def _accept_shown(self) -> None:
        """Accept every suggestion the left list shows that is not already the user's pick, after asking."""
        table = self.data['table'] if self.data else None
        pairs = [(f, self.suggestions[(f.category, f.edid)]) for f in self.forms
                 if (f.category, f.edid) in self.suggestions and SI.current(table, f).kind != 'mine']
        if not pairs:
            self.status.setText('No suggestions shown to accept.')
            return
        asked = QMessageBox.question(self, 'Accept suggestions',
                                     f'Write {len(pairs)} suggestions into your replacement file?\n'
                                     f"{self.data['user_path']}\n\nEach can be reverted one by one afterwards.")
        if asked == QMessageBox.StandardButton.Yes:
            self._accept(pairs)

    def _accept(self, pairs: list) -> None:
        """Write [(form, match)] into the user's file as the records themselves."""
        user = user_table.read(self.data['user_path'])
        for form, match in pairs:
            user_table.set_entry(user, form.category, form.edid, match.entry.use, 'item')
        self._saved(user, f'{len(pairs)} suggestion(s) accepted' if len(pairs) > 1 else
                    f'{pairs[0][0].edid} now uses {pairs[0][1].entry.use}')

    # ---------------------------------------------------------------------------
    #  Apply and Revert
    # ---------------------------------------------------------------------------

    def _apply(self, advance: bool = False) -> None:
        """Write the pick for the picked form into the user's file; `advance` moves to the next form."""
        form, target = self._form(), self._target()
        if form is None or target is None:
            self.status.setText('Pick a form on the left and a record on the right first.')
            return
        user = user_table.read(self.data['user_path'])
        user_table.set_entry(user, form.category, form.edid, target.use, self.right.mode.currentData())
        self._saved(user, f'{form.edid} now uses {target.use}', advance)

    def _apply_and_next(self) -> None:
        """Apply the right pick and move to the next form (the Enter key)."""
        self._apply(advance=True)

    def _revert(self) -> None:
        """Drop the picked form's entry from the user's file."""
        form = self._form()
        if form is None:
            return
        user = user_table.read(self.data['user_path'])
        had = user_table.clear_entry(user, form.category, form.edid)
        self._saved(user, f'{form.edid} is back to the profile or default' if had else
                    f'{form.edid} had no entry of yours')

    def _saved(self, user: dict, what: str, advance: bool = False) -> None:
        """Write the user file, reload the table, pick the same row (or the next form's) and say what changed."""
        form, row = self._form(), self.left.table.currentRow()
        path = user_table.write(self.data['user_path'], user)
        self.data['table'] = load_table(self.data['settings'], self.data['dirs'])
        self.data['required'] = required(self.data['settings'], self.data['dirs'])
        self._required_changed()
        if self.suggestions:
            self.suggestions = suggest_all(self.data)
        self._show_forms()
        if advance and form in self.forms:
            row = self.forms.index(form) + 1
        self.left.table.selectRow(min(row, len(self.forms) - 1))
        self.left.table.setFocus()
        self.status.setText(f'{what}. Saved to {path}; the next Build on the Convert screen uses it.')


def allowed_modes(target, form) -> tuple:
    """The modes the loader accepts for `target` (FO4 records any; others, leveled lists, as they are): items any but
    `rig` and `speaker`; a creature FNV's mesh only where a rig pair exists for its skeleton folder, its own rig only
    where the rig table has it."""
    if target.plugin.lower() != RP.BASE.lower() or target.sig == 'LVLN':
        return ('item',)
    if target.category != 'creature':
        return tuple(m for m in RP.MODES if m not in ('rig', 'speaker'))
    folder = skeleton_folder(form.model) if form is not None else None
    return ('item', 'stats', 'speaker') + (('fnv',) if folder in PAIRS else ()) + (('rig',) if folder in rigs() else ())


def suggest_all(data: dict) -> dict:
    """{(category, source EditorID): matching.Match} for every category, against the current stand-ins."""
    out, order = {}, list(data['found'])
    for category in CATEGORY_LABELS:
        matcher = Matcher(C.in_category(data['found'], category), order)
        for form in SI.source_forms(data['export'], category, data['placed']):
            match = matcher.suggest(form, SI.current(data['table'], form).entry)
            if match:
                out[(category, form.edid)] = match
    return out


def table_layers(settings: dict) -> tuple:
    """(the user's replacement file or None, the profile or None) for the chosen game."""
    source = settings['source']
    user = S.replacement_file(settings, source)
    return user if user.is_file() else None, settings['per_source'][source]['profile'] or None


def load_table(settings: dict, dirs: list):
    """The chosen game's replacement table: defaults, profile, the user's file."""
    return RP.load(*table_layers(settings), tuple(dirs))


def required(settings: dict, dirs: list) -> list:
    """required_mods.survey() of the chosen game's table layers."""
    return RM.survey(RP.layers(*table_layers(settings)), dirs, S.mod_sources(settings))


def load(settings: dict) -> dict:
    """What the screen reads: export, placements, files (output first, for converted meshes), catalog, table."""
    source = settings['source']
    game, dirs = S.game_dir(settings, 'fallout4'), data_dirs(S.mod_sources(settings))
    fo4_data = [game / 'Data'] if game else []
    files = Files([S.output_dir(settings, source), *dirs, *fo4_data])
    sources = [*S.mod_sources(settings), *(ModSource(d, 'flat') for d in fo4_data)]
    ours = {GAMES[source]['plugin'].lower(), FALLOUT4_HELPER_PLUGIN.lower()}
    found = C.catalog({k: v for k, v in plugins(sources).items() if k not in ours}, files)
    export = export_dir(source)
    return {'settings': settings, 'source': source, 'dirs': dirs, 'files': files, 'found': found,
            'known': C.index(found), 'materials': Materials(files),
            'index': {(e.plugin.lower(), e.edid.lower()): e for entries in found.values() for e in entries},
            'export': export if export.is_dir() else None,
            'placed': SI.placements(export) if export.is_dir() else {},
            'table': load_table(settings, dirs), 'required': required(settings, dirs),
            'user_path': S.replacement_file(settings, source)}
