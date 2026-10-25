"""The Convert screen's stages as the command lines they run, from the app's settings. No Qt here.

Each stage is an existing command (docs/fork/fo4_pipeline.md): export (convert.py), scripts
(script_convert.pipeline), the helper plugin, the build (fo4_import.pipeline.run), the reference check
(tools.validate.fo4_ref_check) and, optional and off by default, FO4Edit's full check. Output
goes to the source's output folder (fo4_import.app.settings.output_dir), which is the build's Data folder; the
converted scripts go to the chosen scripts folder (an earlier run's can be reused). The export folder is still the
repo's `export/` (convert.py fixes it); found() says what an earlier run already left for each stage. A stage that cannot run here says why: FO3 has no build path yet, and a stage needing a Windows-only tool
needs Windows.

See: docs/fork/fo4_gui.md#app-shape
"""

import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.mod_sources import data_dirs
from fo4_import.app import settings as S
from script_convert.constants import FALLOUT4_HELPER_PLUGIN

REPO = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO / 'export'
#: Per source game: master, plugin built, start cell, main worldspace, test block center, whether the build supports it.
GAMES = {
    'falloutnv': {'master': 'FalloutNV.esm', 'plugin': 'FalloutNV.esp', 'cell': 'GSDocMitchellHouse',
                  'world': 'WastelandNV', 'test_center': (-18, 0), 'built': True},
    'fallout3': {'master': 'Fallout3.esm', 'plugin': 'Fallout3.esp', 'cell': '', 'world': 'Wasteland',
                 'test_center': (0, 0), 'built': False},
}
#: Stage keys in run order, with their labels.
ORDER = (('export', 'Export the source game'), ('scripts', 'Convert scripts'),
         ('helpers', 'Helper plugin'), ('build', 'Build the plugin and assets'),
         ('check', 'Check references (fast)'), ('fo4edit', "FO4Edit's full check (slow; may wait for a click)"))
#: Stages left unticked unless the user ticks them: FO4Edit waits on its developer-message dialog when unattended.
OPTIONAL = frozenset({'fo4edit'})
#: Stages that run a Windows-only tool (the FO4 Papyrus compiler, Creation Kit tools, FO4Edit).
WINDOWS_TOOLS = {'scripts': 'the FO4 Papyrus compiler', 'build': "the Creation Kit's Elric and LipGen",
                 'fo4edit': 'FO4Edit'}


@dataclass(frozen=True)
class Scope:
    """What the build covers: `kind` test (the documented 3x3 block), region (grid corners) or world (whole)."""
    kind: str = 'test'
    region: tuple = (0, 0, 0, 0)
    workers: int = 0


def export_dir(source: str) -> Path:
    """Where `source`'s export lives (convert.py's export folder)."""
    return EXPORT_ROOT / GAMES[source]['master']


@dataclass(frozen=True)
class Found:
    """What an earlier run (the app's or the command line's) left for a stage; `done`: no need to run it again."""
    text: str
    done: bool = False


def found(settings: dict, source: str, stage: str) -> 'Found | None':
    """What `stage` already has: the export, converted scripts (done when newer than the export), the helper plugin
    or the built plugin in the output; None when nothing (the checks leave nothing)."""
    header = export_dir(source) / '_HEADER.txt'
    exported = header.stat().st_mtime if header.is_file() else 0
    if stage == 'export':
        return Found(f'export from {_when(exported)}', True) if exported else None
    if stage == 'scripts':
        times = [e.stat().st_mtime for e in _entries(S.scripts_dir(settings, source)) if e.name.endswith('.psc')]
        if not times:
            return None
        stale = max(times) < exported
        return Found(f'{len(times)} converted {_when(max(times))}' + (', older than the export' if stale else ''),
                     not stale)
    made = {'helpers': S.output_dir(settings, source) / FALLOUT4_HELPER_PLUGIN,
            'build': plugin_path(settings, source)}.get(stage)
    return Found(f'{made.name} built {_when(made.stat().st_mtime)}') if made and made.is_file() else None


def _entries(folder: Path) -> list:
    """`folder`'s entries ([] when it is missing)."""
    if not folder.is_dir():
        return []
    with os.scandir(folder) as entries:
        return list(entries)


def _when(stamp: float) -> str:
    """A file time as local 'YYYY-MM-DD HH:MM'."""
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(stamp))


def plugin_path(settings: dict, source: str) -> Path:
    """The plugin the build writes, in the output folder."""
    return S.output_dir(settings, source) / GAMES[source]['plugin']


def unavailable(settings: dict, source: str, stage: str, platform: str = sys.platform) -> str:
    """Why `stage` cannot run for `source` here, or '' when it can."""
    if stage != 'export' and not GAMES[source]['built']:
        return f"the Fallout 4 build does not support {GAMES[source]['master']} yet"
    if stage in WINDOWS_TOOLS and platform != 'win32':
        return f'needs {WINDOWS_TOOLS[stage]}, which the FO4 build runs only on Windows so far'
    if stage == 'export' and not _has_data(settings, source):
        return f"{GAMES[source]['master']}'s game folder is not set, or has no Data folder"
    if stage in ('helpers', 'build', 'check', 'fo4edit') and not _has_data(settings, 'fallout4'):
        return "Fallout 4's game folder is not set, or has no Data folder"
    return ''


def _has_data(settings: dict, game: str) -> bool:
    """Whether `game`'s folder is known and holds a Data folder."""
    folder = S.game_dir(settings, game)
    return bool(folder) and (folder / 'Data').is_dir()


def command(settings: dict, source: str, stage: str, scope: Scope, settings_file: Path) -> list:
    """The argv of `stage` for `source` (`settings_file`: the saved settings, read by the build for mod sources)."""
    py, game, out = sys.executable, GAMES[source], S.output_dir(settings, source)
    if stage == 'export':
        return [py, str(REPO / 'convert.py'), '--export-only', '-f', game['master'],
                '--data-dir', str(S.game_dir(settings, source) / 'Data')]
    if stage == 'scripts':
        return [py, '-m', 'script_convert.pipeline', str(export_dir(source)), '-o',
                str(S.scripts_dir(settings, source)), '--target', 'fallout4']
    if stage == 'helpers':
        return [py, '-m', 'fo4_import.helpers_plugin', '--out', str(out / FALLOUT4_HELPER_PLUGIN)]
    if stage == 'build':
        return [py, '-m', 'fo4_import.pipeline.run', *build_arguments(settings, source, scope, settings_file)]
    dirs = [str(d) for d in data_dirs(S.mod_sources(settings))]
    tool = 'tools.validate.fo4_ref_check' if stage == 'check' else 'tools.validate.fo4_check'
    return [py, '-m', tool, str(plugin_path(settings, source)), '--plugin-dirs', str(out), *dirs]


def build_arguments(settings: dict, source: str, scope: Scope, settings_file: Path) -> list:
    """fo4_import.pipeline.run's arguments for `scope`, with the source's profile and replacement file."""
    game, out, block = GAMES[source], S.output_dir(settings, source), settings['per_source'][source]
    args = ['--export', str(export_dir(source)), '--out', str(plugin_path(settings, source)), '--data', str(out),
            '--scripts', str(S.scripts_dir(settings, source)), '--mod-sources', str(settings_file),
            '--world', game['world']]
    if scope.kind == 'test':
        args += ['--around', *map(str, game['test_center']), '--radius', '1']
    elif scope.kind == 'region':
        args += ['--region', *map(str, scope.region)]
    else:
        args += ['--whole', '--no-test-cell']
    args += ['--workers', str(scope.workers)] if scope.workers else []
    args += ['--profile', block['profile']] if block['profile'] else []
    replacements = S.replacement_file(settings, source)
    args += ['--replacements', str(replacements)] if replacements.is_file() else []
    return args + [game['cell']]


def package(settings: dict, source: str) -> 'Path | None':
    """Zip `source`'s output folder beside it when the user chose zip output; the zip, or None."""
    if settings['per_source'][source]['output']['kind'] != 'zip':
        return None
    folder = S.output_dir(settings, source)
    return Path(shutil.make_archive(str(folder), 'zip', root_dir=folder))


def plan(settings: dict, source: str, chosen: list, scope: Scope, settings_file: Path) -> list:
    """[(stage key, label, argv)] of the `chosen` stages that can run, in run order."""
    return [(key, label, command(settings, source, key, scope, settings_file)) for key, label in ORDER
            if key in chosen and not unavailable(settings, source, key)]
