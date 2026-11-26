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
from fo4_import.app import addons, light_plugins
from fo4_import.app import settings as S
from fo4_import.base import release
from asset_convert.sources import source_registry
from fo4_import.classic_look import plugin_name
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from fo4_import.pipeline import build_plan, eta, eta_inputs
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.spike.facegen import faces_stamp
from tools.validate.fo4_install_check import PLUGINS, RUNTIME_DLL

REPO = Path(__file__).resolve().parents[2]
#: Per source game: name, note, master, plugin, start cell, worldspace, test block center, Classic Look made for it.
GAMES = {
    'falloutnv': {'label': 'Fallout: New Vegas', 'note': '', 'master': 'FalloutNV.esm', 'plugin': 'FalloutNV.esm',
                  'cell': 'GSDocMitchellHouse', 'world': 'WastelandNV', 'test_center': (-18, 0), 'classic': True},
    'fallout3': {'label': 'Fallout 3', 'note': 'experimental; keep it in its own Mod Organizer profile',
                 'master': 'Fallout3.esm', 'plugin': 'Fallout3.esm', 'cell': 'Vault101d', 'world': 'Wasteland',
                 'test_center': (-4, -4), 'classic': False},
}
#: Stage keys in run order, with their labels.
ORDER = (('import', 'Import the mod folder'), ('export', 'Export the plugin and its archives'),
         ('helpers', 'Helper plugin'), ('build', 'Build the plugin and assets (whole build)'),
         ('update', 'Rebuild what changed (code-only changes replayed; the mods built on it follow)'),
         ('faces', 'Faces (our own FaceGen)'),
         ('runtime', 'Install the F4SE plugin (F3NV.dll)'),
         ('classic', 'Classic Look plugin (flat FNV lights and tone)'),
         ('check', 'Check references (fast)'), ('fo4edit', "FO4Edit's full check (slow; may wait for a click)"))
#: Stages left unticked unless the user ticks them: the Classic Look is a choice; FO4Edit waits.
OPTIONAL = frozenset({'classic', 'fo4edit'})
#: Stages that build, the first of them preceded by BENCHMARK when this machine has none (plan).
BUILDS = frozenset({'build', 'update'})
#: The key and label of the machine benchmark plan() runs once.
BENCHMARK = ('benchmark', 'Measure this machine for the time estimate (once, about a minute)')
#: Stages that need a Windows-only tool.
WINDOWS_TOOLS = {'fo4edit': 'FO4Edit'}


@dataclass(frozen=True)
class Scope:
    """What the build covers: `kind` test (the documented 3x3 block), region (grid corners) or world (whole)."""
    kind: str = 'test'
    region: tuple = (0, 0, 0, 0)
    workers: int = 0


#: Plugin file suffixes a built folder can hold (lower case).
PLUGIN_FILES = ('.esm', '.esp', '.esl')
#: Stages only the game itself runs: the helper plugin, the Classic Look and the F4SE plugin go with the game's.
GAME_ONLY = frozenset({'helpers', 'classic', 'runtime'})


def target(settings: dict, source: str) -> addons.Target:
    """What `source`'s run converts (fo4_import.app.addons)."""
    return addons.target(settings, source, GAMES[source]['master'])


def export_dir(settings: dict, source: str) -> Path:
    """Where the target's export lives (convert.py's export folder; an imported mod's by the registry)."""
    chosen = target(settings, source)
    if chosen.mod and source_registry.get(S.export_root(settings), chosen.plugin):
        return Path(source_registry.record_dir(S.export_root(settings), chosen.plugin))
    return S.export_root(settings) / (Path(chosen.mod).name if chosen.mod else chosen.plugin)


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
        return Found('imported', True) if chosen.mod and source_registry.get(S.export_root(settings), chosen.plugin) else None
    if stage == 'export':
        return Found(f'export from {_when(exported)}', True) if exported else None
    if stage in ('build', 'faces'):
        return _built(plugin_path(settings, source), stage)
    made = {'helpers': S.output_dir(settings, source) / FALLOUT4_HELPER_PLUGIN,
            'classic': S.output_dir(settings, source) / plugin_name(GAMES[source]['plugin']),
            'runtime': chosen.output / PLUGINS / RUNTIME_DLL}.get(stage)
    return Found(f'{made.name} built {_when(made.stat().st_mtime)}') if made and made.is_file() else None


def _built(plugin: Path, stage: str) -> 'Found | None':
    """found() of the build or faces stage of `plugin`: done once a finished build (or faces run) is recorded, as
    Rebuild what changed then rebuilds it, and runs its faces again, when needed.
    See: docs/fork/fo4_gui.md#rebuild
    """
    older = build_plan.from_older_release(plugin) if plugin.is_file() else ''
    if stage == 'faces':
        stamp = faces_stamp(plugin)
        finished = stamp is not None and stamp.get('status') == 'finished'
        return Found(f'faces made {stamp["ended"]}', not older) if finished else None
    if not plugin.is_file():
        return None
    built = f'{plugin.name} built {_when(plugin.stat().st_mtime)}'
    return Found(f'{built}, {older}: convert it in full' if older else built,
                 not older and build_plan.record(plugin) is not None)


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
    plugin = None if chosen.game else addons.source_file(settings, source, chosen, S.export_root(settings))
    names = addons.plugin_masters(plugin) if plugin else []
    return [addons.output(settings, source, name, master) for name in names]


def built_plugins(settings: dict, source: str) -> list:
    """Every plugin of `source` with a finished build recorded (build_plan.record): the game's, each add-on's, then
    any other in a folder beside the game's output (built there from the command line)."""
    master, out = GAMES[source]['master'], S.output_dir(settings, source)
    paths = [out / GAMES[source]['plugin']]
    paths += [addons.output(settings, source, e['plugin'], master) / e['plugin'] for e in addons.entries(settings, source)]
    beside = sorted(p for d in (out.parent.iterdir() if out.parent.is_dir() else ()) if d.is_dir() and d != out
                    for p in d.iterdir() if p.suffix.lower() in PLUGIN_FILES)
    found = [p for p in dict.fromkeys([*paths, *beside]) if build_plan.record(p) is not None]
    return list({p.resolve(): p for p in found}.values())


def rebuilt(settings: dict, source: str) -> list:
    """What Rebuild what changed hands build_plan --run: the target's built plugin, the built plugins it reads as
    masters, and the built add-ons reading it, directly or through another.
    See: docs/fork/fo4_gui.md#rebuild
    """
    built, own = built_plugins(settings, source), plugin_path(settings, source).resolve()
    return [p for p in built if p.resolve() in build_plan.dependents(own, built)
            or own in build_plan.dependents(p, built)]


def missing_master(settings: dict, source: str) -> str:
    """The first of the target's masters with no built plugin in its output folder or no export in this work
    folder (a build reads both); '' when none."""
    chosen, master, root = target(settings, source), GAMES[source]['master'], S.export_root(settings)
    plugin = None if chosen.game else addons.source_file(settings, source, chosen, root)
    for name in addons.plugin_masters(plugin) if plugin else []:
        built = GAMES[source]['plugin'] if name.lower() == master.lower() else name
        if not (addons.output(settings, source, name, master) / built).is_file() \
                or not Path(build_plan.in_root(root, name)).is_dir():
            return name
    return ''


def unavailable(settings: dict, source: str, stage: str, platform: str = sys.platform) -> str:
    """Why `stage` cannot run for `source` here, or '' when it can."""
    chosen = target(settings, source)
    if stage == 'classic' and not GAMES[source]['classic']:
        return f"made for {GAMES['falloutnv']['label']} only so far"
    if stage == 'import' and not chosen.mod:
        return 'only a mod folder is imported'
    if stage in GAME_ONLY and not chosen.game:
        return 'made with the game itself'
    if stage in WINDOWS_TOOLS and platform != 'win32':
        return f'needs {WINDOWS_TOOLS[stage]}, which runs only on Windows'
    if stage == 'export' and not chosen.mod and not _has_data(settings, source):
        return f"{GAMES[source]['master']}'s game folder is not set, or has no Data folder"
    if stage in ('build', 'update') and not chosen.game and missing_master(settings, source):
        return f'convert its master {missing_master(settings, source)} first, with this work folder'
    if stage == 'update' and build_plan.record(plugin_path(settings, source)) is None:
        return 'no finished build of it yet: build it once first'
    if stage == 'update' and build_plan.from_older_release(plugin_path(settings, source)):
        return f'{build_plan.from_older_release(plugin_path(settings, source))}: convert it in full'
    if stage in ('helpers', 'build', 'update', 'check', 'fo4edit') and not _has_data(settings, 'fallout4'):
        return "Fallout 4's game folder is not set, or has no Data folder"
    return ''


def game_problem(settings: dict, source: str) -> str:
    """Why game `source` cannot be picked ('' when its Data holds its master)."""
    folder = S.game_dir(settings, source)
    return '' if folder and (folder / 'Data' / GAMES[source]['master']).is_file() else 'folder not set (Setup screen)'


def row_state(settings: dict, source: str, plugin: str) -> str:
    """The note beside `plugin` ('' the game) in the target list: when it was built and by which release, else
    what it waits on."""
    master, game = GAMES[source]['master'], S.output_dir(settings, source) / GAMES[source]['plugin']
    path = addons.output(settings, source, plugin, master) / plugin if plugin else game
    if build_plan.record(path) is not None:
        return f'built {_when(path.stat().st_mtime)}{release.made_with(build_plan.built_release(path))}'
    return f'convert {master} first' if plugin and build_plan.record(game) is None else 'not built yet'


def next_step(settings: dict, source: str) -> str:
    """What the user does next for the chosen target, in one sentence or two.
    See: docs/fork/fo4_gui.md#convert-screen
    """
    chosen, master = target(settings, source), GAMES[source]['master']
    name, missing = (master, '') if chosen.game else (chosen.plugin, missing_master(settings, source))
    if not _has_data(settings, 'fallout4'):
        return 'Set your Fallout 4 folder on the Setup screen first.'
    if chosen.game and game_problem(settings, source):
        return f"Set your {GAMES[source]['label']} folder on the Setup screen first."
    if missing:
        return f'Convert {missing} first: pick it in the list above.'
    built = plugin_path(settings, source)
    if build_plan.record(built) is None or build_plan.from_older_release(built):
        return f'Click Convert to build {name}; the line under the button says about how long it takes.'
    return (f'{name} is built. Click Convert to rebuild only what changed since, or open Finished to set it up in '
            'Mod Organizer and play.')


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
    if stage == 'update':
        return lambda: [py, '-m', 'fo4_import.pipeline.build_plan', '--run', '--export-root',
                        str(S.export_root(settings)), '--scripts-root', str(S.scripts_dir(settings, source).parent),
                        *map(str, rebuilt(settings, source))]
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
    masters' outputs as plugin folders, its light opt-in (light_plugins), and its scope from its export
    (addons.build_scope; a region scope's corners on the largest master worldspace it changes)."""
    chosen, out = target(settings, source), plugin_path(settings, source)
    region = scope.region if scope.kind == 'region' else None
    args = ['--export', str(export_dir(settings, source)), '--out', str(out), '--data',
            str(chosen.output), '--scripts', str(S.scripts_dir(settings, source).parent / chosen.plugin),
            '--plugin-dirs', *map(str, master_dirs(settings, source)), '--mod-sources', str(settings_file),
            '--no-test-cell', *light_plugins.arguments(settings, source, chosen.plugin, out)]
    return args + _shared_arguments(settings, source, scope) + addons.build_scope(export_dir(settings, source),
                                                                                  region)


def _shared_arguments(settings: dict, source: str, scope: Scope) -> list:
    """The workers, resource profile, replacement profile and replacement file every build of `source` takes."""
    block, replacements = settings['per_source'][source], S.replacement_file(settings, source)
    args = ['--resources', settings['resources']] + (['--workers', str(scope.workers)] if scope.workers else [])
    args += ['--profile', block['profile']] if block['profile'] else []
    return args + (['--replacements', str(replacements)] if replacements.is_file() else [])


def estimate(settings: dict, source: str) -> str:
    """'Estimated build time: ...' of `source`'s target under the chosen resources, from its last finished build,
    else its export; '' when it has neither yet.
    See: docs/fork/fo4_build_resources.md#eta
    """
    model, stamp = eta.load(), stamp_path(plugin_path(settings, source))
    found = eta.target_features(stamp if eta_inputs.record_build(stamp) else export_dir(settings, source), model)
    if found is None:
        return ''
    source_text = 'from its last build' if found[1] else 'from its export, for a whole build'
    return (f'Estimated build time: {eta.summary(model, found[0], eta.benchmark(), settings["resources"])} '
            f'({source_text}; {eta.NOTE})')


def package(settings: dict, source: str) -> 'Path | None':
    """Zip `source`'s output folder beside it when the user chose zip output; the zip, or None."""
    if settings['per_source'][source]['output']['kind'] != 'zip':
        return None
    folder = target(settings, source).output
    return Path(shutil.make_archive(str(folder), 'zip', root_dir=folder))


def plan(settings: dict, source: str, chosen: list, scope: Scope, settings_file: Path) -> list:
    """[(stage key, label, argv)] of the `chosen` stages that can run, in run order; before the first build on a
    machine with no benchmark (eta.benchmark), the benchmark, so the build's estimate fits this machine.
    See: docs/fork/fo4_build_resources.md#benchmark
    """
    out = [(key, label, command(settings, source, key, scope, settings_file)) for key, label in ORDER
           if key in chosen and not unavailable(settings, source, key)]
    builds = [i for i, (key, _label, _argv) in enumerate(out) if key in BUILDS]
    if builds and eta.benchmark() is None:
        where = eta.benchmark_path()
        argv = [sys.executable, str(REPO / 'tools' / 'release' / 'machine_benchmark.py'), '--out', str(where),
                '--dir', str(where.parent.parent)]
        out.insert(builds[0], (*BENCHMARK, argv))
    return out
