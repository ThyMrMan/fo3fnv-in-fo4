"""An isolated Fallout 4 for headless, automated in-game tests.

    python -m tools.live.fo4_test_instance build [--profile "Fallout 3"] [--slot N]
    python -m tools.live.fo4_test_instance launch | status | stop | shot [--out x.png]
    python -m tools.live.fo4_test_instance console "coc QASmoke"
    python -m tools.live.fo4_test_instance smoke [--cell QASmoke]

`build` makes the instance folder from HARD LINKS to Fallout 4's own files,
F4SE, the test bridge and the mods an MO2 profile enables (its plugins.txt
and INIs too). Small config files are copied, so nothing the game writes
reaches the mod folders. `launch` starts it muted on a hidden desktop with
My Games and LocalAppData redirected (TESSandbox.dll), so it never touches
the player's screen, input, INIs, saves or logs. Slots 2+ run beside slot 1.

See: docs/fork/fo4_story_tests.md#instance
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

from core.mod_sources import enabled_mods, mo2_layout, profile_dir
from fo4_import.app import settings as S
from tools.live import hidden_launch
from tools.live.game_bridge import Bridge, BridgeError
from tools.validate.fo4_install_check import machine_from

REPO = Path(__file__).resolve().parents[2]
TEST_BIN = REPO / 'tes_runtime' / 'fo4_test' / 'bin'
#: Our UI DLLs whose debug logging the instance turns on (each reads `[Log] iLevel` from its own Plugins ini).
DEBUG_LOGS = ('CleanroomDialogue', 'CleanroomUI')
APP_ID = '377160'
WINDOW_CLASS = 'Fallout4'
#: Game-root files the game and F4SE use, linked where the install has them; CK files and proxy DLLs stay out.
ROOT_FILES = ('Fallout4.exe', 'steam_api64.dll', 'bink2w64.dll', 'd3dcompiler_46.dll',
              'GFSDK_GodraysLib.x64.dll', 'GFSDK_SSAO_D3D11.win64.dll', 'cudart64_75.dll',
              'flexExtRelease_x64.dll', 'flexRelease_x64.dll', 'nvToolsExt64_1.dll',
              'Fallout4_Default.ini', 'Low.ini', 'Medium.ini', 'High.ini', 'Ultra.ini')
#: Data files of the base game and its DLCs; Creation Club content stays out.
VANILLA_PREFIXES = ('fallout4', 'dlc')
VANILLA_SUFFIXES = ('.esm', '.ba2', '.cdx', '.csg')
#: Files the game or its plugins may rewrite: copied, never hard-linked into a mod folder.
COPIED_SUFFIXES = ('.ini', '.json', '.toml', '.txt', '.yaml')
INIS = ('Fallout4.ini', 'Fallout4Prefs.ini', 'Fallout4Custom.ini')
#: Tick unfocused, no intro, the Papyrus log on, saves in the sandbox, loose files and plugins.txt honored.
CUSTOM_INI = (('General', 'bAlwaysActive', '1'), ('General', 'sIntroSequence', ''),
              ('General', 'sLocalSavePath', 'Saves\\'), ('General', 'bUseMyGamesDirectory', '1'),
              ('Papyrus', 'bEnableLogging', '1'), ('Papyrus', 'bEnableTrace', '1'),
              ('Papyrus', 'bLoadDebugInformation', '1'), ('Archive', 'bInvalidateOlderFiles', '1'),
              ('Archive', 'sResourceDataDirsFinal', ''), ('Launcher', 'bEnableFileSelection', '1'),
              ('Bethesda.net', 'bEnablePlatform', '0'))
#: A small window; silence (volume 0 keeps sound-timed lines real); subtitles, which the trace records.
PREFS_INI = (('Display', 'bFull Screen', '0'), ('Display', 'bBorderless', '1'),
             ('Display', 'iSize W', '640'), ('Display', 'iSize H', '360'),
             ('AudioMenu', 'fAudioMasterVolume', '0.0000'), ('Interface', 'bDialogueSubtitles', '1'),
             ('Interface', 'bGeneralSubtitles', '1'), ('Launcher', 'bEnableFileSelection', '1'))


# ---------------------------------------------------------------------------
#  Instance
# ---------------------------------------------------------------------------

class Instance:
    """The folders, pipe and desktop of test instance `slot` (1 = the first)."""

    def __init__(self, slot: int = 1, fallout4: 'Path | None' = None, visible: bool = False):
        """Slot 1 lives in `<drive>\\Fallout 4 Test`, slot N in `... N`, on Fallout 4's drive (hard links).

        `visible` runs it on the user's own desktop, in front (a dedicated test machine).
        """
        self.fallout4 = Path(fallout4 or machine_from(S.load()).fallout4)
        self.visible = visible
        suffix = '' if slot == 1 else ' %d' % slot
        self.root = Path(self.fallout4.drive + os.sep) / ('Fallout 4 Test' + suffix)
        self.data = self.root / 'Data'
        self.profile = self.root / '_profile'
        self.documents = self.profile / 'Documents'
        self.local_appdata = self.profile / 'LocalAppData'
        self.my_games = self.documents / 'My Games' / 'Fallout4'
        self.pipe = r'\\.\pipe\f3nv_test' + suffix.strip()
        self.desktop = 'Default' if visible else 'F3NVTest' + suffix.strip()

    def path(self, name: str) -> Path:
        """`name` inside the sandbox profile."""
        return self.profile / name


# ---------------------------------------------------------------------------
#  Build
# ---------------------------------------------------------------------------

def place(src: Path, dst: Path, made: list) -> None:
    """Hard-links `src` to `dst` (copies a config file), replacing what is there; records `dst` in `made`."""
    if dst.exists():
        dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in COPIED_SUFFIXES:
        shutil.copy2(src, dst)
    else:
        os.link(src, dst)
    made.append(str(dst))


def place_tree(src: Path, dst: Path, made: list) -> int:
    """Places every file under `src` at the same path under `dst`, MO2's hidden files and meta.ini left out."""
    count = 0
    for folder, _dirs, files in os.walk(src):
        rel = Path(folder).relative_to(src)
        for name in files:
            if name.endswith('.mohidden') or (rel == Path('.') and name.lower() == 'meta.ini'):
                continue
            place(Path(folder) / name, dst / rel / name, made)
            count += 1
    return count


def vanilla_files(data: Path) -> list:
    """The base game's and DLCs' plugins and archives in `data`."""
    return [p for p in data.iterdir() if p.is_file() and p.name.lower().startswith(VANILLA_PREFIXES)
            and p.suffix.lower() in VANILLA_SUFFIXES]


def clear(inst: Instance) -> None:
    """Removes every file an earlier build placed (only those: links go, the sources stay)."""
    listed = inst.path('placed.txt')
    if listed.is_file():
        for name in listed.read_text(encoding='utf-8').splitlines():
            if os.path.isfile(name):
                os.remove(name)


def set_ini(text: str, settings) -> str:
    """`text` with each (section, key, value) in `settings` set, adding what is missing."""
    lines = text.splitlines()
    for section, key, value in settings:
        header = '[%s]' % section.lower()
        start = next((i for i, line in enumerate(lines) if line.strip().lower() == header), None)
        if start is None:
            lines += ['[%s]' % section, '%s=%s' % (key, value)]
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('[')), len(lines))
        hit = next((i for i in range(start + 1, end)
                    if lines[i].split('=', 1)[0].strip().lower() == key.lower()), None)
        if hit is None:
            lines.insert(start + 1, '%s=%s' % (key, value))
        else:
            lines[hit] = '%s=%s' % (key, value)
    return '\n'.join(lines) + '\n'


def apply_ini(inst: Instance, name: str, settings) -> None:
    """Sets `settings` in the sandbox INI `name`."""
    path = inst.my_games / name
    text = path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''
    path.write_text(set_ini(text, settings), encoding='utf-8')


def write_profile(inst: Instance, mo2_profile: Path) -> None:
    """The sandbox's INIs (the MO2 profile's, then the test settings) and Plugins.txt."""
    inst.my_games.mkdir(parents=True, exist_ok=True)
    for name in INIS:
        source = mo2_profile / name.lower()
        if source.is_file():
            shutil.copyfile(source, inst.my_games / name)
    apply_ini(inst, 'Fallout4Custom.ini', CUSTOM_INI)
    apply_ini(inst, 'Fallout4Prefs.ini', PREFS_INI)
    plugins = inst.local_appdata / 'Fallout4' / 'Plugins.txt'
    plugins.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mo2_profile / 'plugins.txt', plugins)


def debug_log(ini: Path, made: list) -> None:
    """Gives the instance its own copy of DLL setting file `ini` (a placed one is a link into a mod, left as it is)
    with `[Log] iLevel=3`, debug logging, unless it sets a log level already."""
    text = ini.read_text(encoding='utf-8', errors='replace') if ini.is_file() else ''
    if '[Log]' in text:
        return
    ini.unlink(missing_ok=True)
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text(text.rstrip('\n') + '\n\n[Log]\niLevel=3\n', encoding='utf-8')
    if str(ini) not in made:
        made.append(str(ini))


def build(inst: Instance, mo2: Path, profile: str) -> None:
    """Stops a game a run kept, links the game, F4SE, the test bridge and the profile's mods into the instance,
    and writes its profile."""
    general, folders = mo2_layout(mo2)
    mo2_profile = profile_dir(general, folders, profile)
    stop(inst)
    clear(inst)
    made = []
    for name in ROOT_FILES + tuple(p.name for p in inst.fallout4.glob('f4se_1_*.dll')):
        if (inst.fallout4 / name).is_file() or name == 'Fallout4.exe':
            place(inst.fallout4 / name, inst.root / name, made)
    for path in vanilla_files(inst.fallout4 / 'Data'):
        place(path, inst.data / path.name, made)
    for folder in (p for p in (inst.fallout4 / 'Data').iterdir() if p.is_dir()):
        place_tree(folder, inst.data / folder.name, made)
    mods = list(reversed(enabled_mods(mo2_profile / 'modlist.txt')))
    for mod in mods:
        place_tree(folders['mods'] / mod, inst.data, made)
    place(TEST_BIN / 'F3NVTest.dll', inst.data / 'F4SE' / 'Plugins' / 'F3NVTest.dll', made)
    for name in DEBUG_LOGS:
        debug_log(inst.data / 'F4SE' / 'Plugins' / f'{name}.ini', made)
    (inst.root / 'steam_appid.txt').write_text(APP_ID)
    inst.profile.mkdir(parents=True, exist_ok=True)
    inst.path('placed.txt').write_text('\n'.join(made), encoding='utf-8')
    write_profile(inst, mo2_profile)
    print('built %s: %d files, %d mods from profile %r' % (inst.root, len(made), len(mods), mo2_profile.name))


# ---------------------------------------------------------------------------
#  Run
# ---------------------------------------------------------------------------

def running_pid(inst: Instance) -> int:
    """The pid of the running instance, or 0."""
    try:
        pid = int(inst.path('pid.txt').read_text().strip())
    except (OSError, ValueError):
        return 0
    return pid if hidden_launch.process_image(pid) else 0


def launch(inst: Instance, extra_env: 'dict | None' = None) -> int:
    """Starts the instance hidden, muted, sandboxed and under F4SE; refuses a second copy. Its pid."""
    if running_pid(inst):
        sys.exit('test instance already running (pid %d)' % running_pid(inst))
    apply_ini(inst, 'Fallout4Custom.ini', CUSTOM_INI)
    apply_ini(inst, 'Fallout4Prefs.ini', PREFS_INI)
    env = {'SteamAppId': APP_ID, 'SteamGameId': APP_ID, 'F3NV_TEST_PIPE': inst.pipe,
           'TES_SANDBOX_MUTE': '1', 'TES_SANDBOX_DOCUMENTS': str(inst.documents),
           'TES_SANDBOX_LOCALAPPDATA': str(inst.local_appdata), **(extra_env or {})}
    f4se = next(inst.root.glob('f4se_1_*.dll'))
    pid = hidden_launch.launch(str(inst.root / 'Fallout4.exe'), str(inst.root), inst.desktop,
                               [str(TEST_BIN / 'TESSandbox.dll'), (str(f4se), 1)], env)
    inst.path('pid.txt').write_text(str(pid))
    print('launched pid %d on desktop %s' % (pid, inst.desktop))
    return pid


def focus(inst: Instance) -> None:
    """Brings a visible instance's window to the front, where Fallout 4 keeps loading."""
    if inst.visible and not hidden_launch.bring_to_front(inst.desktop, WINDOW_CLASS):
        print('no %s window to bring to the front' % WINDOW_CLASS)


def stop(inst: Instance) -> int:
    """Kills the running instance (only a process whose exe is inside the instance); 0."""
    pid = running_pid(inst)
    if pid and hidden_launch.terminate(pid, str(inst.root)):
        print('stopped pid %d' % pid)
    return 0


def tail(path: Path, lines: int) -> list:
    """The last `lines` lines of `path`, or [] when it does not exist."""
    try:
        return path.read_text(encoding='utf-8', errors='replace').splitlines()[-lines:]
    except OSError:
        return []


def status(inst: Instance) -> int:
    """Prints whether the instance runs, its log tails and the bridge's state; 0 when it answers."""
    pid = running_pid(inst)
    print('process: %s' % ('pid %d' % pid if pid else 'not running'))
    for log in (inst.documents / 'TESSandbox.log', inst.my_games / 'F4SE' / 'f4se.log',
                inst.my_games / 'F4SE' / 'F3NVTest.log'):
        print('--- %s' % log)
        for line in tail(log, 8):
            print('    ' + line)
    try:
        with Bridge(pipe=inst.pipe, timeout=5) as bridge:
            print('bridge: %s' % bridge.status())
            return 0
    except BridgeError as err:
        print('bridge: %s' % err)
        return 1


def shot(inst: Instance, path: Path) -> int:
    """Saves a screenshot of the hidden game window to `path`; 0."""
    image = hidden_launch.capture(inst.desktop, WINDOW_CLASS)
    if image is None:
        sys.exit('no game window on desktop %s' % inst.desktop)
    image.save(path)
    print('saved %s' % path)
    return 0


def console(inst: Instance, text: str) -> int:
    """Runs one console line in the running instance and prints what it printed; 0."""
    with Bridge(pipe=inst.pipe, timeout=30, loading_retries=1) as bridge:
        print(send(bridge, text))
    return 0


def request(inst: Instance, cmd: str, text: str) -> int:
    """Prints the running bridge's answer to one command (`invoke`...); 0."""
    with Bridge(pipe=inst.pipe, timeout=30, loading_retries=1) as bridge:
        print(bridge.request(cmd, text=text))
    return 0


def connect(inst: Instance, seconds: float) -> Bridge:
    """A bridge connection once the game answers `ping`, polling up to `seconds`."""
    deadline = time.time() + seconds
    while True:
        try:
            bridge = Bridge(pipe=inst.pipe, timeout=30, loading_retries=1).connect()
            bridge.ping()
            return bridge
        except BridgeError:
            if time.time() > deadline or not running_pid(inst):
                raise
            time.sleep(1)


def send(bridge: Bridge, text: str) -> str:
    """Runs console `text` once; its output, or '' while a load holds the main thread (the line still runs)."""
    try:
        return bridge.console(text)
    except BridgeError as err:
        if err.code != 'E_LOADING':
            raise
        return ''


def at_main_menu(state: dict) -> bool:
    """Main menu up and loaded, and the player made (a `coc` before crashes)."""
    return 'MainMenu' in state['menus'] and 'LoadingMenu' not in state['menus'] and bool(state.get('player'))


def wait_status(bridge: Bridge, ready, seconds: float) -> dict:
    """Polls the bridge's status until `ready(status)` holds; the last status. Raises on timeout."""
    deadline = time.time() + seconds
    while True:
        try:
            state = bridge.status()
        except BridgeError as err:
            if err.code != 'E_LOADING':
                raise
            state = {'menus': ['LoadingMenu'], 'cell': ''}
        if ready(state):
            return state
        if time.time() > deadline:
            raise BridgeError('timed out waiting; last status %s' % state, 'E_TIMEOUT')
        time.sleep(1)


def game_hour(bridge: Bridge) -> float:
    """The GameHour global, read through the console."""
    return float(bridge.console('GetGlobalValue GameHour').rsplit('>>', 1)[1])


def smoke(inst: Instance, cell: str) -> int:
    """Launches, runs smoke_checks, and always stops the game; 0 when every check passes."""
    launch(inst)
    try:
        return smoke_checks(inst, cell)
    finally:
        stop(inst)


def smoke_checks(inst: Instance, cell: str) -> int:
    """Waits for the main menu, coc into `cell`, checks game time runs and screenshots; 0 when all pass."""
    started = time.time()
    with connect(inst, 180) as bridge:
        print('bridge up after %.1fs' % (time.time() - started))
        wait_status(bridge, at_main_menu, 180)
        print('main menu after %.1fs' % (time.time() - started))
        focus(inst)
        print('coc -> %r' % send(bridge, 'coc %s' % cell).strip(), flush=True)
        state = wait_status(bridge, lambda s: s['cell'] and 'LoadingMenu' not in s['menus'], 180)
        print('in %s (%s) after %.1fs; menus %s' % (state['cell_name'], state['cell'], time.time() - started,
                                                   state['menus']))
        bridge.console('set timescale to 1000')
        before = game_hour(bridge)
        time.sleep(2)
        advanced = game_hour(bridge) - before
    shot(inst, inst.path('smoke.png'))
    papyrus = inst.my_games / 'Logs' / 'Script' / 'Papyrus.0.log'
    checks = {'game time advanced %.3f h in 2 s' % advanced: advanced > 0.1,
              'Papyrus log written in the sandbox': papyrus.is_file()}
    for name, ok in checks.items():
        print('%s  %s' % ('ok  ' if ok else 'FAIL', name))
    return 0 if all(checks.values()) else 1


# ---------------------------------------------------------------------------
#  Command line
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--slot', type=int, default=1, help='instance number; 2+ run beside the first')
    ap.add_argument('--visible', action='store_true', help='run on the desktop, in front (a dedicated machine)')
    sub = ap.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--mo2', type=Path, help="MO2 instance (default: the app's MO2 mod source)")
    b.add_argument('--profile', default='Fallout 3', help='MO2 profile whose mods and plugins to use')
    for name in ('launch', 'status', 'stop'):
        sub.add_parser(name)
    sub.add_parser('shot').add_argument('--out', type=Path, default=Path('fo4_test_shot.png'))
    sub.add_parser('console').add_argument('text')
    r = sub.add_parser('request')
    r.add_argument('cmd')
    r.add_argument('text', nargs='?', default='')
    sub.add_parser('smoke').add_argument('--cell', default='QASmoke')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    """Runs one command on instance `--slot`; its exit code."""
    args = parse_args(argv)
    inst = Instance(args.slot, visible=args.visible)
    commands = {
        'build': lambda: build(inst, args.mo2 or machine_from(S.load()).mo2, args.profile) or 0,
        'launch': lambda: launch(inst) and 0,
        'stop': lambda: stop(inst),
        'status': lambda: status(inst),
        'shot': lambda: shot(inst, args.out),
        'console': lambda: console(inst, args.text),
        'request': lambda: request(inst, args.cmd, args.text),
        'smoke': lambda: smoke(inst, args.cell),
    }
    return commands[args.command]()


if __name__ == '__main__':
    sys.exit(main())
