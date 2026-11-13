"""A DLC's or mod's "build as light" opt-in (an add-on entry's `light`), its lock and its warnings. No Qt here.

Full by default. The opt-in is chosen before the add-on's first build; once built, the other type moves every own
FormID, so the switch is passed to the build only after the user confirmed it (the entry's `light_confirmed`
names the type confirmed). The game itself is always full.

See: docs/fork/fo4_gui.md#light
"""

from pathlib import Path

from fo4_import.app import addons
from fo4_import.base.ledger import ID, LIGHT_SPAN, Ledger, ledger_path
from fo4_import.pipeline.export_index import export_masters, own_records
from fo4_import.pipeline.light_choice import built_light, own_ids

#: Own ids the app advises staying under, leaving a quarter of the light range for updates.
ROOMY = 3071


def chosen(settings: dict, source: str, plugin: str) -> bool:
    """Whether add-on `plugin` is opted in."""
    return bool((addons.entry(settings, source, plugin) or {}).get('light'))


def built_as(plugin: Path) -> 'bool | None':
    """Whether built `plugin` is light (True), full (False), or never built (None: no plugin and no ledger ids)."""
    ledger = Ledger(ledger_path(plugin))
    if not plugin.is_file() and not ledger.values(ID):
        return None
    return built_light(plugin, ledger)


def own_count(plugin: Path) -> int:
    """FormIDs a type switch of `plugin` moves: its own ids, else its ledger's."""
    return len(own_ids(plugin)) if plugin.is_file() else len(Ledger(ledger_path(plugin)).values(ID))


def needs_confirming(built: Path, light: bool) -> bool:
    """Whether `light` switches the type the add-on at `built` was built as."""
    before = built_as(built)
    return before is not None and before != light


def choose(settings: dict, source: str, plugin: str, light: bool, confirmed: bool = False) -> None:
    """Record `light` for `plugin`; `confirmed`: the user agreed to switch its built type (needs_confirming)."""
    entry = addons.add(settings, source, plugin)
    entry['light'] = light
    if confirmed:
        entry['light_confirmed'] = light


def arguments(settings: dict, source: str, plugin: str, built: Path) -> list:
    """fo4_import.pipeline.run's light arguments for add-on `plugin` built at `built`."""
    entry = addons.entry(settings, source, plugin) or {}
    light = bool(entry.get('light'))
    args = ['--light'] if light else []
    before = built_as(built)
    if before is not None and before != light and entry.get('light_confirmed') == light:
        args.append('--switch-plugin-type')
    return args


def warnings(export_dir: Path, built: Path) -> list:
    """The light-only problems of the add-on exported in `export_dir` (built at `built`), as lines to show.
    See: docs/fork/research/fo4_light_plugins.md#problems
    """
    out = []
    if built.is_file() or Ledger(ledger_path(built)).values(ID):
        count = own_count(built)
        room = 'fits' if count <= ROOMY else 'fits, with little room for updates' if count <= LIGHT_SPAN else \
            'does not fit'
        out.append(f'{count:,} own records of {LIGHT_SPAN:,}: {room}')
    if not (Path(export_dir) / '_HEADER.txt').is_file():
        return out + ['Export it first to check for light-only problems']
    try:
        masters = export_masters(str(export_dir))
    except SystemExit as missing:
        return out + [str(missing)]
    plain = [Path(m).name for m in masters if Path(m).suffix.lower() == '.esp']
    if plain:
        out.append(f"plain .esp masters ({', '.join(plain)}): loading a light plugin early pulls them early too")
    own = len(masters)
    new ={sig: sum(int(r['FormID'], 16) >> 24 == own for r in own_records(export_dir, sig)) for sig in ('CELL', 'WRLD')}
    if new['CELL'] and built.suffix.lower() == '.esm':
        out.append(f"{new['CELL']} new cells in a master: a mod overriding them may not load them (an xEdit warning, "
                   'not confirmed in Fallout 4)')
    if new['WRLD']:
        out.append(f"{new['WRLD']} new worldspaces: untested in a light plugin")
    return out
