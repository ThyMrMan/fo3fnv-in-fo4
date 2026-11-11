"""Convert FNV/FO3 meshes with convert_static twice in one process, reading them with pyffi and then with
fo4_import.nif.fnv_reader, and compare the FO4 NIF bytes and every material, texture and map the two name.

    python tools/nif/fnv_convert_check.py <files or folders> --max 100 --out temp/fnv_convert.jsonl

The second run swaps, in the converter's modules only, `NifFormat` for fnv_schema.FORMAT and `fnv_file.read` for
fnv_reader.read: the integration the reader would ship with. Nothing is written but the result lines.

See: docs/fork/research/fnv_nif_reader.md#integration
"""

import argparse
import contextlib
import hashlib
import multiprocessing
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.process_job import limit_own_memory
from fo4_import.nif.fnv_schema import FORMAT, NifFormat
from fo4_import.nif import convert_static, file as fo4_file, fnv_file, fnv_reader
from tools.nif.fnv_reader_check import emit, meshes, varied

#: Module name prefixes the swap reaches (convert_static and what it calls).
SWAPPED = ('fo4_import.nif.', 'fo4_import.spike.', 'asset_convert.collision.')
#: Modules never swapped: the reader itself.
KEPT = ('fo4_import.nif.fnv_schema', 'fo4_import.nif.fnv_reader', 'fo4_import.nif.fnv_file')
#: Converted fields compared besides the NIF bytes.
PARTS = ('materials', 'effects', 'textures', 'spec_maps', 'glow_maps', 'animatable')


@contextlib.contextmanager
def ours():
    """The converter's modules reading with fnv_reader (NifFormat as FORMAT) inside the block."""
    reader = types.SimpleNamespace(read=fnv_reader.read, header_start=fnv_file.header_start)
    changed = []
    for name, module in list(sys.modules.items()):
        if not name.startswith(SWAPPED) or name in KEPT:
            continue
        for attr, old, new in (('NifFormat', NifFormat, FORMAT), ('fnv_file', fnv_file, reader)):
            if getattr(module, attr, None) is old:
                setattr(module, attr, new)
                changed.append((module, attr, old))
    try:
        yield
    finally:
        for module, attr, old in changed:
            setattr(module, attr, old)


def texture_root(path: str) -> str:
    """The export folder holding mesh `path` (the part before its `meshes` folder)."""
    parts = Path(path).resolve().parts
    lower = [p.lower() for p in parts]
    return str(Path(*parts[:lower.index('meshes')])) if 'meshes' in lower else ''


def outcome(path: str) -> tuple:
    """(seconds, {part: value}) of converting `path`, or (seconds, {'error': ...})."""
    start = time.perf_counter()
    try:
        made = convert_static.convert(path, texture_root(path) or None)
        found = {'nif': hashlib.sha1(fo4_file.write(made.nif)).hexdigest()}
        found.update({k: repr(sorted(v.items()) if isinstance(v, dict) else sorted(v) if isinstance(v, set) else v)
                      for k, v in ((k, getattr(made, k)) for k in PARTS)})
    except Exception as error:
        found = {'error': f'{type(error).__name__}: {error}'[:200]}
    return time.perf_counter() - start, found


def check(path: str) -> dict:
    """Both conversions of `path`: their times (each after a pyffi run warmed the converter's caches) and the
    parts that differ."""
    theirs = outcome(path)[1]
    with ours():
        ours_s, mine = outcome(path)
    pyffi_s = outcome(path)[0]
    differ = sorted(k for k in set(theirs) | set(mine) if theirs.get(k) != mine.get(k))
    return {'file': path, 'size': os.path.getsize(path), 'pyffi_convert_s': pyffi_s, 'ours_convert_s': ours_s,
            'same': not differ, 'differ': differ, 'pyffi_error': theirs.get('error'), 'ours_error': mine.get('error')}


def _job(task: tuple) -> dict:
    """One file's check under a memory cap of task[1] bytes."""
    path, cap = task
    limit_own_memory(cap)
    try:
        return check(path)
    except MemoryError:
        return {'file': path, 'error': 'memory cap'}


def main() -> None:
    """Check every chosen file, writing each result as it is known."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--max', type=int, default=0, help='sample this many files from the folders (0: all)')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--workers', type=int, default=max(1, os.cpu_count() - 1))
    parser.add_argument('--cap-gb', type=float, default=4.0)
    parser.add_argument('--out', help='append one JSON line per file here')
    args = parser.parse_args()
    files = meshes(args.paths)
    files = varied(files, args.max, args.seed) if args.max else files
    tasks = [(str(p), int(args.cap_gb * 2 ** 30)) for p in files]
    with multiprocessing.get_context('spawn').Pool(args.workers, maxtasksperchild=20) as pool:
        for result in pool.imap_unordered(_job, tasks):
            emit(result, args.out)


if __name__ == '__main__':
    main()
