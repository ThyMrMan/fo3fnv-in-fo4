"""The files a call opens, read and written, through Python's `open` audit event.

Work that reads files it finds by record (an export's head meshes, skins and brow textures) keys its work cache
entry on what it actually read and keeps what it wrote. Reads accumulate per process from the first recorded call
on: a memo an earlier call filled stands in for a file a later call no longer opens.

See: docs/fork/fo4_facegen_plan.md#skin-cache
"""

import functools
import hashlib
import os
import sys

#: os.open flags that open a file to write.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT
#: Whether the hook is installed and recording, the files read since the first recorded call, those written now.
_STATE = {'hooked': False, 'on': False, 'reads': set(), 'writes': set()}


def _audit(event: str, args: tuple) -> None:
    """sys.audit hook: while recording, a file opened is noted as read or written."""
    if event != 'open' or not _STATE['on'] or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    mode, flags = args[1], args[2]
    writing = any(c in mode for c in 'wax+') if isinstance(mode, str) else bool((flags or 0) & _WRITE_FLAGS)
    _STATE['writes' if writing else 'reads'].add(os.path.normcase(os.path.abspath(os.fsdecode(args[0]))))


def opened(call) -> tuple:
    """(call()'s value, files this process's recorded calls have read so far, files `call` wrote): normalized
    absolute paths."""
    if not _STATE['hooked']:
        sys.addaudithook(_audit)
        _STATE['hooked'] = True
    _STATE['writes'] = set()
    _STATE['on'] = True
    try:
        value = call()
    finally:
        _STATE['on'] = False
    return value, frozenset(_STATE['reads']), frozenset(_STATE['writes'])


@functools.cache
def digest(path: str) -> 'str | None':
    """SHA-1 of the file at `path`, read once per process; None when there is none."""
    try:
        with open(path, 'rb') as f:
            return hashlib.file_digest(f, 'sha1').hexdigest()
    except OSError:
        return None
