"""Which repo functions ran in this process: sys.monitoring (PEP 669) reports each function's first start and is
told not to report it again, so it costs one event per function. capture() collects what runs inside it (it
re-arms the reports first), for a cache entry keyed on the code that made it.

See: docs/fork/fo4_plugin_layout.md#code-identity
"""

import atexit
import contextlib
import sys

from fo4_import.pipeline.code_identity import SEP, hashes, relative

#: This module's sys.monitoring tool id and name (0-2 and 5 are the debugger, coverage, profiler, optimizer slots).
TOOL, NAME = 4, 'f3nv ran code'
#: The recording's own files (its audit hook runs inside every capture): never part of what made a value.
RECORDERS = frozenset(f'fo4_import/pipeline/{name}.py' for name in ('build_inputs', 'ran_code', 'code_identity',
                                                                     'code_tag'))
#: Every repo function key that ran in this process since start().
RAN = set()
_CAPTURES = []


def _started(code, offset: int):
    """Record `code`'s first start: a repo function or class body (not a lambda, comprehension, module, or the
    __annotate__ Python makes for annotations, which its class or function's identity holds)."""
    rel = relative(code.co_filename)
    if rel is not None and rel not in RECORDERS and not code.co_qualname.endswith(('>', '__annotate__')):
        key = rel + SEP + code.co_qualname
        RAN.add(key)
        for seen in tuple(_CAPTURES):
            seen.add(key)
    return sys.monitoring.DISABLE


def start() -> None:
    """Report repo functions' first starts in this process from now on (again harmless)."""
    if sys.monitoring.get_tool(TOOL) == NAME:
        return
    sys.monitoring.use_tool_id(TOOL, NAME)
    sys.monitoring.register_callback(TOOL, sys.monitoring.events.PY_START, _started)
    sys.monitoring.set_events(TOOL, sys.monitoring.events.PY_START)
    atexit.register(stop)


def stop() -> None:
    """Stop reporting (at exit, before module globals are torn down)."""
    if sys.monitoring.get_tool(TOOL) == NAME:
        sys.monitoring.set_events(TOOL, 0)
        sys.monitoring.register_callback(TOOL, sys.monitoring.events.PY_START, None)
        sys.monitoring.free_tool_id(TOOL)


@contextlib.contextmanager
def capture():
    """A set filled with the key of every repo function that starts inside the block (re-arming every report)."""
    start()
    seen = set()
    _CAPTURES.append(seen)
    sys.monitoring.restart_events()
    try:
        yield seen
    finally:
        _CAPTURES.remove(seen)


def ran_while(make) -> tuple:
    """(make()'s value, {key: identity} of the repo functions that ran making it)."""
    with capture() as seen:
        value = make()
    return value, hashes(seen)
