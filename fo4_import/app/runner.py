"""Running the Convert screen's stages: one command after another from the repo folder, each output line handed
on as it arrives, stopping at the first failure or when asked. No Qt here; the window runs this on a thread.

See: docs/fork/fo4_gui.md#app-shape
"""

import os
import subprocess
import time
from dataclasses import dataclass

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.app.stages import REPO

#: Output lines worth repeating on the Finished screen: replacement fallbacks and errors.
WARNING_MARKS = ('replacements:', 'Traceback', 'Error', 'ERROR', 'FAILED')


@dataclass
class Result:
    """How one stage ended: its key and label, exit code (None when stopped) and seconds taken."""
    key: str
    label: str
    code: 'int | None'
    seconds: float


class Runner:
    """Runs a stage plan (fo4_import.app.stages.plan); stop() ends the running stage."""

    def __init__(self, plan: list, env: 'dict | None' = None):
        """Runs `plan` [(key, label, argv or a function giving it)] with `env` added."""
        self.plan, self.process, self.stopped, self.warnings, self.env = plan, None, False, [], env or {}

    def run(self, on_line) -> list:
        """Run each stage in order, calling `on_line(text)` per output line; the Results, up to a failure."""
        results = []
        for key, label, argv in self.plan:
            on_line(f'=== {label}')
            started = time.time()
            code = self._one(argv() if callable(argv) else argv, on_line)
            results.append(Result(key, label, code, time.time() - started))
            on_line(f'=== {label}: ' + ('stopped' if code is None else 'done' if code == 0 else f'failed ({code})'))
            if code != 0:
                break
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
