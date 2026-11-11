"""Check fo4_import.nif.fnv_reader against pyffi on FNV/FO3 meshes: every field of every block, read time, and
peak committed memory per reader in capped child processes.

    python tools/nif/fnv_reader_check.py <files or folders> --max 300 --out temp/fnv_reader.jsonl
    python tools/nif/fnv_reader_check.py big.nif --peak --cap-gb 4

Folders are sampled for variety: files bringing a block type not yet seen first, then seeded random ones.
Each result is written as one JSON line as soon as it is known.

See: docs/fork/research/fnv_nif_reader.md#proof
"""

import argparse
import ctypes
import json
import math
import multiprocessing
import os
import random
import struct
import sys
import time
import tracemalloc
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.process_job import limit_own_memory
from fo4_import.nif.fnv_schema import NifFormat, StructBase
from fo4_import.nif import fnv_file, fnv_reader
from pyffi.object_models.xml.bit_struct import BitStructBase

#: Differences listed per file (the count covers all).
LIMIT = 20
#: Bytes read for a header when choosing files.
HEADER_BYTES = 1 << 16
#: PROCESS_MEMORY_COUNTERS fields.
COUNTER_FIELDS = (('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t),
                  ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                  ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                  ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t),
                  ('PeakPagefileUsage', ctypes.c_size_t))


# ---------------------------------------------------------------------------
# Choosing files
# ---------------------------------------------------------------------------

def meshes(paths: list) -> list:
    """Every .nif named or under a named folder, sorted."""
    out = []
    for path in map(Path, paths):
        out += sorted(path.rglob('*.nif')) if path.is_dir() else [path]
    return out


def block_types(path: Path) -> set:
    """The block types a NIF's header lists; empty when it is not a readable FO3/FNV header."""
    try:
        with open(path, 'rb') as f:
            raw = f.read(HEADER_BYTES)
        raw = raw if len(raw) < HEADER_BYTES else path.read_bytes()
        return {kind for kind, _ in fnv_reader.read_header(raw[fnv_file.header_start(raw):])[1]}
    except (ValueError, IndexError, OSError, struct.error):
        return set()


def varied(files: list, count: int, seed: int) -> list:
    """Up to `count` of `files`: each bringing a block type not yet chosen first, then seeded random ones."""
    shuffled = random.Random(seed).sample(files, len(files))
    chosen, seen = [], set()
    for path in shuffled:
        kinds = block_types(path)
        if kinds - seen and len(chosen) < count:
            chosen.append(path)
            seen |= kinds
    taken = set(chosen)
    return chosen + [p for p in shuffled if p not in taken][:max(0, count - len(chosen))]


# ---------------------------------------------------------------------------
# Field-by-field comparison
# ---------------------------------------------------------------------------

def _equal(a, b) -> bool:
    """Whether two basic values are equal (floats exactly, NaN equal to NaN)."""
    if isinstance(a, float) and isinstance(b, float):
        return a == b or math.isnan(a) and math.isnan(b)
    return type(a) is type(b) and a == b or isinstance(a, (int, bool)) and a == b


def _is_link(a, b) -> bool:
    """Whether pyffi value `a` is a link (a block, or None where ours is no array)."""
    return isinstance(a, NifFormat.NiObject) or a is None and not isinstance(b, (list, fnv_reader.Values))


class Diff:
    """The differences found between one file's pyffi and fnv_reader reads."""

    def __init__(self, pyffi_data, ours):
        """Comparison of pyffi `pyffi_data` with our NifData `ours`."""
        self.data, self.found, self.count = pyffi_data, [], 0
        self.ours = {id(b): i for i, b in enumerate(ours.blocks)}
        self.theirs = {id(b): i for i, b in enumerate(pyffi_data.blocks)}

    def note(self, where: str, a, b) -> None:
        """Record one difference."""
        self.count += 1
        if len(self.found) < LIMIT:
            self.found.append(f'{where}: pyffi {str(a)[:60]!r} ours {str(b)[:60]!r}')

    def link(self, where: str, a, b) -> None:
        """Compare pyffi link `a` (a block or None) with ours by block index."""
        theirs = None if a is None else self.theirs[id(a)]
        ours = None if b is None else self.ours.get(id(b), 'foreign')
        if theirs != ours:
            self.note(where, theirs, ours)

    def value(self, where: str, a, b) -> None:
        """Compare pyffi value `a` with ours `b`."""
        if _is_link(a, b):
            return self.link(where, a, b)
        if isinstance(a, StructBase):
            return self.struct(where, a, b)
        if isinstance(a, BitStructBase):
            return self.value(where, int(a), int(b))
        if isinstance(a, list):
            return self.array(where, a, b)
        if not _equal(a, b):
            self.note(where, a, b)
        return None

    def array(self, where: str, a, b) -> None:
        """Compare pyffi array `a` with ours `b`, element by element."""
        if len(a) != len(b):
            self.note(where + '.len', len(a), len(b))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            self.value(f'{where}[{i}]', x, y)

    def struct(self, where: str, a, b) -> None:
        """Compare pyffi struct `a` with ours `b`, every field pyffi read."""
        if type(a).__name__.removesuffix('View') != type(b).__name__:
            self.note(where + '.type', type(a).__name__, type(b).__name__)
            return
        for attr in a._get_filtered_attribute_list(self.data):
            self.value(f'{where}.{attr.name}', getattr(a, attr.name), getattr(b, attr.name))

    def links(self, at: int, a, b) -> None:
        """Compare block `at`'s get_refs order."""
        theirs = [self.theirs[id(x)] for x in a.get_refs()]
        ours = [self.ours[id(x)] for x in b.get_refs()]
        if theirs != ours:
            self.note(f'{at}.get_refs', theirs, ours)


def compare(path: str) -> dict:
    """Read `path` with pyffi and fnv_reader; their times and every field that differs."""
    out = {'file': path, 'size': os.path.getsize(path)}
    start = time.perf_counter()
    ours = fnv_reader.read(path)
    out['ours_s'] = time.perf_counter() - start
    out.update(skipped=ours.skipped, resized=ours.resized, blocks=len(ours.blocks))
    try:
        start = time.perf_counter()
        theirs = fnv_file.read(path)
        out['pyffi_s'] = time.perf_counter() - start
    except Exception as error:
        out['pyffi_error'] = f'{type(error).__name__}: {error}'[:200]
        return out
    diff = Diff(theirs, ours)
    if len(theirs.blocks) != len(ours.blocks):
        diff.note('blocks', len(theirs.blocks), len(ours.blocks))
    for at, (a, b) in enumerate(zip(theirs.blocks, ours.blocks)):
        diff.struct(f'{at}:{type(a).__name__}', a, b)
        if not isinstance(b, fnv_reader.Unread):
            diff.links(at, a, b)
    diff.array('roots', theirs.roots, ours.roots)
    out.update(diffs=diff.count, first=diff.found)
    return out


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class _Counters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS."""
    _fields_ = COUNTER_FIELDS


def committed() -> tuple:
    """(committed bytes now, peak committed bytes) of this process."""
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb)
    return counters.PagefileUsage, counters.PeakPagefileUsage


def _peak_child(path: str, reader: str, cap: int, queue) -> None:
    """In a child process capped at `cap` bytes: read `path` with `reader`; put (seconds, peak - base, status)."""
    limit_own_memory(cap)
    base = committed()[0]
    start = time.perf_counter()
    try:
        data = (fnv_reader.read if reader == 'ours' else fnv_file.read)(path)
        status = f'{len(data.blocks)} blocks'
    except MemoryError:
        status = 'cap'
    queue.put((time.perf_counter() - start, committed()[1] - base, status))


def peak(path: str, reader: str, cap: int) -> dict:
    """Seconds, peak committed memory over the process's start and status of reading `path` with `reader`."""
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    child = context.Process(target=_peak_child, args=(path, reader, cap, queue))
    child.start()
    child.join()
    if queue.empty():
        return {f'{reader}_status': f'died ({child.exitcode})'}
    seconds, grown, status = queue.get()
    return {f'{reader}_s': seconds, f'{reader}_peak_mb': grown / 2 ** 20, f'{reader}_status': status}


def traced(path: str) -> dict:
    """Peak Python-traced memory (numpy included) of each reader on `path`, in MB."""
    out = {}
    for name, reader in (('ours', fnv_reader.read), ('pyffi', fnv_file.read)):
        tracemalloc.start()
        try:
            reader(path)
            out[f'{name}_traced_mb'] = tracemalloc.get_traced_memory()[1] / 2 ** 20
        except Exception:
            out[f'{name}_traced_mb'] = None
        tracemalloc.stop()
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _job(task: tuple) -> dict:
    """One file's result for `task` (path, options)."""
    path, options = task
    limit_own_memory(options['cap'])
    try:
        out = compare(path)
        out.update(traced(path) if options['traced'] else {})
    except MemoryError:
        out = {'file': path, 'error': 'memory cap'}
    except Exception as error:
        out = {'file': path, 'error': f'{type(error).__name__}: {error}'[:300]}
    return out


def _args() -> argparse.Namespace:
    """Command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--max', type=int, default=0, help='sample this many files from the folders (0: all)')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--workers', type=int, default=max(1, os.cpu_count() - 1))
    parser.add_argument('--cap-gb', type=float, default=4.0, help='memory cap per worker or child')
    parser.add_argument('--peak', action='store_true', help='only measure time and peak memory per reader')
    parser.add_argument('--traced', action='store_true', help='also measure traced peak memory')
    parser.add_argument('--out', help='append one JSON line per file here')
    return parser.parse_args()


def emit(result: dict, out) -> None:
    """Print one result line and append it to `out`."""
    line = json.dumps(result, default=str)
    print(line[:400], flush=True)
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def main() -> None:
    """Compare or measure every chosen file, writing each result as it is known."""
    args = _args()
    files = meshes(args.paths)
    files = varied(files, args.max, args.seed) if args.max else files
    cap = int(args.cap_gb * 2 ** 30)
    if args.peak:
        for path in map(str, files):
            emit({'file': path, 'size': os.path.getsize(path), **peak(path, 'ours', cap),
                   **peak(path, 'pyffi', cap)}, args.out)
        return
    options = {'cap': cap, 'traced': args.traced}
    with multiprocessing.get_context('spawn').Pool(args.workers, maxtasksperchild=20) as pool:
        for result in pool.imap_unordered(_job, [(str(p), options) for p in files]):
            emit(result, args.out)


if __name__ == '__main__':
    main()
