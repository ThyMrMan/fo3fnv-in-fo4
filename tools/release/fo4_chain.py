"""The FO4 build chain, watched: base FalloutNV.esm, its faces (--own-facegen), the helpers plugin, F3NV.dll, then
every other built plugin through build_plan --run (The Frontier left out), then the preflight and, when asked, a test
plugin copied into its own mod folder. Each step's output goes to the console and the chain log.

    py -3.14 -m tools.release.fo4_chain                # run, skipping steps finished and still current
    py -3.14 -m tools.release.fo4_chain --check        # the startup checks only
    py -3.14 -m tools.release.fo4_chain --plan         # print build_plan's plan only
    py -3.14 -m tools.release.fo4_chain --fresh --notify --kit <file.esl> --kit-mod <mod folder>

It fails in seconds on a broken setup, stops a step that prints nothing or writes no file for too long, warns when
a step runs past twice its estimate, and stops when the faces no longer belong to the base build.

See: docs/fork/fo4_chain.md
"""

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.pipeline import build_plan, creation_kit, eta, eta_inputs
from fo4_import.pipeline.build_steps import stamp_path
from fo4_import.pipeline.code_tag import ROOT

#: The base plugin, and the mod folder it is built into when fo4_app.json names none.
BASE, DEFAULT_NV = 'FalloutNV.esm', Path(r'D:\Modlists\fo3fnv-in-fo4\mods\F3NV - Fallout New Vegas')
#: Mod folders build_plan --run leaves out (a lowercase part of the folder name).
LEFT_OUT = ('frontier',)
#: The base build's stages profiled by default (the scratch chain's choice); --profile-stages '' turns it off.
PROFILE_STAGES = 'worlds,item WEAP'
#: Programs that must not run during the chain (lowercase image names).
BLOCKING = {'fallout4.exe': 'Fallout 4', 'f4se_loader.exe': 'Fallout 4 (F4SE)', 'modorganizer.exe': 'Mod Organizer 2',
            'creationkit.exe': 'the Creation Kit'}
#: Minutes a step may print nothing, and write no new file in the folders it watches, before it counts as stalled.
NO_OUTPUT_MINUTES, NO_FILE_MINUTES = 45.0, 45.0
#: Seconds between the watchdog's looks at the process, and at the watched folders' newest file.
POLL, FILE_POLL = 5.0, 60.0
#: A step past SLOW_FACTOR times its estimate prints the slow-step alarm.
SLOW_FACTOR = 2.0
#: Gigabytes the build drives need free at least.
MIN_FREE_GB = 40.0
#: Named errors the chain stops with.
STARTUP, STALL_OUTPUT, STALL_FILE, FAILED, FACES_STALE = ('STARTUP_CHECK', 'STALL_NO_OUTPUT', 'STALL_NO_NEW_FILE',
                                                          'STEP_FAILED', 'FACES_NOT_FROM_BASE_BUILD')
#: The chain's exit codes for a failed startup check and a stalled step (a failed step exits with its own code).
EXIT_STARTUP, EXIT_STALL, EXIT_FACES = 2, 124, 6
#: Windows PowerShell toast: title and text come from F3NV_TOAST_TITLE and F3NV_TOAST_TEXT.
TOAST = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]"
         " | Out-Null; $t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
         "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); $x = $t.GetElementsByTagName('text'); "
         "$x.Item(0).AppendChild($t.CreateTextNode($env:F3NV_TOAST_TITLE)) | Out-Null; "
         "$x.Item(1).AppendChild($t.CreateTextNode($env:F3NV_TOAST_TEXT)) | Out-Null; "
         "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
         "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
         ".Show([Windows.UI.Notifications.ToastNotification]::new($t))")


class ChainError(Exception):
    """A named reason the chain stopped (`name`), with its exit code."""

    def __init__(self, name: str, message: str, code: int):
        """Name, message and exit code."""
        super().__init__(f'{name}: {message}')
        self.name, self.code = name, code


@dataclass
class Config:
    """Where everything the chain reads and writes is."""
    root: Path
    export: Path
    sources: Path
    app: Path
    nv: Path
    mo2: Path
    fallout4: Path
    tools: dict
    state: Path
    log: Path
    min_free_gb: float = MIN_FREE_GB

    @property
    def base(self) -> Path:
        """The base plugin in its mod folder."""
        return self.nv / BASE


def _json(path: Path) -> 'dict | None':
    """`path`'s JSON, None when unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def nv_folder(app: Path) -> Path:
    """The FalloutNV.esm mod folder fo4_app.json names, else DEFAULT_NV."""
    named = ((_json(app) or {}).get('per_source', {}).get('falloutnv', {}).get('output', {}).get('path') or '')
    return Path(named) if named else DEFAULT_NV


def default_config() -> Config:
    """This checkout's and this machine's paths."""
    from fo4_import.base.install import FALLOUT4_DIR
    from fo4_import.base.papyrus import FO4_COMPILER
    from fo4_import.face.texture import TEXCONV
    from fo4_import.app.runtime_dll import DIST
    app = Path(os.environ.get('APPDATA', '')) / 'F3NV' / 'fo4_app.json'
    tools = {'the Creation Kit': FALLOUT4_DIR / 'CreationKit.exe', 'the Papyrus compiler': FO4_COMPILER,
             'texconv': TEXCONV, 'Mod Organizer 2': creation_kit.MO2 / 'ModOrganizer.exe', 'F3NV.dll': DIST}
    work = ROOT / 'temp' / 'fo4_chain'
    return Config(ROOT, ROOT / 'export' / BASE, ROOT / 'export' / 'sources.json', app, nv_folder(app),
                  creation_kit.MO2, FALLOUT4_DIR, tools, work / 'state.json', work / 'chain.log')


def others(nv: Path) -> list:
    """Every built plugin in the mod folders beside `nv` except the base and LEFT_OUT's, by its path in its mod."""
    mods, out = nv.parent, set()
    for stamp in mods.glob('*/**/*.build.json'):
        mod = stamp.relative_to(mods).parts[0]
        name = stamp.name[:-len('.build.json')]
        if any(part in mod.lower() for part in LEFT_OUT) or name == BASE:
            continue
        out.add(mods / mod / name)
    return sorted(out)


def missing_paths(cfg: Config) -> list:
    """A line for each configured path that does not exist.
    See: docs/fork/fo4_chain.md#startup
    """
    out = []

    def need(path, what: str) -> None:
        """Note `what` when `path` is missing."""
        if not path or not Path(path).exists():
            out.append(f'{what} is missing: {path}')
    sources = _json(cfg.sources)
    if sources is None:
        out.append(f'the source registry is missing or unreadable: {cfg.sources}')
    for row in (sources or {}).get('directories', []):
        need(row.get('path'), f'source directory "{row.get("label")}" (export/sources.json)')
    for plugin, home in (sources or {}).get('homes', {}).items():
        need(home, f'the home of {plugin} (export/sources.json)')
    app = _json(cfg.app)
    if app is None:
        out.append(f'the app settings are missing or unreadable: {cfg.app}')
    for game, path in (app or {}).get('games', {}).items():
        if path:
            need(path, f'the {game} install named in fo4_app.json')
    for row in (app or {}).get('mod_sources', []):
        if row.get('enabled', True):
            need(row.get('folder'), 'a mod source folder named in fo4_app.json')
    need(cfg.export, 'the FalloutNV.esm export')
    need(cfg.nv, 'the FalloutNV.esm mod folder')
    need(cfg.fallout4 / 'Fallout4.exe', 'the Fallout 4 install')
    need(cfg.mo2, 'the Mod Organizer 2 instance (creation_kit.MO2)')
    for name, path in cfg.tools.items():
        need(path, name)
    return out


def processes() -> set:
    """Lowercase image names of the running processes."""
    listing = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                             **POPEN_FLAGS).stdout
    return {line.split('","')[0].strip('"').lower() for line in listing.splitlines() if line.startswith('"')}


def running_programs(names: set) -> list:
    """A line for each BLOCKING program among the image `names`."""
    return [f'{label} is running ({image}): close it first' for image, label in BLOCKING.items() if image in names]


def low_space(cfg: Config, free=lambda path: shutil.disk_usage(path).free) -> list:
    """A line for each drive of the mod folder and the checkout with under cfg.min_free_gb free."""
    out = []
    for anchor in dict.fromkeys(Path(p).anchor for p in (cfg.nv, cfg.root) if Path(p).anchor):
        gb = free(anchor) / (1 << 30)
        if gb < cfg.min_free_gb:
            out.append(f'drive {anchor} has {gb:.1f} GB free, under {cfg.min_free_gb:.0f} GB')
    return out


def startup_problems(cfg: Config, plugins: list, names: set, free=None) -> list:
    """Every startup check's lines: missing paths, blocking programs, low space, masters from scratch copies.
    See: docs/fork/fo4_chain.md#startup
    """
    out = missing_paths(cfg) + running_programs(names)
    out += low_space(cfg, free) if free else low_space(cfg)
    if not out:
        out += [f'a master would come from a scratch copy: {line}' for line in build_plan.scratch_masters(plugins)]
    return out


@dataclass
class Step:
    """One chain step: a command (argv) or an in-process call, the folders whose new files show it works, the key
    saying it is still current (None: run it), its estimate in seconds (None: none), and its stall limits."""
    name: str
    argv: list = None
    call: object = None
    env: dict = None
    watch: list = field(default_factory=list)
    key: object = lambda: None
    estimate: object = lambda: None
    stamp: Path = None
    fatal: bool = True
    no_output: float = NO_OUTPUT_MINUTES * 60
    no_file: 'float | None' = NO_FILE_MINUTES * 60


def _stat(path: Path) -> str:
    """'size mtime_ns' of `path`, '' when missing."""
    try:
        st = Path(path).stat()
    except OSError:
        return ''
    return f'{st.st_size} {st.st_mtime_ns}'


def code_key(root: Path) -> str:
    """SHA-1 of the checkout's commit and its uncommitted tracked changes."""
    out = hashlib.sha1()
    for args in (['rev-parse', 'HEAD'], ['diff', 'HEAD']):
        out.update(subprocess.run(['git', *args], cwd=root, capture_output=True, **POPEN_FLAGS).stdout)
    return out.hexdigest()


def base_key(cfg: Config) -> 'str | None':
    """The base build on disk when build_plan finds it current, else None."""
    from fo4_import.spike import facegen
    rows = build_plan.plan([cfg.base]) if cfg.base.is_file() else []
    return facegen.base_build(cfg.base) if rows and rows[0][1] == build_plan.CURRENT else None


def faces_key(cfg: Config) -> 'str | None':
    """The finished faces stamp's base build when it is the build on disk, else None."""
    from fo4_import.spike import facegen
    kept = facegen.faces_stamp(cfg.base)
    if not kept or kept.get('status') != 'finished' or facegen.faces_stale(cfg.base):
        return None
    return f'{kept["base_build"]} faces {kept.get("ended")}'


def build_estimate(stamp: Path) -> 'tuple | None':
    """(seconds, {group: seconds}) to rebuild `stamp`'s plugin (eta.planned)."""
    groups = eta.planned(stamp)
    return (sum(groups.values()), groups) if groups else None


def others_estimate(plugins: list) -> 'tuple | None':
    """(seconds, None) build_plan --run should take for the plugins it would build now."""
    rows = [p for p, verdict, _ in build_plan.plan(plugins) if verdict == build_plan.BUILD]
    found = [build_estimate(stamp_path(p)) for p in rows]
    return (sum(f[0] for f in found if f), None) if any(found) else None


def copy_kit(kit: Path, mod: Path) -> None:
    """Copy test plugin `kit` into mod folder `mod` (left unticked in MO2)."""
    mod.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kit, mod / kit.name)
    print(f'test plugin {kit.name} copied into {mod} (not ticked in MO2)', flush=True)


def faces_check(cfg: Config) -> None:
    """Raise when the base plugin's faces are not from its build on disk."""
    from fo4_import.spike import facegen
    reason = facegen.faces_stale(cfg.base)
    if reason:
        raise ChainError(FACES_STALE, f'{BASE}: {reason}', EXIT_FACES)
    print(f'{BASE}: faces belong to build {facegen.base_build(cfg.base)}', flush=True)


def chain_steps(cfg: Config, args: argparse.Namespace) -> list:
    """The chain's steps in order (the scratch chain's order and arguments).
    See: docs/fork/fo4_chain.md#steps
    """
    py, nv, ck_out = [sys.executable], cfg.nv, _ck_output()
    plugins = [cfg.base, *others(nv)]
    plan = py + ['-m', 'fo4_import.pipeline.build_plan', *map(str, plugins)]
    env = dict(os.environ, **({'F3NV_PROFILE_STAGES': args.profile_stages} if args.profile_stages else {}))
    base_argv = py + ['-m', 'fo4_import.pipeline.run', '--export', cfg.export, '--out', cfg.base, '--data', nv,
                      '--scripts', cfg.root / 'temp' / 'fo4_scripts' / BASE, '--mod-sources', cfg.app,
                      '--world', 'WastelandNV', 'reached', '--whole', '--no-test-cell',
                      '--replacements', cfg.root / 'replacements' / 'falloutnv.json', 'GSDocMitchellHouse']
    helpers, dll = nv / 'FalloutHelpers.esl', nv / 'F4SE' / 'Plugins' / 'F3NV.dll'
    steps = [
        Step('base', base_argv, env=env, watch=[nv, cfg.root / 'temp' / 'fo4_scripts', *ck_out],
             key=lambda: base_key(cfg), estimate=lambda: build_estimate(stamp_path(cfg.base)),
             stamp=stamp_path(cfg.base)),
        Step('faces', py + ['-m', 'fo4_import.spike.facegen', '--export', cfg.export, '--data', nv, '--own-facegen',
                            BASE], watch=[nv, *ck_out], key=lambda: faces_key(cfg)),
        Step('helpers', py + ['-m', 'fo4_import.helpers_plugin', '--out', helpers], watch=[nv],
             key=lambda: f'{code_key(cfg.root)} {_stat(helpers)}' if helpers.is_file() else None),
        Step('dll', py + ['-m', 'fo4_import.app.runtime_dll', '--out', nv], watch=[nv],
             key=lambda: f'{_stat(cfg.tools.get("F3NV.dll", ""))} {_stat(dll)}' if dll.is_file() else None),
        Step('plan', plan, no_file=None),
        Step('others', plan + ['--run'], watch=[nv.parent, cfg.root / 'temp' / 'fo4_scripts', *ck_out],
             estimate=lambda: others_estimate(plugins)),
        Step('faces check', call=lambda: faces_check(cfg)),
        Step('preflight', py + ['-m', 'tools.validate.preflight', '--fo4', cfg.base], fatal=False, no_file=None),
    ]
    if args.kit and args.kit_mod:
        steps.append(Step('test plugin', call=lambda: copy_kit(args.kit, args.kit_mod)))
    return steps


def _ck_output() -> list:
    """MO2's folder for the CK's new files, when MO2's settings can be read."""
    try:
        return [creation_kit.output_dir()]
    except (OSError, ValueError, KeyError):
        return []


def _entries(folder: str) -> list:
    """`folder`'s entries, none when it cannot be listed."""
    try:
        with os.scandir(folder) as entries:
            return list(entries)
    except OSError:
        return []


def _mtime(entry: os.DirEntry) -> float:
    """`entry`'s modification time, 0 when it vanished."""
    try:
        return entry.stat().st_mtime
    except OSError:
        return 0.0


def newest(folders: list) -> float:
    """The newest modification time of a file under `folders`, 0 when none."""
    best, stack = 0.0, [str(f) for f in folders if Path(f).is_dir()]
    while stack:
        for entry in _entries(stack.pop()):
            if entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
            else:
                best = max(best, _mtime(entry))
    return best


def spawn(argv: list, env: 'dict | None', cwd: Path) -> subprocess.Popen:
    """Start `argv` with its output (unbuffered, stderr joined) readable line by line."""
    env = dict(env or os.environ, PYTHONUNBUFFERED='1')
    return subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', **POPEN_FLAGS)


def kill_tree(proc) -> None:
    """End `proc` and its children."""
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True, **POPEN_FLAGS)


def close_ck() -> None:
    """Close the CK if a stalled step left it running."""
    if creation_kit.running():
        creation_kit.close()


def toast(title: str, text: str) -> None:
    """A Windows desktop notification; nothing when PowerShell cannot show one."""
    env = dict(os.environ, F3NV_TOAST_TITLE=title, F3NV_TOAST_TEXT=text)
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', TOAST], env=env, capture_output=True, timeout=30,
                       **POPEN_FLAGS)
    except (OSError, subprocess.SubprocessError):
        pass


@dataclass
class Hooks:
    """What the runner does to the outside world, replaceable in tests."""
    clock: object = time.time
    sleep: object = time.sleep
    spawn: object = spawn
    newest: object = newest
    kill: object = kill_tree
    close_ck: object = close_ck
    notify: object = None
    out: object = None


class State:
    """Each step's last result, kept in a JSON file: status, key, seconds, end time.
    See: docs/fork/fo4_chain.md#resume
    """

    def __init__(self, path: Path, fresh: bool = False):
        """Read `path` (nothing when `fresh`)."""
        self.path = Path(path)
        self.steps = {} if fresh else ((_json(self.path) or {}).get('steps', {}))

    def current(self, step: Step) -> bool:
        """Whether `step` passed last time and its key still says so (a key that cannot be read: no)."""
        kept = self.steps.get(step.name, {})
        if kept.get('status') != 'passed' or kept.get('key') is None:
            return False
        return kept['key'] == _safe(step.key)

    def last_seconds(self, name: str) -> 'float | None':
        """How long step `name` took when it last passed."""
        kept = self.steps.get(name, {})
        return kept.get('seconds') if kept.get('status') == 'passed' else kept.get('passed_seconds')

    def record(self, step: Step, status: str, seconds: float, key=None) -> None:
        """Keep `step`'s result and write the file."""
        old = self.steps.get(step.name, {})
        row = {'status': status, 'key': key, 'seconds': round(seconds, 1), 'ended': time.strftime('%Y-%m-%d %H:%M:%S')}
        if status != 'passed' and old.get('status') == 'passed':
            row['passed_seconds'] = old.get('seconds')
        self.steps[step.name] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'steps': self.steps}, indent=1) + '\n', encoding='utf-8')


class Runner:
    """Runs the steps in order under the watchdog, recording each result in State.
    See: docs/fork/fo4_chain.md#watchdog
    """

    def __init__(self, cfg: Config, state: State, hooks: Hooks = None, notify: bool = False):
        """Run `cfg`'s steps, resuming from `state`."""
        self.cfg, self.state, self.hooks = cfg, state, hooks or Hooks()
        self.notify_on = notify
        self.log = None

    def emit(self, line: str) -> None:
        """Print `line` and add it to the chain log."""
        line = line.rstrip('\n')
        (self.hooks.out or (lambda text: print(text, flush=True)))(line)
        if self.log:
            self.log.write(line + '\n')
            self.log.flush()

    def notify(self, title: str, text: str) -> None:
        """A desktop notification when asked for."""
        if self.notify_on:
            (self.hooks.notify or toast)(title, text)

    def estimate(self, step: Step) -> tuple:
        """(seconds, {group: seconds} or None) step's estimate: its own, else its last passing run's time (an
        estimate that cannot be made is noted, never fatal)."""
        found = _safe(step.estimate, lambda e: self.emit(f'(no estimate for {step.name}: {e})'))
        if found:
            return found
        seconds = self.state.last_seconds(step.name)
        return (seconds, None) if seconds else (None, None)

    def run(self, steps: list) -> int:
        """Run `steps`, skipping current ones; 0, or the exit code of the error that stopped them."""
        self.cfg.log.parent.mkdir(parents=True, exist_ok=True)
        with self.cfg.log.open('a', encoding='utf-8') as self.log:
            self.emit(f'===== chain started {time.strftime("%Y-%m-%d %H:%M:%S")}')
            for step in steps:
                try:
                    self.step(step)
                except ChainError as e:
                    self.emit(f'===== chain stopped: {e}')
                    self.notify('F3NV build chain stopped', str(e)[:200])
                    return e.code
            self.emit('===== chain finished')
            self.notify('F3NV build chain finished', 'every step passed')
        return 0

    def step(self, step: Step) -> None:
        """Run one step unless it is current; raise ChainError when it fails or stalls."""
        if self.state.current(step):
            self.emit(f'===== {step.name}: current, skipped')
            return
        seconds, groups = self.estimate(step)
        note = f' (estimate {eta.minutes(seconds)})' if seconds else ''
        self.emit(f'===== {step.name}: {" ".join(map(str, step.argv)) if step.argv else "in process"}{note}')
        started = self.hooks.clock()
        try:
            code, slow = self.call(step) if step.call else self.watch(step, seconds)
        except ChainError as e:
            self.state.record(step, 'stalled' if e.code == EXIT_STALL else 'failed', self.hooks.clock() - started)
            raise
        took = self.hooks.clock() - started
        self.emit(f'===== {step.name}: exit {code} after {took:.0f} s')
        if slow:
            self.slow_advice(step, groups)
        if code:
            self.state.record(step, 'failed', took)
            if step.fatal:
                raise ChainError(FAILED, f'step {step.name} exited with {code}', code)
            return
        self.state.record(step, 'passed', took, self._key(step))

    def _key(self, step: Step):
        """The step's key after it passed (None: a restart runs it again)."""
        return _safe(step.key, lambda e: self.emit(f'(no resume key for {step.name}: {e})'))

    def call(self, step: Step) -> tuple:
        """(0, False) after the in-process step; ChainError passes through, another error is the step's failure."""
        try:
            step.call()
        except ChainError:
            raise
        except Exception as e:
            self.emit(f'{step.name} failed: {type(e).__name__}: {e}')
            return 1, False
        return 0, False

    def watch(self, step: Step, estimate: 'float | None') -> tuple:
        """(exit code, ran slow) of the step's process, ended with ChainError when it prints nothing for
        step.no_output seconds or writes no new file in step.watch for step.no_file seconds."""
        h = self.hooks
        started = h.clock()
        proc = h.spawn(step.argv, step.env, self.cfg.root)
        last = {'out': started, 'file': started, 'looked': started}
        lines = queue.Queue()

        def read() -> None:
            """Pass each output line on, stamping when it came."""
            for line in proc.stdout:
                last['out'] = h.clock()
                lines.put(line)
            lines.put(None)
        reader = threading.Thread(target=read, name=f'{step.name} output', daemon=True)
        reader.start()
        slow = False
        while True:
            self._drain(lines)
            if proc.poll() is not None:
                break
            h.sleep(POLL)
            now = h.clock()
            if step.no_file is not None and now - last['looked'] >= FILE_POLL:
                last['looked'], found = now, h.newest(step.watch)
                last['file'] = max(last['file'], found)
            if now - last['out'] > step.no_output:
                self._stall(proc, step, STALL_OUTPUT, f'{step.name} printed nothing for {(now - last["out"]) / 60:.0f}'
                            f' min (limit {step.no_output / 60:.0f})')
            if step.no_file is not None and now - last['file'] > step.no_file:
                self._stall(proc, step, STALL_FILE, f'{step.name} wrote no new file in {_names(step.watch)} for '
                            f'{(now - last["file"]) / 60:.0f} min (limit {step.no_file / 60:.0f})')
            if estimate and not slow and now - started > SLOW_FACTOR * estimate:
                slow = True
                self.emit(f'SLOW: {step.name} has run {eta.minutes(now - started)}, over {SLOW_FACTOR:g} times its '
                          f'estimate of {eta.minutes(estimate)}')
                self.notify(f'F3NV chain: {step.name} is slow', f'{eta.minutes(now - started)} so far, '
                            f'estimate {eta.minutes(estimate)}')
        reader.join(timeout=10)
        self._drain(lines)
        return proc.returncode, slow

    def _drain(self, lines: queue.Queue) -> None:
        """Emit the output lines read so far."""
        while True:
            try:
                line = lines.get_nowait()
            except queue.Empty:
                return
            if line is not None:
                self.emit(line)

    def _stall(self, proc, step: Step, name: str, message: str) -> None:
        """End the stalled step's process (and a CK it left), notify, raise."""
        self.emit(f'{name}: {message}; ending it')
        self.hooks.kill(proc)
        self.hooks.close_ck()
        raise ChainError(name, message, EXIT_STALL)

    def slow_advice(self, step: Step, groups: 'dict | None') -> None:
        """After a slow step: which stages to profile in the next run (F3NV_PROFILE_STAGES)."""
        found = eta_inputs.record_build(step.stamp) if step.stamp and groups else None
        stages = eta.overran(groups, found[0]) if found else []
        if stages:
            self.emit(f'SLOW: {step.name} ran past its estimate most in {", ".join(stages)}: next run, '
                      f'--profile-stages "{",".join(stages)}" (F3NV_PROFILE_STAGES) to see why')
        else:
            self.emit(f'SLOW: {step.name}: next run, set F3NV_PROFILE_STAGES (--profile-stages) to the stages its '
                      f'"stage" lines show as slowest')


def _safe(fn, noted=lambda e: None):
    """`fn()`, or None after passing its exception to `noted`."""
    try:
        return fn()
    except Exception as e:
        noted(e)
        return None


def _names(folders: list) -> str:
    """Folders `folders`, joined for a message."""
    return ', '.join(str(f) for f in folders) or 'no folder'


def main() -> None:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true', help='Run the startup checks only')
    ap.add_argument('--plan', action='store_true', help="Print build_plan's plan only")
    ap.add_argument('--fresh', action='store_true', help='Forget earlier results: run every step')
    ap.add_argument('--notify', action='store_true', help='Show a desktop notification when the chain stops or ends')
    ap.add_argument('--profile-stages', default=PROFILE_STAGES, help='F3NV_PROFILE_STAGES for the base build')
    ap.add_argument('--no-output-minutes', type=float, default=NO_OUTPUT_MINUTES)
    ap.add_argument('--no-file-minutes', type=float, default=NO_FILE_MINUTES)
    ap.add_argument('--min-free-gb', type=float, default=MIN_FREE_GB)
    ap.add_argument('--kit', type=Path, help='A test plugin to copy into --kit-mod after every step passed')
    ap.add_argument('--kit-mod', type=Path, help='The mod folder for --kit')
    args = ap.parse_args()
    cfg = default_config()
    cfg.min_free_gb = args.min_free_gb
    plugins = [cfg.base, *others(cfg.nv)]
    problems = startup_problems(cfg, plugins, processes())
    if problems:
        print(f'{STARTUP}: the chain cannot start:\n  ' + '\n  '.join(problems), flush=True)
        if args.notify:
            toast('F3NV build chain did not start', problems[0][:200])
        sys.exit(EXIT_STARTUP)
    if args.check:
        print('startup checks passed')
        return
    if args.plan:
        sys.exit(subprocess.call([sys.executable, '-m', 'fo4_import.pipeline.build_plan', *map(str, plugins)],
                                 cwd=cfg.root))
    steps = chain_steps(cfg, args)
    for step in steps:
        step.no_output = args.no_output_minutes * 60
        step.no_file = None if step.no_file is None else args.no_file_minutes * 60
    sys.exit(Runner(cfg, State(cfg.state, args.fresh), notify=args.notify).run(steps))


if __name__ == '__main__':
    main()
