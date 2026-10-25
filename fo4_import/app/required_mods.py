"""Required mods: every plugin other than Fallout4.esm that the replacement table names, and whether it can be used.

The build adds each such plugin as a master of the converted plugin, and an entry whose plugin is not installed (or
names a master that is not) falls back to the layer below. survey() says, per plugin: how many entries name it,
where it was found, which MO2 mod folders hold it without the profile enabling them, and which of its own masters
are missing. RequiredModsDialog shows that list.

See: docs/fork/fo4_gui.md#required-mods
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPlainTextEdit,
                               QTableWidget, QVBoxLayout)

from core.mod_sources import PLUGIN_SUFFIXES, find_file, mo2_folders, mo2_layout
from fo4_import.app.replacement_columns import fill
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.spike import replacements as RP

PROBLEM = QColor(200, 40, 40)
HEADERS = ['Plugin', 'Entries', 'Status', 'Where', 'Missing masters']
RULE_KINDS = ('creature', 'body', 'melee')


# ---------------------------------------------------------------------------
#  The survey
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Disabled:
    """A plugin's file in an MO2 mod folder that the profile does not enable."""
    mod: str
    profile: str
    path: Path


@dataclass(frozen=True)
class RequiredMod:
    """One named plugin: entries naming it, loadable or not, its file among the sources, its files in MO2 mods the
    profile leaves off (Disabled), and its masters that are not loadable [(name, (Disabled, ...))]."""
    plugin: str
    entries: int
    installed: bool
    path: 'Path | None' = None
    disabled: tuple = ()
    missing_masters: tuple = ()

    @property
    def status(self) -> str:
        """'ready', 'missing masters', 'not enabled' or 'not installed'."""
        if self.installed:
            return 'ready'
        if self.path or (self.disabled and self.missing_masters):
            return 'missing masters'
        return 'not enabled' if self.disabled else 'not installed'


def named(layers: list) -> dict:
    """{lowercase plugin: (its name as written, {entry key})} of every non-base plugin the layers name, entries in
    any layer counted once; a plugin only a profile's `requires` names has no entries."""
    out = {}
    for data, _ in layers:
        for where, key, spec in _specs(data):
            plugin = spec['use'].partition('|')[0]
            if plugin.lower() != RP.BASE.lower():
                out.setdefault(plugin.lower(), (plugin, set()))[1].add((where, key))
        for req in data.get('_profile', {}).get('requires', ()):
            out.setdefault(req['plugin'].lower(), (req['plugin'], set()))
    return out


def _specs(data: dict):
    """(where, key, spec) of every entry in one layer: categories, then rules."""
    for category in RP.CATEGORIES:
        for key, spec in data.get(category, {}).items():
            yield category, key, spec
    rules = data.get('_rules', {})
    for kind in RULE_KINDS:
        for key, spec in rules.get(kind, {}).items():
            yield f'rule {kind}', key, spec
    for rule in rules.get('armor', ()):
        yield 'rule armor', ','.join(rule['covers']), rule


def disabled_index(sources: list) -> dict:
    """{lowercase plugin: [Disabled]} over the MO2 sources' mod folders that their profile does not enable."""
    out = {}
    for source in (s for s in sources if s.kind == 'mo2_profile'):
        general, folders = mo2_layout(source.folder)
        enabled, profile = set(mo2_folders(source.folder, source.profile)), source.profile or \
            general.get('selected_profile', '')
        mods = sorted(folders['mods'].iterdir(), key=lambda p: p.name.casefold()) if folders['mods'].is_dir() else []
        for mod in (m for m in mods if m.is_dir() and m not in enabled):
            for path in mod.iterdir():
                if path.suffix.lower() in PLUGIN_SUFFIXES and path.is_file():
                    out.setdefault(path.name.lower(), []).append(Disabled(mod.name, profile, path))
    return out


def survey(layers: list, dirs: list, sources: list) -> list:
    """[RequiredMod] for every non-base plugin `layers` name, plugins looked for as the loader does (the game's
    Data, then `dirs`); problems first, then the most entries."""
    present, off, roots = RP.presence(tuple(dirs)), disabled_index(sources), [FALLOUT4_DIR / 'Data', *dirs]
    out = []
    for key, (plugin, keys) in named(layers).items():
        path, disabled = find_file(plugin, roots), tuple(off.get(key, ()))
        file = path or (disabled[0].path if disabled else None)
        missing = tuple((m, tuple(off.get(m.lower(), ()))) for m in (RP.file_masters(file) if file else ())
                        if not present(m))
        out.append(RequiredMod(plugin, len(keys), present(plugin), path, disabled, missing))
    return sorted(out, key=lambda m: (m.installed, -m.entries, m.plugin.lower()))


# ---------------------------------------------------------------------------
#  Rows and summary
# ---------------------------------------------------------------------------

def _off_text(disabled: tuple) -> str:
    """Each MO2 mod holding the plugin unenabled, with its profile, joined."""
    return '; '.join(f'MO2 mod "{d.mod}" (not enabled in profile {d.profile or "?"})' for d in disabled)


def row(mod: RequiredMod) -> tuple:
    """(cells, problem?) of one plugin for HEADERS."""
    status = {'ready': 'Ready', 'not installed': 'Not installed: its entries fall back',
              'not enabled': 'Not enabled: its entries fall back',
              'missing masters': 'Missing masters: its entries fall back'}[mod.status]
    where = f'{mod.path.parent.name} ({mod.path.parent})' if mod.path else _off_text(mod.disabled) or 'not found'
    masters = '; '.join(f'{name} ({_off_text(off)})' if off else name for name, off in mod.missing_masters)
    return (mod.plugin, mod.entries, status, where, masters), not mod.installed


def summary(mods: list) -> str:
    """One line: how many plugins the table names, how many can't be used now and how many entries fall back."""
    broken = [m for m in mods if not m.installed]
    if not broken:
        return f'Your replacement table names {len(mods)} plugins besides Fallout4.esm; all are installed.'
    return (f'Your replacement table names {len(mods)} plugins besides Fallout4.esm; the build makes each a master '
            f'of the converted plugin. {len(broken)} cannot be used now, so their {sum(m.entries for m in broken)} '
            'entries fall back to the layer below. Enable the listed MO2 mods in the profile, or install the '
            'missing ones and their masters.')


def button_text(mods: list) -> str:
    """The screen's button label: 'Required mods (N to fix)' or 'Required mods'."""
    broken = sum(1 for m in mods if not m.installed)
    return f'Required mods ({broken} to fix)' if broken else 'Required mods'


# ---------------------------------------------------------------------------
#  The dialog
# ---------------------------------------------------------------------------

class RequiredModsDialog(QDialog):
    """The required-mods list for `mods` [RequiredMod], problems in red, and the loader's `warnings` under it."""

    def __init__(self, mods: list, warnings: list, parent=None):
        """A dialog listing `mods` with the summary and `warnings`."""
        super().__init__(parent)
        self.setWindowTitle('Required mods')
        self.resize(1100, 600)
        text, self.table, self.warnings = QLabel(summary(mods)), QTableWidget(0, len(HEADERS)), QPlainTextEdit()
        text.setWordWrap(True)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        fill(self.table, [(cells, PROBLEM if bad else None) for cells, bad in map(row, mods)])
        self.warnings.setReadOnly(True)
        self.warnings.setPlainText('\n'.join(dict.fromkeys(warnings)) or 'None.')
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        for widget, stretch in ((text, 0), (self.table, 3), (QLabel('Loader warnings'), 0), (self.warnings, 1),
                                (close, 0)):
            box.addWidget(widget, stretch)
