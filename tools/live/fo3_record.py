"""Record Fallout 3 itself playing an opening, as the story runs' answer key (the recorder test).

    python -m tools.live.fo3_record --fallout3 "C:\\Program Files\\GOG Galaxy\\Games\\Fallout 3" --seconds 240 \\
        --menu "coc Vault101d" --cell "startquest CG00;setstage CG00 0" --until "stage\\|CG00\\|[^|]*\\|10$"

Installs F3Recorder.dll into the game's Data\\FOSE\\Plugins, starts the game with FOSE
(Fallout3.exe itself when the Anniversary patcher made it load FOSE, else fose_loader.exe)
with the recorder's settings, prints the timeline as it grows, and closes the game when
`--until` matches a line or `--seconds` pass. Needs Fallout 3 1.7.0.3 (FOSE refuses
Steam's 1.7.0.4) and FOSE 1.3 beta 2.

See: docs/fork/fo4_story_tests.md#baseline
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / 'tes_runtime' / 'fo3_test' / 'bin' / 'F3Recorder.dll'
#: Seconds the recorder has to write its first line before the run is called failed.
START_SECONDS = 120


def install(fallout3: Path) -> None:
    """Copies the recorder plugin into the game's FOSE plugin folder."""
    plugins = fallout3 / 'Data' / 'FOSE' / 'Plugins'
    plugins.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PLUGIN, plugins / PLUGIN.name)


def launcher(fallout3: Path) -> Path:
    """Fallout3.exe when it loads FOSE itself, else fose_loader.exe."""
    exe = fallout3 / 'Fallout3.exe'
    return exe if b'fose_1_7.dll' in exe.read_bytes() else fallout3 / 'fose_loader.exe'


def launch(fallout3: Path, out: Path, menu: str, cell: str) -> None:
    """Starts the game with FOSE and the recorder writing to `out`."""
    env = dict(os.environ, F3_RECORD=str(out), F3_RECORD_MENU=menu, F3_RECORD_CELL=cell)
    out.unlink(missing_ok=True)
    subprocess.Popen([str(launcher(fallout3))], cwd=fallout3, env=env)


def stop() -> None:
    """Closes the game."""
    subprocess.run(['taskkill', '/im', 'Fallout3.exe', '/f'], capture_output=True)


def follow(out: Path, seconds: float, until) -> tuple:
    """Prints the timeline as it grows; (lines, matched) once `until` matches or time is up."""
    lines, offset, start, matched = [], 0, time.time(), False
    while not matched and time.time() - start < seconds:
        if not lines and time.time() - start > START_SECONDS:
            break
        if out.is_file():
            with open(out, 'rb') as f:
                f.seek(offset)
                chunk = f.read()
            text = chunk[:chunk.rfind(b'\n') + 1]
            offset += len(text)
            for line in text.decode('utf-8', 'replace').splitlines():
                print(line, flush=True)
                lines.append(line)
                matched = matched or bool(until and until.search(line))
        time.sleep(0.5)
    return lines, matched


def summary(lines: list) -> str:
    """How many of each kind of line, and every fault."""
    kinds = Counter(line.split('|')[1] for line in lines if line.count('|') >= 1)
    faults = [line for line in lines if '|fault|' in line]
    return 'kinds: %s\n%s' % (dict(sorted(kinds.items())), '\n'.join(faults) or 'no faults')


def record(args) -> int:
    """Installs, launches, follows and closes; 0 when the recorder ran and `--until` (if any) matched."""
    install(args.fallout3)
    launch(args.fallout3, args.out, args.menu, args.cell)
    until = re.compile(args.until) if args.until else None
    try:
        lines, matched = follow(args.out, args.seconds, until)
    finally:
        stop()
    if not lines:
        print('the recorder wrote nothing: is the exe 1.7.0.3 and FOSE 1.3 beta 2?')
        return 1
    print(summary(lines))
    return 0 if matched or not until else 1


def parse_args(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--fallout3', type=Path, required=True, help='the Fallout 3 install')
    ap.add_argument('--out', type=Path, default=REPO / 'temp' / 'fo3_record' / 'f3_timeline.log')
    ap.add_argument('--seconds', type=float, default=300)
    ap.add_argument('--menu', default='', help="console lines, ';'-separated, run at the main menu")
    ap.add_argument('--cell', default='', help='console lines run once the player is first in a cell')
    ap.add_argument('--until', default='', help='a regex: stop when a timeline line matches')
    return ap.parse_args(argv)


if __name__ == '__main__':
    sys.exit(record(parse_args()))
