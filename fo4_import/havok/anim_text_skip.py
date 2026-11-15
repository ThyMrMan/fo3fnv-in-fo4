"""The animation data stage's skip: a live run keeps, per plugin in the work cache, what it read (where each
Meshes path was found and its digest), the files it wrote (size and time) and its template entries. A later build
on the same inputs whose reads still find the same bytes in the same place, whose files are as written and whose
code is unchanged touches those files instead of making them again.

See: docs/fork/research/anim_text_data.md#skip
"""

import hashlib
import os
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.ba2_pack import data_reader
from fo4_import.havok import anim_text
from fo4_import.pipeline import work_cache
from fo4_import.pipeline.ran_code import ran_while

SITE = 'anim_text_run'
#: The kept record's layout; a change makes every kept run stale.
FORMAT = 1


def inputs(plugin: Path, records: list, stamps: tuple, dirs: list, copies: dict) -> tuple:
    """A run's work cache inputs: everything it depends on but its reads."""
    return FORMAT, str(plugin), hashlib.sha1(b''.join(records)).hexdigest(), stamps, [str(d) for d in dirs], \
        sorted(copies.items())


def archive_stamps(game_data: Path, pattern: str) -> tuple:
    """(name, size, time) of each `pattern` archive in `game_data`."""
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(game_data.glob(pattern)))


def kept(key: tuple, dirs: list, data_dir: Path) -> 'dict | None':
    """The kept run for `key` when it is current: its code unchanged, every read finding the same (_same_reads)
    and every file as written (_as_written), those files then touched and the run kept again with their new
    times; else None."""
    run = work_cache.lookup(SITE, __name__, key)
    if run is None or not _as_written(run, data_dir):
        return None
    places = [data_reader(d) for d in dirs]
    if not all(_same_reads(log, places[:count]) for count, log in run['reads']):
        return None
    for rel in run['files']:
        os.utime(data_dir / rel)
    return _keep(key, run, data_dir)


def live(key: tuple, data_dir: Path, make) -> dict:
    """make(logs) run and kept for `key`: logs is a list each reader appends (place count, read log) to; make
    returns ([written paths], {entry: template}); the run ({'reads', 'files', 'templates', 'ran'})."""
    logs = []
    (written, templates), ran = ran_while(lambda: make(logs))
    run = {'reads': logs, 'files': [str(Path(p).relative_to(data_dir)) for p in written],
           'templates': templates, 'ran': ran}
    return _keep(key, run, data_dir)


def logged_reader(logs: list, *places):
    """anim_text.reader(*places) whose reads are logged in `logs` (live)."""
    log = {}
    logs.append((sum(not isinstance(p, Archives) for p in places), log))
    return anim_text.reader(*places, log=log)


def _keep(key: tuple, run: dict, data_dir: Path) -> dict:
    """`run` kept for `key` with its files' current sizes and times; `run`."""
    run['stats'] = [_stat(data_dir / rel) for rel in run['files']]
    return work_cache.store(SITE, __name__, key, run, run['ran'])


def _stat(path: Path) -> tuple:
    """(size, time) of `path`."""
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _as_written(run: dict, data_dir: Path) -> bool:
    """Whether every file `run` wrote is still there with the size and time it kept."""
    try:
        return all(_stat(data_dir / rel) == tuple(stat) for rel, stat in zip(run['files'], run['stats']))
    except OSError:
        return False


def _same_reads(log: dict, places: list) -> bool:
    """Whether each logged read ({rel: (index of the place that had it or None, digest)}) finds the same: the
    data folder `places` before it still lack it and the one that had it gives the same bytes (a game archive's
    answer is in the key)."""
    for rel, (at, digest) in log.items():
        stop = len(places) if at is None else min(at, len(places))
        if any(anim_text.read_in(place, rel) is not None for place in places[:stop]):
            return False
        if stop < len(places) and _digest(anim_text.read_in(places[stop], rel)) != digest:
            return False
    return True


def _digest(data: 'bytes | None') -> 'bytes | None':
    """The SHA-1 of `data`; None for None."""
    return None if data is None else hashlib.sha1(data).digest()
