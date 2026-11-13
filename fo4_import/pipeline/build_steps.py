"""The steps around a build: converting the FNV scripts it reads, and the stamp beside the plugin saying what the
build holds and whether it finished.

See: docs/fork/fo4_pipeline.md#build-stamp
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from core.build_resources import profile_cores
from core.subprocess_flags import POPEN_FLAGS
from core.worker_budget import WORKERS_ENV_VAR
from fo4_import.base.build_files import moved_in
from fo4_import.pipeline.build_inputs import leave_out
from script_convert.ownership import OWNED_SUFFIX

ROOT = Path(__file__).resolve().parents[2]
#: The stamp's file name ending, after the plugin's name.
STAMP_SUFFIX = '.build.json'


def convert_scripts(export_dir: Path, scripts_dir: Path) -> None:
    """Convert the export's scripts into `scripts_dir` (script_convert.pipeline): every build, as the compile
    after it recompiles only scripts whose text changed. Its workers are the resource profile's unless
    TESCONV_WORKERS says otherwise. Other plugins' script lists beside it stay out of the build's record.
    See: docs/fork/fo4_plugin_layout.md#owned-lists
    """
    started = time.time()
    leave_out([scripts_dir.parent, *scripts_dir.parent.glob(f'*{OWNED_SUFFIX}')])
    cmd = [sys.executable, '-m', 'script_convert.pipeline', str(export_dir), '-o', str(scripts_dir),
           '--target', 'fallout4']
    env = {**os.environ, WORKERS_ENV_VAR: os.environ.get(WORKERS_ENV_VAR) or str(profile_cores())}
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, **POPEN_FLAGS)
    if done.returncode:
        print(done.stdout[-4000:] + done.stderr[-4000:])
        raise SystemExit(f'script conversion failed ({done.returncode}): {" ".join(cmd)}')
    print(f'scripts converted in {time.time() - started:.1f}s')


def stamp_path(plugin: Path) -> Path:
    """`plugin`'s stamp, in the build records beside it (build_files)."""
    return moved_in(plugin.with_name(plugin.name + STAMP_SUFFIX))


def _git(*args: str) -> str:
    """A git command's output in the repo, or '' when git fails."""
    try:
        done = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, **POPEN_FLAGS)
    except OSError:
        return ''
    return done.stdout if done.returncode == 0 else ''


def source_state() -> dict:
    """The commit the build starts from and the files then differing from it (git status)."""
    changed = [line[3:] for line in _git('status', '--porcelain', '--untracked-files=no').splitlines() if line]
    return {'commit': _git('rev-parse', 'HEAD').strip(), 'changed files': sorted(changed)}


def write_stamp(plugin: Path, status: str, started: float, extra: dict) -> None:
    """The stamp: `status` (running, finished, failed), when the build started and ended, and `extra`."""
    body = {'status': status, 'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started)),
            'ended': None if status == 'running' else time.strftime('%Y-%m-%d %H:%M:%S'), **extra}
    path = stamp_path(plugin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
