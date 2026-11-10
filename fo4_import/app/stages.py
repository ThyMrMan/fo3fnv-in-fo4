"""The Convert screen's stages as the command lines they run, from the app's settings. No Qt here.

Each stage is an existing command (docs/fork/fo4_pipeline.md): a mod folder's import and the export with its
archives (convert.py), the helper plugin, the build (fo4_import.pipeline.run, converting the scripts first), the
reference check and, optional, FO4Edit's full check. They convert the chosen target (fo4_import.app.addons): the
game, or a DLC or imported mod into its own output folder with its masters' outputs as plugin folders and its
scope from its export, computed when the build starts. found() says what earlier runs left; a stage that cannot
run here says why.

See: docs/fork/fo4_gui.md#app-shape
"""

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.mod_sources import data_dirs
from fo4_import.app import addons
from fo4_import.app import settings as S
from asset_convert.sources import source_registry
from fo4_import.classic_look import plugin_name
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from tools.validate.fo4_install_check import PLUGINS, RUNTIME_DLL

REPO = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO / 'export'
#: Per source game: master, plugin built, start cell, main worldspace, test block center, whether the build supports it.
GAMES = {
    'falloutnv': {'master': 'FalloutNV.esm', 'plugin': 'FalloutNV.esm', 'cell': 'GSDocMitchellHouse',
                  'world': 'WastelandNV', 'test_center': (-18, 0), 'built': True},
    'fallout3': {'master': 'Fallout3.esm', 'plugin': 'Fallout3.esp', 'cell': '', 'world': 'Wasteland',
                 'test_center': (0, 0), 'built': False},
}
#: Stage keys in run order, with their labels.
ORDER = (('import', 'Import the mod folder'), ('export', 'Export the plugin and its archives'),
         ('helpers', 'Helper plugin'), ('build', 'Build the plugin and assets'),
         ('faces', 'Faces (the Creation Kit\'s FaceGen, through MO2; slow)'),
         ('runtime', 'Install the F4SE plugin (F3NV.dll)'),
         ('classic', 'Classic Look plugin (flat FNV lights and tone)'),
         ('check', 'Check references (fast)'), ('fo4edit', "FO4Edit's full check (slow; may wait for a click)"))
#: Stages left unticked unless the user ticks them: the Classic Look is a choice; faces take hours; FO4Edit waits.
OPTIONAL = frozenset({'classic', 'faces', 'fo4edit'})
#: Stages that run a Windows-only tool (the FO4 Papyrus compiler, Creation Kit tools, FO4Edit).
WINDOWS_TOOLS = {'build': "the FO4 Papyrus compiler and the Creation Kit's Elric and LipGen", 'fo4edit': 'FO4Edit',
                 'faces': 'the Creation Kit'}


@dataclass(frozen=True)
class Scope:
    """What the build covers: `kind` test (the documented 3x3 block), region (grid corners) or world (whole)."""
    kind: str = 'test'
    region: tuple = (0, 0, 0, 0)
    workers: int = 0


#: Stages only the game itself runs: the helper plugin, the Classic Look and the F4SE plugin go with the game's.
GAME_ONLY = frozenset({'helpers', 'classic', 'runtime'})


def target(settings: dict, source: str) -> addons.Target:
    """What `source`'s run converts (fo4_import.app.addons)."""
    return addons.target(settings, source, GAMES[source]['master'])


def export_dir(settings: dict, source: str) -> Path:
    """Where the target's export lives (convert.py's export folder; an imported mod's by the registry)."""
    chosen = target(settings, source)
    if chosen.mod and source_registry.get(EXPORT_ROOT, chosen.plugin):
        return Path(source_registry.record_dir(EXPORT_ROOT, chosen.plugin))
    return EXPORT_ROOT / (Path(chosen.mod).name if chosen.mod else chosen.plugin)


@dataclass(frozen=True)
class Found:
    """What an earlier run (the app's or the command line's) left for a stage; `done`: no need to run it again."""
    text: str
    done: bool = False


def found(settings: dict, source: str, stage: str) -> 'Found | None':
    """What `stage` already has: the export, the helper plugin or the built plugin in the output; None when nothing
    (the checks leave nothing)."""
    chosen, header = target(settings, source), export_dir(settings, source) / '_HEADER.txt'
    exported = header.stat().st_mtime if header.is_file() else 0
    if stage == 'import':
        return Found('imported', True) if chosen.mod and source_registry.get(EXPORT_ROOT, chosen.plugin) else None
    if stage == 'export':
        return Found(f'export from {_when(exported)}', True) if exported else None
    made = {'helpers': S.output_dir(settings, source) / FALLOUT4_HELPER_PLUGIN,
            'build': plugin_path(settings, source),
            'classic': S.output_dir(settings, source) / plugin_name(GAMES[source]['plugin']),
            'runtime': chosen.output / PLUGINS / RUNTIME_DLL}.get(stage)
    return Found(f'{made.name} built {_when(made.stat().st_mtime)}') if made and made.is_file() else None


def _when(stamp: float) -> str:
    """A file time as local 'YYYY-MM-DD HH:MM'."""
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(stamp))


def plugin_path(settings: dict, source: str) -> Path:
    """The plugin the build writes, in the target's output folder."""
    chosen = target(settings, source)
    return chosen.output / (GAMES[source]['plugin'] if chosen.game else chosen.plugin)


def master_dirs(settings: dict, source: str) -> list:
    """The output folders of the target's masters (an add-on's plugin folders), in its master order."""
    chosen, master = target(settings, source), GAMES[source]['master']
    plugin = None if chosen.game else addons.source_file(settings, source, chosen, EXPORT_ROOT)
    names = addons.plugin_masters(plugin) if plugin else []
    return [addons.output(settings, source, name, master) for name in names]


def missing_master(settings: dict, source: str) -> str:
    """The first of the target's masters with no built plugin in its output folder ('' when all are built)."""
    chosen, master = target(settings, source), GAMES[source]['master']
    plugin = None if chosen.game else addons.source_file(settings, source, chosen, EXPORT_ROOT)
    for name in addons.plugin_masters(plugin) if plugin else []:
        built = GAMES[source]['plugin'] if name.lower() == master.lower() else name
        if not (addons.output(settings, source, name, master) / built).is_file():
            return name
    return ''


def unavailable(settings: dict, source: str, stage: str, platform: str = sys.platform) -> str:
    """Why `stage` cannot run for `source` here, or '' when it can."""
    chosen = target(settings, source)
    if stage not in ('import', 'export') and not GAMES[source]['built']:
        return f"the Fallout 4 build does not support {GAMES[source]['master']} yet"
    if stage == 'import' and not chosen.mod:
        return 'only a mod folder is imported'
    if stage in GAME_ONLY and not chosen.game:
        return 'made with the game itself'
    if stage in WINDOWS_TOOLS and platform != 'win32':
        return f'needs {WINDOWS_TOOLS[stage]}, which the FO4 build runs only on Windows so far'
    if stage == 'export' and not chosen.mod and not _has_data(settings, source):
        return f"{GAMES[source]['master']}'s game folder is not set, or has no Data folder"
    if stage == 'build' and not chosen.game and missing_master(settings, source):
        return f'build its master {missing_master(settings, source)} first'
    if stage == 'faces' and not any(s.kind == 'mo2_profile' for s in S.mod_sources(settings)):
        return 'the Creation Kit runs through MO2: add your MO2 profile as a mod source on the Setup screen'
    if stage in ('helpers', 'build', 'check', 'fo4edit') and not _has_data(settings, 'fallout4'):
        return "Fallout 4's game folder is not set, or has no Data folder"
    return ''


def _has_data(settings: dict, game: str) -> bool:
    """Whether `game`'s folder is known and holds a Data folder."""
    folder = S.game_dir(settings, game)
    return bool(folder) and (folder / 'Data').is_dir()


def command(settings: dict, source: str, stage: str, scope: Scope, settings_file: Path) -> list:
    """The argv of `stage` for `source`'s target (`settings_file`: the saved settings, read by the build for mod
    sources); an add-on's build is a function giving it when the stage starts, after its export."""
    py, chosen, out = sys.executable, target(settings, source), target(settings, source).output
    if stage == 'import':
        return [py, str(REPO / 'convert.py'), '--import-mod', chosen.mod]
    if stage == 'export':
        game = [] if chosen.mod else ['--extract-only', '--data-dir', str(S.game_dir(settings, source) / 'Data')]
        return [py, str(REPO / 'convert.py'), '--export-only', *game, '-f', chosen.plugin]
    if stage == 'helpers':
        return [py, '-m', 'fo4_import.helpers_plugin', '--out', str(out / FALLOUT4_HELPER_PLUGIN)]
    if stage == 'faces':
        return [py, '-m', 'fo4_import.spike.facegen', '--export', str(export_dir(settings, source)), '--data',
                str(out), plugin_path(settings, source).name]
    if stage == 'runtime':
        return [py, '-m', 'fo4_import.app.runtime_dll', '--out', str(out)]
    if stage == 'classic':
        return [py, '-m', 'fo4_import.classic_look', '--plugin', str(plugin_path(settings, source)), '--out', str(out)]
    if stage == 'build' and not chosen.game:
        return lambda: [py, '-m', 'fo4_import.pipeline.run', *addon_arguments(settings, source, scope, settings_file)]
    if stage == 'build':
        return [py, '-m', 'fo4_import.pipeline.run', *build_arguments(settings, source, scope, settings_file)]
    dirs = [str(d) for d in (*master_dirs(settings, source), *data_dirs(S.mod_sources(settings)))]
    tool = 'tools.validate.fo4_ref_check' if stage == 'check' else 'tools.validate.fo4_check'
    return [py, '-m', tool, str(plugin_path(settings, source)), '--plugin-dirs', str(out), *dirs]


def build_arguments(settings: dict, source: str, scope: Scope, settings_file: Path) -> list:
    """fo4_import.pipeline.run's arguments for `scope`, with the source's profile and replacement file."""
    game, out = GAMES[source], S.output_dir(settings, source)
    args = ['--export', str(export_dir(settings, source)), '--out', str(plugin_path(settings, source)), '--data',
            str(out), '--scripts', str(S.scripts_dir(settings, source)), '--mod-sources', str(settings_file),
            '--world', game['world']]
    if scope.kind == 'test':
        args += ['--around', *map(str, game['test_center']), '--radius', '1']
    elif scope.kind == 'region':
        args += ['--region', *map(str, scope.region)]
    else:
        args += ['reached', '--whole', '--no-test-cell']
    return args + _shared_arguments(settings, source, scope) + [game['cell']]


def addon_arguments(settings: dict, source: str, scope: Scope, settings_file: Path) -> list:
    """fo4_import.pipeline.run's arguments for an add-on target: its own output, scripts beside the game's, its
    masters' outputs as plugin folders, and its scope from its export (addons.build_scope; a region scope's corners
    on the largest master worldspace it changes)."""
    chosen = target(settings, source)
    region = scope.region if scope.kind == 'region' else None
    args = ['--export', str(export_dir(settings, source)), '--out', str(plugin_path(settings, source)), '--data',
            str(chosen.output), '--scripts', str(S.scripts_dir(settings, source).parent / chosen.plugin),
            '--plugin-dirs', *map(str, master_dirs(settings, source)), '--mod-sources', str(settings_file),
            '--no-test-cell']
    return args + _shared_arguments(settings, source, scope) + addons.build_scope(export_dir(settings, source),
                                                                                  region)


def _shared_arguments(settings: dict, source: str, scope: Scope) -> list:
    """The workers, profile and replacement file every build of `source` takes."""
    block, replacements = settings['per_source'][source], S.replacement_file(settings, source)
    args = ['--workers', str(scope.workers)] if scope.workers else []
    args += ['--profile', block['profile']] if block['profile'] else []
    return args + (['--replacements', str(replacements)] if replacements.is_file() else [])


def package(settings: dict, source: str) -> 'Path | None':
    """Zip `source`'s output folder beside it when the user chose zip output; the zip, or None."""
    if settings['per_source'][source]['output']['kind'] != 'zip':
        return None
    folder = target(settings, source).output
    return Path(shutil.make_archive(str(folder), 'zip', root_dir=folder))


def plan(settings: dict, source: str, chosen: list, scope: Scope, settings_file: Path) -> list:
    """[(stage key, label, argv)] of the `chosen` stages that can run, in run order."""
    return [(key, label, command(settings, source, key, scope, settings_file)) for key, label in ORDER
            if key in chosen and not unavailable(settings, source, key)]
