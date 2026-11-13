"""Measure this machine for the build's time estimate: one core's speed, how speed grows with worker processes,
disk writes and reads, memory size and copy speed. Writes one JSON file to send back; takes about a minute.

    python tools/release/machine_benchmark.py [--out <file>] [--dir <folder on the build's drive>]

Needs only Python and numpy. A score is work units a second, so a faster machine scores higher; the estimate
scales each stage by the reference machine's score over this one's (fo4_import.pipeline.eta).

See: docs/fork/fo4_build_resources.md#benchmark
"""

import argparse
import json
import os
import platform
import struct
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.memory_budget import free_ram_bytes
from core.process_job import total_memory

VERSION = 1
#: Where the result goes by default: where the build's estimate looks for it (fo4_import.pipeline.eta.BENCHMARK).
DEFAULT_OUT = Path(__file__).resolve().parents[2] / 'output' / 'machine_benchmark.json'
MB = 1 << 20
#: Records one Python work unit packs, parses and indexes; a unit takes about 0.1 s on the reference machine.
UNIT_RECORDS = 20000
#: Seconds each single-core measurement runs for.
SECONDS = 3.0
#: Units each worker runs in the scaling measurement.
UNITS_EACH = 12
#: Disk test: the large file's size; how many small files, and the size of each.
BIG_BYTES, SMALL_FILES, SMALL_BYTES = 512 * MB, 2000, 64 << 10


def python_unit(seed: int = 0) -> int:
    """One unit of the build's kind of pure-Python work: records packed to bytes, read back into dicts, indexed."""
    rows = {}
    for i in range(UNIT_RECORDS):
        raw = struct.pack('<IIf8s', i, i ^ seed, i * 0.5, b'EDID%04d' % (i % 10000))
        form, other, value, edid = struct.unpack('<IIf8s', raw)
        rows[f'{form:08X}'] = {'FormID': form, 'Other': other, 'Value': value, 'EditorID': edid.decode()}
    return sum(len(r['EditorID']) for r in rows.values() if r['Other'] & 1)


def numpy_unit() -> float:
    """One unit of numpy work: a 400 x 400 matrix product and a sort of 1M floats."""
    rng = numpy.random.default_rng(1)
    a = rng.random((400, 400))
    numpy.sort(rng.random(1 << 20))
    return float((a @ a).sum())


def rate(fn, seconds: float = SECONDS) -> float:
    """Calls of `fn` a second over about `seconds`."""
    fn()
    calls, started = 0, time.perf_counter()
    while time.perf_counter() - started < seconds:
        fn()
        calls += 1
    return calls / (time.perf_counter() - started)


def _units(count: int) -> int:
    """`count` Python units in one worker."""
    return sum(python_unit(n) for n in range(count))


def scaling(single: float) -> dict:
    """{workers: units a second, all workers together} at 1, a quarter, half, three quarters and all but one of the
    logical cores, each run UNITS_EACH units a worker; 'effective_cores' the best of them over `single`."""
    cpus = os.cpu_count() or 2
    counts = sorted({1, max(1, cpus // 4), max(1, cpus // 2), max(1, cpus * 3 // 4), max(1, cpus - 1)})
    out = {}
    for workers in counts:
        with ProcessPoolExecutor(workers) as pool:
            list(pool.map(_units, [1] * workers))
            started = time.perf_counter()
            list(pool.map(_units, [UNITS_EACH] * workers))
            out[str(workers)] = round(workers * UNITS_EACH / (time.perf_counter() - started), 2)
        print(f'  {workers} workers: {out[str(workers)]} units/s', flush=True)
    return {'units_per_second': out, 'effective_cores': round(max(out.values()) / single, 2)}


def _small_files(scratch: Path) -> float:
    """Seconds to write, then read, SMALL_FILES files of SMALL_BYTES each (a build's many small meshes)."""
    data = os.urandom(SMALL_BYTES)
    started = time.perf_counter()
    for n in range(SMALL_FILES):
        (scratch / f'{n}.bin').write_bytes(data)
    for n in range(SMALL_FILES):
        (scratch / f'{n}.bin').read_bytes()
    return time.perf_counter() - started


def disk(folder: Path) -> dict:
    """In a scratch folder under `folder`: one BIG_BYTES file written in 16 MB blocks and flushed to disk once,
    then read back (MB/s each way: the read may come from the system's cache), and small files written and read
    (files a second)."""
    block = os.urandom(16 * MB)
    with tempfile.TemporaryDirectory(dir=folder) as scratch:
        big = Path(scratch) / 'big.bin'
        started = time.perf_counter()
        with open(big, 'wb') as f:
            for _ in range(BIG_BYTES // len(block)):
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
        wrote = time.perf_counter() - started
        started = time.perf_counter()
        with open(big, 'rb') as f:
            while f.read(16 * MB):
                pass
        read = time.perf_counter() - started
        small = _small_files(Path(scratch))
    return {'write_mb_s': round(BIG_BYTES / MB / wrote, 1), 'read_mb_s': round(BIG_BYTES / MB / read, 1),
            'small_files_s': round(SMALL_FILES / small, 1), 'folder': str(folder)}


def memory() -> dict:
    """Physical and free memory in GB and numpy's copy speed in GB/s over a 256 MB array."""
    block = numpy.ones(256 * MB // 8)
    copies = rate(lambda: block.copy(), 1.0)
    return {'total_gb': round(total_memory() / (1 << 30), 1), 'free_gb': round((free_ram_bytes() or 0) / (1 << 30), 1),
            'copy_gb_s': round(copies * 0.25, 1)}


def measure(folder: Path) -> dict:
    """Every measurement, with what identifies the machine's parts (no user or machine name)."""
    print('one core: Python...', flush=True)
    single = rate(python_unit)
    print('one core: numpy...', flush=True)
    numeric = rate(numpy_unit)
    print('worker processes...', flush=True)
    scaled = scaling(single)
    print('disk...', flush=True)
    return {'version': VERSION, 'when': time.strftime('%Y-%m-%d %H:%M'), 'cpu': platform.processor(),
            'machine': platform.machine(), 'os': platform.platform(), 'python': platform.python_version(),
            'logical_cores': os.cpu_count(), 'single': {'python_units_s': round(single, 2),
                                                        'numpy_units_s': round(numeric, 2)},
            'workers': scaled, 'disk': disk(folder), 'memory': memory()}


def main() -> None:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT, help=f'The result file to send back (default {DEFAULT_OUT})')
    ap.add_argument('--dir', type=Path, default=Path(tempfile.gettempdir()),
                    help="A folder on the drive the build writes to (default: the system's temporary folder)")
    args = ap.parse_args()
    result = measure(args.dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=1))
    print(f'written: {args.out.resolve()}')


if __name__ == '__main__':
    main()
