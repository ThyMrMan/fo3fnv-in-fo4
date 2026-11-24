"""The Convert screen's activity line: its wording, and CpuWatch's CPU use on real child processes."""
import subprocess
import sys
import time

import pytest

from core.process_job import CpuWatch
from fo4_import.app.runner import activity

BUSY = 'import time\nend = time.time() + 1.5\nwhile time.time() < end: pass'
#: A child that starts a grandchild leaving the job, as MO2 starts the Creation Kit.
BREAKAWAY = ('import subprocess, sys\n'
             "r = subprocess.run([sys.executable, '-c', 'pass'], creationflags=0x01000000)\n"
             'sys.exit(r.returncode)')
windows = pytest.mark.skipif(sys.platform != 'win32', reason='Windows job objects')


def test_wording():
    """Quiet time, then busy, idle or unknown CPU, each in plain words."""
    assert activity(2, None) == 'Output arriving.'
    assert activity(130, (6.42, 9)) == 'No new output for 2 min 10 s; still working: 6.4 cores busy across 9 processes.'
    assert activity(45, (0.0, 1)).startswith('No new output for 45 s; the build is not using the CPU')


def _watched(code: str) -> tuple:
    """(first sample, sample after the child ends, exit code) for a watched child running `code`."""
    watch = CpuWatch()
    child = subprocess.Popen([sys.executable, '-c', code])
    assert watch.add(child.pid)
    first = watch.sample()
    code = child.wait(timeout=60)
    time.sleep(0.2)
    after = watch.sample()
    watch.close()
    return first, after, code


@windows
def test_a_busy_child_shows_cores():
    """A child spinning for 1.5 s reads as busy; the first sample has no baseline."""
    first, (cores, running), code = _watched(BUSY)
    assert first is None and code == 0
    assert cores > 0.3 and running == 0


@windows
def test_an_idle_child_reads_idle():
    """A sleeping child uses next to no CPU."""
    watch = CpuWatch()
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'])
    assert watch.add(child.pid)
    time.sleep(1)
    watch.sample()
    time.sleep(1)
    cores, running = watch.sample()
    child.wait(timeout=60)
    watch.close()
    assert cores < 0.05 and running == 1


@windows
def test_a_child_may_still_break_away():
    """A watched child can still start a program outside the job."""
    assert _watched(BREAKAWAY)[2] == 0
