"""Seconds each build stage takes, its own time only: a stage run inside another is taken out of the outer one,
so the stages add up to the build; and, while sample() runs, the peak memory of the main process and of the other
processes in the build's job (pool workers, tools) during each stage's own time.

    @timed('people')
    def _people(...): ...

    stop = sample()
    ...
    stop()
    for line in report(): print(line)

See: docs/fork/fo4_plugin_layout.md#stage-times
See: docs/fork/fo4_build_resources.md#stage-memory
"""

import functools
import threading
import time

from core.process_memory import job_commits, own_commit

#: Seconds between memory samples.
SAMPLE_SECONDS = 0.5
#: The name memory sampled outside every stage is charged to.
OUTSIDE = 'outside stages'
GB = 1 << 30
_spent: dict = {}
#: [stage name, seconds of the stages nested in it so far] of each running stage, innermost last.
_stack: list = []
#: {stage name: [main process peak, workers' summed peak, largest worker, most worker processes]} in bytes.
_peaks: dict = {}
#: Callables told (stage name, seconds of this call) when a stage call ends.
LISTENERS: list = []


def timed(name: str):
    """Decorate a build stage: its calls add their own seconds to `name`."""
    def wrap(fn):
        """`fn`, timed under `name`."""
        @functools.wraps(fn)
        def run(*args, **kwargs):
            """Call `fn`, charging its time less its nested stages' to `name`."""
            _stack.append([name, 0.0])
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                took = time.perf_counter() - started
                nested = _stack.pop()[1]
                _spent[name] = _spent.get(name, 0.0) + took - nested
                if _stack:
                    _stack[-1][1] += took
                for listener in LISTENERS:
                    listener(name, took - nested)
        return run
    return wrap


def charged(name: str, fn, *args):
    """`fn(*args)`, its time charged to stage `name`."""
    return timed(name)(fn)(*args)


def note(main: 'int | None', workers: list) -> None:
    """Charge one memory reading (main process bytes, each worker's bytes) to the innermost running stage."""
    running = list(_stack)
    peak = _peaks.setdefault(running[-1][0] if running else OUTSIDE, [0, 0, 0, 0])
    for i, value in enumerate((main or 0, sum(workers), max(workers, default=0), len(workers))):
        peak[i] = max(peak[i], value)


def sample() -> 'callable':
    """Start reading memory every SAMPLE_SECONDS on a daemon thread; the function that stops it (one last read)."""
    stop = threading.Event()

    def loop():
        """Read and note until stopped."""
        while not stop.wait(SAMPLE_SECONDS):
            note(own_commit(), job_commits())

    thread = threading.Thread(target=loop, name='stage memory', daemon=True)
    thread.start()

    def finish():
        """Stop the thread after a last reading."""
        stop.set()
        thread.join()
        note(own_commit(), job_commits())
    return finish


def _memory(peak) -> str:
    """', peak <main> GB main, <workers> GB in <n> workers' of a _peaks value, or '' for none."""
    main, workers, _largest, count = peak or (0, 0, 0, 0)
    if not main:
        return ''
    return f', peak {main / GB:.2f} GB main' + (f', {workers / GB:.2f} GB in {count} workers' if count else '')


def report() -> list:
    """'stage <name>: <s>s[, peaks]' lines in run order, then the total."""
    lines = [f'stage {name}: {spent:.1f}s{_memory(_peaks.get(name))}' for name, spent in _spent.items()]
    whole = [max(column) for column in zip(*_peaks.values())] if _peaks else None
    return lines + [f'stage total: {sum(_spent.values()):.1f}s{_memory(whole)}']


def records() -> dict:
    """{stage name: {seconds, peak_main_gb, peak_workers_gb, largest_worker_gb, workers}} in first-run order; the
    memory keys only for a stage a reading fell in (OUTSIDE included)."""
    out = {name: {'seconds': round(spent, 1)} for name, spent in _spent.items()}
    for name, (main, workers, largest, count) in _peaks.items():
        out.setdefault(name, {}).update(peak_main_gb=round(main / GB, 2), peak_workers_gb=round(workers / GB, 2),
                                        largest_worker_gb=round(largest / GB, 2), workers=count)
    return out
