"""Our dialogue menu in place of XDI: a built plugin's links file, and the menu movie built from the user's own game
files, written with the build.

F3NV.dll (tes_runtime/fo4_condition/dialogue.cpp) reads every file in
F4SE/Plugins/F3NV_Menus. A row of four columns links a menu option (an INFO
of a scene's player topic) to its answer topic; a row of five names the skill
check an answer INFO's prompt carries. Each FormID is a plugin name and an
object id, so a row resolves under any load order or ESL. Each plugin writes
its own file, named after it; the masterless build also installs the menu
movie (built from our own sources with mxmlc) and drops the XDI-era hub files
an older setup put in the data folder.

See: docs/fork/fo4_dialogue_menu_plan.md#converter
"""

from pathlib import Path

from fo4_import.dialogue_menu import movie

#: The links files' folder in a mod, which F3NV.dll reads (dialogue.cpp LINKS).
LINKS = Path('F4SE') / 'Plugins' / 'F3NV_Menus'
#: The hub plugin and links tools.dialog.menu_rebuild made for XDI-built menus: deleted, as the build has its own.
LEGACY = ('F3NV_MenuHub.esp', (LINKS / 'F3NV_MenuHub.txt').as_posix())
HEADER = ('# option plugin, option INFO, answer plugin, answer DIAL | answer plugin, answer INFO, skill plugin, '
          'skill AVIF, needed (F3NV.dll dialogue.cpp)')


def write_links(path: Path, rows: list) -> Path:
    """A links file of `rows` (plugin, FormID pairs, then a check's number needed); object ids in hex."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER] + ['\t'.join(f'{v & 0xFFFFFF:06X}' if i % 2 else str(v) for i, v in enumerate(row))
                        for row in rows]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def rows(names: list, links: list, checks: list) -> list:
    """Links rows of `links` [(option, answer)] and `checks` [(answer INFO, actor value, needed)]; `names` the
    plugin of each load index (the masters, then the plugin)."""
    def named(fid: int) -> tuple:
        """(plugin, FormID) of `fid`."""
        return names[fid >> 24], fid
    return ([(*named(option), *named(answer)) for option, answer in links]
            + [(*named(info), *named(av), needed) for info, av, needed in checks])


def remove_legacy(data_dir: Path) -> list:
    """Delete the XDI-era hub files (LEGACY) in `data_dir`; the paths removed."""
    gone = [Path(data_dir) / rel for rel in LEGACY if (Path(data_dir) / rel).is_file()]
    for path in gone:
        path.unlink()
    return gone


def write(builder, data_dir: Path, plugin: str) -> None:
    """Write `plugin`'s links file from builder.say's links and checks into `data_dir`; the masterless build also
    installs the movie and removes the legacy hub files. Counts go to builder.counts."""
    say, counts = builder.say, builder.counts
    found = rows([*builder.writer.masters, plugin], say.links, say.checks) if say else []
    path = Path(data_dir) / LINKS / f'{Path(plugin).stem}.txt'
    if found:
        write_links(path, found)
    else:
        path.unlink(missing_ok=True)
    counts['dialogue menu links'] = len(say.links) if say else 0
    counts['dialogue menu skill checks'] = len(say.checks) if say else 0
    counts['dialogue menu hub files removed'] = len(remove_legacy(data_dir))
    if not builder.built:
        installed = int(movie.install(data_dir) is not None)
        counts['dialogue menu movie installed'] = installed
        counts['dialogue menu movie missing (no Flex SDK)'] = 1 - installed
