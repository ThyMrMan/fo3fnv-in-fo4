"""Running the Convert screen's stages: one command after another from the repo folder, each output line handed
on as it arrives and written to one run log in logs/ (core.run_log), stopping at the first failure or when asked.
No Qt here; the window runs this on a thread.

See: docs/fork/fo4_gui.md#app-shape
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from asset_convert import paths as data_paths
from core import run_log
from core.subprocess_flags import POPEN_FLAGS
from fo4_import.app.stages import REPO
from fo4_import.base import release

#: Output lines worth repeating on the Finished screen: replacement fallbacks and errors.
WARNING_MARKS = ('replacements:', 'Traceback', 'Error', 'ERROR', 'FAILED')


@dataclass
class Result:
    """How one stage ended: its key and label, exit code (None when stopped) and seconds taken."""
    key: str
    label: str
    code: 'int | None'
    seconds: float


def open_log(name: str, data: 'str | None' = None) -> 'run_log.RunLog | None':
    """A new run log in logs/ of folder `data` (else this checkout) named for `name` (the oldest beyond run_log's
    default count removed); None when logs/ can't be written."""
    folder = run_log.logs_root(Path(data or REPO) / 'logs')
    if not run_log.prune(folder):
        return None
    log = run_log.RunLog(run_log.free_log_path(folder, name), {'Release': release.current(), 'From': 'the app'})
    return log if log.active else None


class Runner:
    """Runs a stage plan (fo4_import.app.stages.plan); stop() ends the running stage."""

    def __init__(self, plan: list, env: 'dict | None' = None, name: str = ''):
        """Runs `plan` [(key, label, argv or its maker)] with `env`, logged as `name`."""
        self.plan, self.process, self.stopped, self.warnings, self.env = plan, None, False, [], env or {}
        self.name = name

    def run(self, on_line) -> list:
        """Run each stage in order, calling `on_line(text)` per output line and writing it to the run log; the
        Results, up to a failure."""
        log = open_log(self.name, self.env.get(data_paths.DATA_ENV))
        if log is not None:
            self.env = {**self.env, run_log.RUN_LOG_ENV_VAR: str(log.path)}

        def line(text: str) -> None:
            """One line to the log and the window."""
            if log is not None:
                log.write_line(text)
            on_line(text)
        results = []
        for key, label, argv in self.plan:
            line(f'=== {label}')
            started = time.time()
            code = self._one(argv() if callable(argv) else argv, line)
            results.append(Result(key, label, code, time.time() - started))
            line(f'=== {label}: ' + ('stopped' if code is None else 'done' if code == 0 else f'failed ({code})'))
            if code != 0:
                break
        if log is not None:
            log.close('done' if results and all(r.code == 0 for r in results) else 'stopped or failed')
        return results

    def _one(self, argv: list, on_line) -> 'int | None':
        """Run one command, streaming its output; its exit code, or None when stopped."""
        if self.stopped:
            return None
        env = {**os.environ, **self.env, 'PYTHONUNBUFFERED': '1', 'PYTHONIOENCODING': 'utf-8'}
        self.process = subprocess.Popen(argv, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding='utf-8', errors='replace', **POPEN_FLAGS)
        for line in self.process.stdout:
            line = line.rstrip('\r\n')
            if any(mark in line for mark in WARNING_MARKS):
                self.warnings.append(line)
            on_line(line)
        code = self.process.wait()
        return None if self.stopped else code

    def stop(self) -> None:
        """End the running stage and run no more."""
        self.stopped = True
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
