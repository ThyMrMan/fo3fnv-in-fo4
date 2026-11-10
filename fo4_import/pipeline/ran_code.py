"""Which repo functions ran in this process: sys.monitoring (PEP 669) reports each function's first start and is
told not to report it again, so it costs one event per function. capture() collects what runs inside it (it
re-arms the reports first), for a cache entry keyed on the code that made it. A capture for a site keeps
everything that ran for that site in this process so far, so work a per-process memo did for an earlier entry
stays in every later entry's record.

See: docs/fork/fo4_plugin_layout.md#code-identity
See: docs/fork/fo4_build_speed.md#keys
"""

import atexit
import contextlib
import functools
import sys

from fo4_import.pipeline.code_identity import SEP, hashes, relative

#: This module's sys.monitoring tool id and name (0-2 and 5 are the debugger, coverage, profiler, optimizer slots).
TOOL, NAME = 4, 'f3nv ran code'
#: The recording's own files (its audit hook runs inside every capture): never part of what made a value.
RECORDERS = frozenset(f'fo4_import/pipeline/{name}.py' for name in ('build_inputs', 'ran_code', 'code_identity',
                                                                     'code_tag'))
#: Every repo function key that ran in this process since start().
RAN = set()
#: {site: every repo function key that ran inside a capture of that site in this process}.
SITES = {}
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
def capture(site=None):
    """A set filled with the key of every repo function that starts inside the block (re-arming every report);
    given `site` (hashable), it is SITES[site]: also what ran in this process's earlier captures of `site`."""
    start()
    seen = set() if site is None else SITES.setdefault(site, set())
    _CAPTURES.append(seen)
    sys.monitoring.restart_events()
    try:
        yield seen
    finally:
        del _CAPTURES[max(i for i, held in enumerate(_CAPTURES) if held is seen)]


def site_of(make):
    """The code `make` runs (through functools.partial and bound methods), standing for its site."""
    while isinstance(make, functools.partial):
        make = make.func
    make = getattr(make, '__func__', make)
    return getattr(make, '__code__', type(make))


def ran_while(make) -> tuple:
    """(make()'s value, {key: identity} of what ran for site_of(make) so far)."""
    with capture(site_of(make)) as seen:
        value = make()
    return value, hashes(seen)
