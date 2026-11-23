"""Run the Fallout 4 story cases on a dedicated test machine, from this one, over SSH.

On this PC:
    python -m tools.live.fo4_laptop setup --host laptop --repo "C:\\F3NV" --mo2 "D:\\Modlists\\fo3fnv-in-fo4"
    python -m tools.live.fo4_laptop push              # send what changed: this checkout, test DLLs, the mods
    python -m tools.live.fo4_laptop run tests/story/fo3_opening [--set SEX=male] [--from CASE] ...
    python -m tools.live.fo4_laptop record --seconds 300 --menu "coc <cell>" ...  # Fallout 3 itself
    python -m tools.live.fo4_laptop fetch [--out DIR] # the run's Papyrus, F4SE and crash logs, the timeline
    python -m tools.live.fo4_laptop query "sqo FNV_VCG01"   # a console line in the game a run kept (status, stop)

`push` sends only files whose size or time differ, as one tar stream, and
removes files gone from a pushed mod folder. `push --profile "New Vegas"` and
`run --profile "New Vegas" ...` use another MO2 profile than the saved one. `run` and `record` start the game
through a scheduled task, so it opens on the logged-in desktop (a program
started over SSH cannot), visible and in front, and stream the run's log.
The test machine needs: OpenSSH Server with this PC's key, Python 3.14 with
requirements.txt, Steam (offline is fine), Fallout 4 with F4SE, the MO2
folder, and a logged-in session that never sleeps or locks; `record` also
needs Fallout 3 1.7.0.3 with FOSE 1.3 beta 2 (`setup --fallout3`).

See: docs/fork/fo4_story_tests.md#laptop
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from core.mod_sources import enabled_mods, mo2_layout, profile_dir
from fo4_import.app import settings as S
from tools.dialog.tes4_ctda_dump import XEDIT_DEFS
from tools.live import fo4_test_instance as T
from tools.validate.fo4_install_check import machine_from

REPO = T.REPO
SYSTEM32 = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
#: Windows' own tools: Git's GNU tar reads `C:` in a path as a remote host.
TAR, SSH = str(SYSTEM32 / 'tar.exe'), str(SYSTEM32 / 'OpenSSH' / 'ssh.exe')
#: The test machine's tar, by full path for the same reason.
REMOTE_TAR = r'"%SystemRoot%\System32\tar.exe"'
CONFIG = S.config_dir() / 'fo4_laptop.json'
TASK = 'F3NVStoryCases'
#: Stops the story-case runner the task started, which `schtasks /end` leaves running.
RUNNER_KILL = ('powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object '
               "{ $_.CommandLine -match 'tools.live.fo4_story_cases' -and $_.Name -eq 'python.exe' } | "
               'ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"')
PROFILE_FILES = ('modlist.txt', 'plugins.txt', 'loadorder.txt', 'fallout4.ini', 'fallout4prefs.ini',
                 'fallout4custom.ini')
#: What `fetch` brings back from the instance profile.
LOG_PATHS = ('Documents/My Games/Fallout4/Logs/Script', 'Documents/My Games/Fallout4/F4SE', 'run.log')
#: Where a Fallout 3 recording keeps its task files, log and timeline on the test machine.
RECORD_DIR = REPO / 'temp' / 'fo3_record'
#: The test DLL folders `push` sends beside the checkout.
TEST_BINS = ('tes_runtime/fo4_test/bin', 'tes_runtime/fo3_test/bin')
#: The files under the ignored references/ that the code reads at import time.
READ_REFERENCES = tuple('references/xEdit/Core/' + name for name in XEDIT_DEFS.values())
#: The ignored folders of generated case files (fo4_stage_sweep, and with --routes) a run may name.
GENERATED_CASES = ('temp/stage_sweep', 'temp/route_sweep')


# ---------------------------------------------------------------------------
#  This PC
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """The saved test machine (host, repo, mo2, profile)."""
    if not CONFIG.is_file():
        raise SystemExit('no test machine set up; run `setup` first')
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def cmdline(args) -> str:
    """`args` as one cmd.exe command line: quoted where cmd would split or pipe them."""
    return ' '.join('"%s"' % a.replace('"', '\\"') if not a or any(c in a for c in ' \t|&<>^();,') else a
                    for a in args)


def remote(cfg: dict, *args: str) -> list:
    """The ssh command running this module with `args` on the test machine."""
    command = 'cd /d "%s" && py -3.14 -u -m tools.live.fo4_laptop %s' % (cfg['repo'], cmdline(args))
    return [SSH, '-o', 'BatchMode=yes', cfg['host'], command]


def ask(cfg: dict, payload, *args: str):
    """Runs a test-machine command with `payload` as JSON on its stdin; the JSON it printed last."""
    done = subprocess.run(remote(cfg, *args), input=json.dumps(payload).encode('utf-8'), capture_output=True)
    if done.returncode:
        raise SystemExit('%s failed on %s: %s' % (args[0], cfg['host'], done.stderr.decode('utf-8', 'replace')))
    return json.loads(done.stdout.decode('utf-8').strip().splitlines()[-1])


def stats(root: Path, rels) -> dict:
    """{rel: [size, whole-second mtime]} of the files `rels` under `root` that exist."""
    out = {}
    for rel in rels:
        path = root / rel
        if path.is_file():
            st = path.stat()
            out[rel] = [st.st_size, int(st.st_mtime)]
    return out


def tree(root: Path, folders) -> list:
    """Every file under each of `folders`, as `/` paths relative to `root`."""
    return [p.relative_to(root).as_posix() for folder in folders for p in (root / folder).rglob('*') if p.is_file()]


def has_checkout(cfg: dict) -> bool:
    """Whether the test machine holds this tool yet, to answer `stat`."""
    probe = 'if exist "%s\\tools\\live\\fo4_laptop.py" echo yes' % cfg['repo']
    done = subprocess.run([SSH, '-o', 'BatchMode=yes', cfg['host'], probe], capture_output=True)
    return b'yes' in done.stdout


def send(cfg: dict, local_root: Path, remote_root: str, rels: list, prune: tuple = (), fresh: bool = False) -> None:
    """Sends the `rels` under `local_root` that differ on the test machine (all of them when `fresh`),
    and removes there what `prune` folders hold that `rels` does not."""
    local = stats(local_root, rels)
    there = {} if fresh else ask(cfg, {'files': list(local), 'under': list(prune)}, 'stat', '--root', remote_root)
    changed = [r for r in local if r not in there or there[r][0] != local[r][0] or there[r][1] < local[r][1]]
    stale = [r for r in there if r not in local]
    if stale:
        ask(cfg, stale, 'remove', '--root', remote_root)
    if changed:
        listing = Path(os.environ.get('TEMP', '.')) / 'f3nv_push.txt'
        listing.write_text('\n'.join(changed) + '\n', encoding='utf-8')
        pack = subprocess.Popen([TAR, '-c', '-f', '-', '-C', str(local_root), '-T', str(listing)],
                                stdout=subprocess.PIPE)
        unpack = subprocess.run([SSH, '-o', 'BatchMode=yes', cfg['host'], '(if not exist "%s" mkdir "%s") & %s -x -f - -C "%s"'
                                 % (remote_root, remote_root, REMOTE_TAR, remote_root)], stdin=pack.stdout)
        pack.stdout.close()
        if pack.wait() or unpack.returncode:
            raise SystemExit('sending %s failed' % local_root)
    size = sum(local[r][0] for r in changed)
    print('%s: %d sent (%.1f MB), %d removed, %d unchanged' % (
        local_root, len(changed), size / 2 ** 20, len(stale), len(local) - len(changed)))


def checkout_files() -> list:
    """This checkout's files as git sees them (tracked and new, ignored left out), the test DLLs, the
    generated cases and the reference files the code reads."""
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=REPO, capture_output=True, check=True).stdout.decode('utf-8').split('\0')
    dlls = [p.relative_to(REPO).as_posix() for folder in TEST_BINS for p in (REPO / folder).glob('*.dll')]
    cases = [p.relative_to(REPO).as_posix() for folder in GENERATED_CASES for p in (REPO / folder).rglob('*.f4test')]
    return [rel for rel in listed if rel] + dlls + cases + list(READ_REFERENCES)


def push(cfg: dict) -> int:
    """Stops a game a run kept (it locks the bridge's DLLs), then sends this checkout (removing the generated cases
    it no longer has), the profile's enabled mods and its profile files to the test machine; 0."""
    general, folders = mo2_layout(machine_from(S.load()).mo2)
    profile = profile_dir(general, folders, cfg['profile'])
    fresh = not has_checkout(cfg)
    if not fresh:
        stop(cfg)
    send(cfg, REPO, cfg['repo'], checkout_files(), GENERATED_CASES, fresh=fresh)
    mods = enabled_mods(profile / 'modlist.txt')
    send(cfg, folders['mods'], cfg['mo2'] + '\\mods', tree(folders['mods'], mods), tuple(mods))
    send(cfg, profile, '%s\\profiles\\%s' % (cfg['mo2'], cfg['profile']), list(PROFILE_FILES))
    return 0


def run(cfg: dict, case_args: list) -> int:
    """The story cases on the test machine (game kept on a failure); exit code."""
    keep = [] if '--keep' in case_args else ['--keep-on-fail']
    return subprocess.run(remote(cfg, 'local-run', '--mo2', cfg['mo2'], '--profile', cfg['profile'],
                                 '--', *keep, *case_args)).returncode


def record(cfg: dict, record_args: list) -> int:
    """Records Fallout 3 on the test machine; the recording's exit code."""
    if not cfg.get('fallout3'):
        raise SystemExit('no Fallout 3 folder set up; run `setup ... --fallout3 DIR`')
    return subprocess.run(remote(cfg, 'local-record', '--fallout3', cfg['fallout3'], '--', *record_args)).returncode


def instance(cfg: dict, args: list) -> int:
    """A fo4_test_instance command on the test machine's game; its code."""
    return subprocess.run(remote(cfg, 'local-instance', '--', *args)).returncode


def stop(cfg: dict) -> int:
    """Ends the run task, the case runner it leaves (RUNNER_KILL), then the game."""
    subprocess.run([SSH, '-o', 'BatchMode=yes', cfg['host'], 'schtasks /end /tn %s' % TASK], capture_output=True)
    subprocess.run([SSH, '-o', 'BatchMode=yes', cfg['host'], RUNNER_KILL], capture_output=True)
    return instance(cfg, ['stop'])


def fetch(cfg: dict, out: Path) -> int:
    """Copies the last run's logs from the test machine into `out`; 0."""
    out.mkdir(parents=True, exist_ok=True)
    pack = subprocess.Popen(remote(cfg, 'pack-logs'), stdout=subprocess.PIPE)
    unpack = subprocess.run([TAR, '-x', '-f', '-', '-C', str(out)], stdin=pack.stdout)
    pack.stdout.close()
    pack.wait()
    print('logs in %s' % out)
    return unpack.returncode


# ---------------------------------------------------------------------------
#  The test machine
# ---------------------------------------------------------------------------

def stat_command(root: Path) -> int:
    """Prints {rel: [size, mtime]} for the stdin JSON's `files` and every file under its `under` folders."""
    asked = json.load(sys.stdin)
    root.mkdir(parents=True, exist_ok=True)
    print(json.dumps(stats(root, asked['files'] + tree(root, [u for u in asked['under'] if (root / u).is_dir()]))))
    return 0


def remove_command(root: Path) -> int:
    """Deletes the files the stdin JSON list names under `root`; prints how many."""
    names = json.load(sys.stdin)
    for rel in names:
        (root / rel).unlink(missing_ok=True)
    print(json.dumps(len(names)))
    return 0


def module(name: str, args: list) -> str:
    """The command line running this checkout's module `name` with `args`."""
    return '"%s" -u -m %s %s' % (sys.executable, name, cmdline(args))


def task_script(folder: Path, commands: list) -> Path:
    """Writes `folder`/run.cmd: `commands` in turn while they succeed, output to run.log, exit code to run.done."""
    log = folder / 'run.log'
    lines = ['@echo off', 'cd /d "%s"' % REPO, 'type nul > "%s"' % log]
    lines += ['if not errorlevel 1 %s >> "%s" 2>&1' % (command, log) for command in commands]
    lines.append('echo %%errorlevel%% > "%s"' % (folder / 'run.done'))
    script = folder / 'run.cmd'
    script.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
    return script


def follow(log: Path, done: Path) -> int:
    """Prints `log` as it grows (its bytes as written, so no character is split or unprintable) until `done`
    appears; the exit code `done` holds."""
    offset, started = 0, time.time()
    while True:
        finished = done.is_file()
        if log.is_file():
            with open(log, 'rb') as f:
                f.seek(offset)
                chunk = f.read()
            offset += len(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        elif time.time() - started > 60:
            raise SystemExit('the run never started: is a user logged on to the desktop?')
        if finished:
            return int(done.read_text().strip() or 1)
        time.sleep(1)


def start_task(folder: Path, commands: list) -> int:
    """Runs `commands` in the logged-on desktop session through a scheduled task and follows them."""
    folder.mkdir(parents=True, exist_ok=True)
    for stale in (folder / 'run.log', folder / 'run.done'):
        stale.unlink(missing_ok=True)
    script = task_script(folder, commands)
    subprocess.run(['schtasks', '/create', '/f', '/tn', TASK, '/sc', 'once', '/st', '00:00', '/it',
                    '/tr', '"%s"' % script], check=True, capture_output=True)
    subprocess.run(['schtasks', '/run', '/tn', TASK], check=True, capture_output=True)
    return follow(folder / 'run.log', folder / 'run.done')


def local_run(mo2: str, profile: str, case_args: list) -> int:
    """Builds the instance and runs the story cases visibly; their exit code."""
    build = module('tools.live.fo4_test_instance', ['build', '--mo2', mo2, '--profile', profile])
    cases = module('tools.live.fo4_story_cases', ['--visible', *case_args])
    return start_task(T.Instance(1, visible=True).profile, [build, cases])


def local_record(fallout3: str, record_args: list) -> int:
    """Records Fallout 3 on the desktop; the recording's exit code."""
    out = RECORD_DIR / 'f3_timeline.log'
    return start_task(RECORD_DIR, [module('tools.live.fo3_record',
                                          ['--fallout3', fallout3, '--out', str(out), *record_args])])


def pack_logs() -> int:
    """Writes the instance profile's logs and the Fallout 3 recording to stdout as a tar stream; tar's exit code."""
    root = T.Instance(1, visible=True).profile
    present = [rel for rel in LOG_PATHS if (root / rel).exists()]
    recorded = ['-C', str(RECORD_DIR.parent), RECORD_DIR.name] if RECORD_DIR.is_dir() else []
    sys.stdout.flush()
    return subprocess.run([TAR, '-c', '-f', '-', '-C', str(root), *present, *recorded],
                          stdout=sys.stdout.buffer).returncode


# ---------------------------------------------------------------------------
#  Command line
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('setup')
    for name in ('host', 'repo', 'mo2'):
        setup.add_argument('--' + name, required=True)
    setup.add_argument('--profile', default='Fallout 3')
    setup.add_argument('--fallout3', default='', help='the Fallout 3 install, for `record`')
    for name in ('push', 'run'):
        sub.add_parser(name).add_argument('--profile', default='', help='MO2 profile instead of the saved one')
    sub.choices['run'].add_argument('case_args', nargs=argparse.REMAINDER)
    sub.add_parser('record').add_argument('case_args', nargs=argparse.REMAINDER)
    sub.add_parser('fetch').add_argument('--out', type=Path, default=REPO / 'temp' / 'laptop_logs')
    for name in ('stat', 'remove'):
        sub.add_parser(name).add_argument('--root', type=Path, required=True)
    local = sub.add_parser('local-run')
    local.add_argument('--mo2', required=True)
    local.add_argument('--profile', required=True)
    local.add_argument('case_args', nargs=argparse.REMAINDER)
    local_rec = sub.add_parser('local-record')
    local_rec.add_argument('--fallout3', required=True)
    local_rec.add_argument('case_args', nargs=argparse.REMAINDER)
    sub.add_parser('pack-logs')
    sub.add_parser('query').add_argument('text', help='a console line for the game a run kept (--keep-on-fail)')
    ask = sub.add_parser('ask', help="one bridge command for the kept game, e.g. ask invoke 'SPECIALMenu editingName'")
    ask.add_argument('cmd')
    ask.add_argument('text', nargs='?', default='')
    sub.add_parser('status')
    sub.add_parser('stop')
    sub.add_parser('local-instance').add_argument('case_args', nargs=argparse.REMAINDER)
    return ap.parse_args(argv)


def save_setup(args) -> int:
    """Saves the test machine's address and folders; 0."""
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({k: getattr(args, k) for k in ('host', 'repo', 'mo2', 'profile', 'fallout3')},
                                 indent=2),
                      encoding='utf-8')
    print('saved %s' % CONFIG)
    return 0


def chosen_profile(args) -> dict:
    """The saved test machine, with `--profile` in place of its profile when given."""
    cfg = load_config()
    return {**cfg, 'profile': args.profile or cfg['profile']}


def main(argv=None) -> int:
    """Runs one command; its exit code."""
    args = parse_args(argv)
    rest = [a for a in getattr(args, 'case_args', []) if a != '--']
    commands = {
        'setup': lambda: save_setup(args),
        'push': lambda: push(chosen_profile(args)),
        'run': lambda: run(chosen_profile(args), rest),
        'record': lambda: record(load_config(), rest),
        'fetch': lambda: fetch(load_config(), args.out),
        'stat': lambda: stat_command(args.root),
        'remove': lambda: remove_command(args.root),
        'local-run': lambda: local_run(args.mo2, args.profile, rest),
        'local-record': lambda: local_record(args.fallout3, rest),
        'pack-logs': pack_logs,
        'query': lambda: instance(load_config(), ['console', args.text]),
        'ask': lambda: instance(load_config(), ['request', args.cmd, args.text]),
        'status': lambda: instance(load_config(), ['status']),
        'stop': lambda: stop(load_config()),
        'local-instance': lambda: T.main(['--visible', *rest]),
    }
    return commands[args.command]()


if __name__ == '__main__':
    sys.exit(main())
