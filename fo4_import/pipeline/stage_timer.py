"""Seconds each build stage takes, its own time only: a stage run inside another is taken out of the outer one,
so the stages add up to the build.

    @timed('people')
    def _people(...): ...

    for line in report(): print(line)

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import functools
import time

_spent: dict = {}
_stack: list = []


def timed(name: str):
    """Decorate a build stage: its calls add their own seconds to `name`."""
    def wrap(fn):
        """`fn`, timed under `name`."""
        @functools.wraps(fn)
        def run(*args, **kwargs):
            """Call `fn`, charging its time less its nested stages' to `name`."""
            _stack.append(0.0)
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                took = time.perf_counter() - started
                nested = _stack.pop()
                _spent[name] = _spent.get(name, 0.0) + took - nested
                if _stack:
                    _stack[-1] += took
        return run
    return wrap


def charged(name: str, fn, *args):
    """`fn(*args)`, its time charged to stage `name` (a name known only at the call, such as a record type)."""
    return timed(name)(fn)(*args)


def report() -> list:
    """'stage <name>: <seconds>s' lines in first-run order, then their total."""
    lines = [f'stage {name}: {spent:.1f}s' for name, spent in _spent.items()]
    return lines + [f'stage total: {sum(_spent.values()):.1f}s']
