"""FNV's Pip-Boy tabs on Fallout 4's STAT page: SKILLS, REPUTATION, KARMA, CHALLENGES, after its own three.

Each tab is a start-game quest running F3NV_PipboyTab (F3NV_KarmaPage for
KARMA, which sets its rows first), which hands the F3NV plugin
the tab: its name, place, rows (a FormList of actor values on the player),
the strings a row's value picks (none: the number) and the globals showing
each row. The plugin draws it. Builds before 2026-10-23 drew these with the
Pip-Boy Tabs mod through Data\\PBT files, which `remove_legacy_tabs` deletes.

See: docs/fork/fo4_pipboy_tabs.md
"""

from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.spike import records as R

#: The tab quest script, the natives it calls, and each tab's place among ours (FNV's STATS order).
TAB_SCRIPT, NATIVES = 'F3NV_PipboyTab', 'CRUI_Pipboy'
ORDER = {'SKILLS': 0, 'REPUTATION': 1, 'KARMA': 2, 'CHALLENGES': 3}
#: derive_formid site of a tab's quest (key: its EditorID).
TAB_SITE = 'FNV Pip-Boy tab'
#: The Pip-Boy Tabs files older builds wrote: Data\\PBT\\<plugin stem>_<name>.ini.
LEGACY_FOLDER, LEGACY_NAMES = 'PBT', ('Karma', 'Reputation')


def tab_edid(name: str) -> str:
    """Tab `name`'s quest EditorID."""
    return f'TES4PipboyTab{name.title()}'


def tab_formid(builder, name: str) -> int:
    """Tab `name`'s quest FormID at TAB_SITE (tab_quest's, given no `fid`)."""
    return builder.writer.derive_formid(TAB_SITE, tab_edid(name))


def tab_quest(builder, name: str, rows: int, values: list = (), shown: int = 0, script: str = TAB_SCRIPT,
              props: tuple = (None, None), fid: int = None) -> int:
    """Write tab `name`'s start-game quest (on `fid`, else one hashed at TAB_SITE) running `script`
    (F3NV_PipboyTab or one extending it, with its own `props`: object and value properties) on FormList `rows`,
    strings `values` and FormList `shown`; its FormID."""
    objects, extra = props
    props = {'Rows': rows, **({'Shown': shown} if shown else {}), **(objects or {})}
    vals = {'TabName': ('string', name), 'Order': ('int', ORDER[name]), **(extra or {})}
    if values:
        vals['Values'] = ('strings', list(values))
    edid = tab_edid(name)
    fid = fid or tab_formid(builder, name)
    vmad = quest_fragments('', [], scripts=[(script, props, vals)])
    builder.writer.add_record('QUST', R.pack_fnv_quest(fid, edid, '', 0, vmad, [], [], [], True))
    builder.scripts.used += [script, TAB_SCRIPT, NATIVES]
    return fid


def remove_legacy_tabs(data_dir: Path, plugin: str) -> list:
    """Delete the Pip-Boy Tabs files an older build of `plugin` wrote in `data_dir`; the paths removed."""
    gone = []
    for name in LEGACY_NAMES:
        path = data_dir / LEGACY_FOLDER / f'{Path(plugin).stem}_{name}.ini'
        if path.exists():
            path.unlink()
            gone.append(path)
    return gone
