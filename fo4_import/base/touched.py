"""Files this process touched without changing their bytes (write_new, a skipped stage's outputs), with their size
and time before the run's first touch and after its last, so a check against an older record of the file
(ba2_pack._held) needs no read while nothing wrote the file since.

See: docs/fork/fo4_pipeline.md#touched
"""

import os
from pathlib import Path

#: {normcased path: ([size, time] before this run first touched it, [size, time] after its last touch)}.
TOUCHED = {}


def touch(path: Path) -> None:
    """os.utime(`path`) now, its bytes unchanged; kept in TOUCHED."""
    key, now = os.path.normcase(str(path)), _stamp(os.stat(path))
    first, last = TOUCHED.get(key, (None, None))
    os.utime(path)
    TOUCHED[key] = first if last == now else now, _stamp(os.stat(path))


def forget(path: Path) -> None:
    """Drop `path` from TOUCHED: its bytes are being changed."""
    TOUCHED.pop(os.path.normcase(str(path)), None)


def before(path: Path, stat) -> 'list | None':
    """`path`'s [size, time] before this run's touches, if `stat` is the last's."""
    first, last = TOUCHED.get(os.path.normcase(str(path)), (None, None))
    return first if last is not None and _stamp(stat) == last else None


def _stamp(stat) -> list:
    """[size, time] of an os.stat result."""
    return [stat.st_size, stat.st_mtime_ns]
