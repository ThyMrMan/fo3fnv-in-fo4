"""Run the preflight audits over every built game, or decide a finding by hand.

    python -m tools.validate.preflight
    python -m tools.validate.preflight --game Fallout3.esm --audit quest
    python -m tools.validate.preflight --mark "quest|Fallout3.esm|MS16|10" --as ok --note "radio"
    python -m tools.validate.preflight --mark "assets|*|outside|*" --as skip
    python -m tools.validate.preflight --accept-build --game Fallout3.esm
    python -m tools.validate.preflight --game Fallout3.esm --audit logs     # after a play-test
    py -3.14 -m tools.validate.preflight --fo4 "<mod folder>/FalloutNV.esm"  # a Fallout 4 build

Exit code 1 when any error is left that the ledger does not hide.
See: docs/commentary/tools_preflight.md#running-it
"""

import argparse
import re
import sys
from functools import partial
from pathlib import Path

from tools.validate.preflight import (asset_fo4, asset_load, build_diff, build_history, built_masters, condition_diff,
                                      dialogue_loss, dlc_overrides, findings, log_triage, package_ai, quest_progression,
                                      quest_start, quest_targets, script_health, script_props, timing,
                                      world_links)
from tools.validate.preflight import behavior
from tools.validate.preflight import menus
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.ledger import ledger_path
from fo4_import.spike.readiness import report_path
from tools.validate.fo4_quest_readiness import RECORD_PREFIX as FO4_EDID_PREFIX
from tools.validate.preflight.fo4_dialogue import Fo4Dialogue, left_out, line_copies, line_parts
from tools.validate.preflight.plugin_index import load_plugin
from tools.validate.preflight.quest_converted import load_scripts
from tools.validate.preflight.quest_source import SourceGame

#: The audits in the order they run and print.
AUDITS = ('quest', 'start', 'dialogue', 'conditions', 'menus', 'targets', 'timing', 'scripts', 'properties', 'packages',
          'behavior', 'world', 'assets', 'build', 'dlc', 'logs')

#: The audits a Skyrim build runs.
SKYRIM_AUDITS = tuple(a for a in AUDITS
                      if a not in ('conditions', 'targets', 'timing', 'properties', 'dlc', 'behavior', 'menus'))

#: The audits a plain run does; `logs` reads the last play session, so it runs only when asked.
DEFAULT_AUDITS = SKYRIM_AUDITS[:-1]

#: The audits a Fallout 4 build runs (fo4_trace reads its play sessions).
FO4_AUDITS = ('quest', 'start', 'dialogue', 'conditions', 'menus', 'targets', 'timing', 'properties', 'packages',
              'behavior', 'world', 'assets', 'build', 'dlc')


def games(output: Path, export: Path, wanted: list) -> list:
    """Built games that have both a plugin and a source export, or `wanted` as given."""
    if wanted:
        return wanted
    return sorted(p.name for p in output.glob('*.es[mp]')
                  if p.is_dir() and (p / p.name).is_file() and (export / p.name).is_dir())


def own_folder(game: str) -> str:
    """The plugin name as a folder, for a game with no scripts to name it."""
    return re.sub(r'[^a-z0-9]', '', Path(game).stem.lower())


class Game:
    """One built game's plugin index, and its quest model built on first use."""

    audits, default = SKYRIM_AUDITS, DEFAULT_AUDITS

    def __init__(self, name: str, args):
        """Read the plugin; the export and scripts load when an audit asks."""
        self.name, self.args = name, args
        self.index = load_plugin(args.output / name / name)
        self._ctx = None

    @property
    def ctx(self):
        """The QuestContext the quest, start and scripts audits share."""
        if self._ctx is None:
            out = self.args.output / self.name
            manifest = quest_progression.load_manifest(out / f'{self.name}.manifest.json')
            self._ctx = quest_progression.QuestContext(self.name, SourceGame(str(self.args.export / self.name)),
                                                       load_scripts(out / 'scripts'), self.index, manifest)
        return self._ctx


class Fo4Game(Game):
    """A Fallout 4 build: the plugin in its mod folder, sources apart from the compiled scripts."""

    audits = default = FO4_AUDITS

    def __init__(self, plugin: Path, args):
        """Read the plugin; its source export is `export/<plugin stem>.esm` unless --fo4-source names one."""
        self.plugin, self.name, self.args = Path(plugin), Path(plugin).name, args
        self.source = args.fo4_source or f'{self.plugin.stem}.esm'
        self.index = load_plugin(self.plugin, FO4_EDID_PREFIX)
        self._ctx, self.parts = None, {}
        self.script_sources = args.fo4_scripts or Path('temp') / 'fo4_scripts' / self.source
        self.masters = built_masters.master_paths(self.plugin, self.index.masters, args.plugin_dirs)

    def dialogue(self) -> Fo4Dialogue:
        """The plugin's dialogue model, its menu links (F3NV.dll's links file) included."""
        return Fo4Dialogue(self.index, menus.plugin_links(self.index, self.plugin)[0])

    @property
    def ctx(self):
        """The QuestContext over the FO4 dialogue model and the ledger's line copies."""
        if self._ctx is None:
            source = SourceGame(str(self.args.export / self.source))
            scripts = load_scripts(self.plugin.parent / 'Scripts', self.script_sources)
            self.parts = line_parts(self.index, ledger_path(self.plugin), source.infos)
            self._ctx = quest_progression.QuestContext(self.name, source, scripts, self.index,
                                                       dialogue=self.dialogue(), copies=line_copies(self.parts),
                                                       left_out=left_out(report_path(self.plugin)))
        return self._ctx


def run_quest(game: Game) -> list:
    """The quest progression findings for one game."""
    return quest_progression.audit(game.ctx)


def run_start(game: Game) -> list:
    """The quest start and alias fill findings for one game."""
    return quest_start.audit(game.ctx)


def run_dialogue(game: Game) -> list:
    """The dialogue loss findings for one game."""
    return dialogue_loss.audit(game.ctx)


def run_conditions(game: Fo4Game) -> list:
    """The condition differential findings for one Fallout 4 build."""
    ctx = game.ctx
    return condition_diff.audit(ctx, game.parts, game.args.export / game.source, ledger_path(game.plugin))


def run_menus(game: Fo4Game) -> list:
    """The dialogue menu links and menu translation findings for one Fallout 4 build."""
    return menus.audit(game.name, game.index, game.plugin, game.masters) + menus.translation_audit(game.name)


def run_timing(game: Fo4Game) -> list:
    """The progress timing findings for one Fallout 4 build."""
    ctx = game.ctx
    return timing.audit(ctx, game.parts, game.args.export / game.source, ledger_path(game.plugin), game.script_sources)


def run_targets(game: Fo4Game) -> list:
    """The quest-stage and actor target findings for one Fallout 4 build."""
    return quest_targets.audit(game.name, game.index, game.masters, game.args.export / game.source, game.script_sources)


def run_dlc(game: Fo4Game) -> list:
    """The DLC override findings for one Fallout 4 build with built masters."""
    return dlc_overrides.audit(game.name, game.index, game.plugin, game.masters, game.args.export / game.source)


def run_properties(game: Fo4Game) -> list:
    """The unfilled script property findings for one Fallout 4 build."""
    dirs = [p.parent for p in game.masters] + list(game.args.plugin_dirs) + built_masters.stamp_dirs(game.plugin)
    return script_props.audit(game.name, game.plugin, dirs, game.script_sources, game.args.export / game.source)


def run_packages(game: Game) -> list:
    """The package and AI findings for one game."""
    return package_ai.audit(game.name, game.index)


def run_behavior(game: Fo4Game) -> list:
    """The left-out package findings for one Fallout 4 build."""
    return behavior.audit(game.name, game.index, game.args.export / game.source, report_path(game.plugin),
                          game.script_sources)


def run_world(game: Game) -> list:
    """The world linkage findings for one game."""
    return world_links.audit(game.name, game.index)


def run_logs(game: Game) -> tuple:
    """The play-test findings for one game, and the previous session's keys for the new tags."""
    found, previous = log_triage.audit(game.ctx, game.args.output, game.args.logs)
    gone = previous - {f.key for f in found}
    if gone:
        print(f'  logs: {len(gone)} causes from the previous session are gone: '
              + ', '.join(sorted(k.split('|', 2)[2] for k in gone)[:6]) + (' ...' if len(gone) > 6 else ''))
    return found, previous


def run_scripts(game: Game) -> list:
    """The script health findings for one game."""
    ctx = game.ctx
    return script_health.audit(game.name, game.index, game.args.output, game.args.export / game.name,
                               ctx.scripts, lambda script: ctx.context_quest(script) or script)


def run_assets(game: Game) -> list:
    """The asset load findings for one game."""
    args = game.args
    if game.index.fo4:
        return asset_fo4.audit(game.name, game.index, game.plugin, FALLOUT4_DIR / 'Data', args.export / game.source)
    own = game.ctx.prefix.rstrip('_').lower() or own_folder(game.name)
    return asset_load.audit(game.name, game.index, args.output / game.name, own, args.export / game.name, args.exe)


def run_build(game: Game) -> list:
    """The drift findings for one game, advancing the baseline while there is none."""
    args = game.args
    path = findings.state_dir(args.output, game.name) / 'build_baseline.json'
    hashes = path.with_name('build_contents.json')
    before, after = build_diff.load_baseline(path), build_diff.snapshot(game.index)
    was, now = build_diff.load_baseline(hashes), build_diff.contents(game.index)
    out = build_diff.audit(game.name, before, after)
    if before is not None:
        build_diff.print_counts('added', build_diff.added(before, after))
    if before is not None and was is not None:
        build_diff.print_counts('changed', build_diff.changed(was, now, after))
    if before is None or not out or args.accept_build:
        build_diff.save_baseline(path, after)
        build_diff.save_baseline(hashes, now)
    if game.index.fo4:
        out += build_history.audit(game.name, path.parent, game.plugin, after, now)
    return [] if args.accept_build else out


#: Each audit's runner, keyed by its name.
RUNNERS = {'quest': run_quest, 'start': run_start, 'dialogue': run_dialogue, 'conditions': run_conditions,
           'targets': run_targets, 'dlc': run_dlc,
           'timing': run_timing, 'scripts': run_scripts, 'properties': run_properties,
           'packages': run_packages, 'world': run_world, 'assets': run_assets, 'build': run_build,
           'behavior': run_behavior, 'menus': run_menus, 'logs': run_logs}


def audit_game(game: Game, args, ledger: dict) -> int:
    """Run the chosen audits on one game, print and file the report; the unhidden error count."""
    print(f'== {game.name} ==')
    folder = findings.state_dir(args.output, game.name)
    report, errors = [], 0
    for audit in [a for a in AUDITS if a in (args.audit or game.default) and a in game.audits]:
        found = RUNNERS[audit](game)
        found, previous = found if isinstance(found, tuple) else (found, findings.load_previous(folder, audit))
        sections = findings.triage(found, ledger, previous)
        findings.save_previous(folder, audit, found)
        errors += len(sections['error'])
        print('\n'.join(findings.render(audit, sections, args.full)))
        report += findings.render(audit, sections, True)
    (folder / 'report.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(f'  full report: {folder / "report.txt"}')
    return errors


def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--game', action='append', default=[], help='a built plugin folder, e.g. Fallout3.esm')
    ap.add_argument('--audit', action='append', choices=AUDITS, help='run only these audits')
    ap.add_argument('--output', type=Path, default=Path('output'))
    ap.add_argument('--export', type=Path, default=Path('export'))
    ap.add_argument('--exe', default=asset_load.DEFAULT_EXE, help='the exe whose RTTI decides which blocks load')
    ap.add_argument('--full', action='store_true', help='print every finding, not the first of each section')
    ap.add_argument('--mark', metavar='KEY', help='decide a finding key or fnmatch pattern')
    ap.add_argument('--as', dest='status', choices=findings.STATUSES, help='the decision for --mark')
    ap.add_argument('--note', default='', help='why, kept in the ledger')
    ap.add_argument('--unmark', metavar='KEY', help='drop a decision from the ledger')
    ap.add_argument('--accept-build', action='store_true', help='accept the current build as the drift baseline')
    ap.add_argument('--logs', type=Path, help='the Papyrus log folder for --audit logs (default: the game\'s)')
    ap.add_argument('--fo4', action='append', default=[], type=Path, help='a built Fallout 4 plugin to audit')
    ap.add_argument('--fo4-source', help='its source export folder name (default: the plugin stem + .esm)')
    ap.add_argument('--plugin-dirs', nargs='+', type=Path, default=[],
                    help='folders holding the built masters (default: the build stamp\'s --plugin-dirs)')
    ap.add_argument('--fo4-scripts', type=Path, help='its converted .psc folder (default: temp/fo4_scripts/<source>)')
    args = ap.parse_args(argv)
    args.audit = args.audit or (['build'] if args.accept_build else None)
    return args


def edit_ledger(args) -> int:
    """Apply --mark or --unmark to the ledger."""
    entries = findings.load_ledger()
    if args.unmark:
        entries.pop(args.unmark, None)
    elif not args.status:
        sys.exit('--mark needs --as ' + '|'.join(findings.STATUSES))
    else:
        entries = findings.mark(entries, args.mark, args.status, args.note)
    findings.save_ledger(entries)
    print(f'ledger: {len(entries)} decisions in {findings.LEDGER}')
    return 0


def main(argv=None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    if args.mark or args.unmark:
        return edit_ledger(args)
    ledger = findings.load_ledger()
    chosen = [] if args.fo4 and not args.game else games(args.output, args.export, args.game)
    makers = [partial(Game, n, args) for n in chosen] + [partial(Fo4Game, p, args) for p in args.fo4]
    errors = sum(audit_game(make(), args, ledger) for make in makers)
    print(f'{errors} unhidden errors' if errors else 'no unhidden errors')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
