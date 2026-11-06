"""FalloutNV.exe 1.4.0.525 function names from two sources side by side: fnv_decomp's (`build/units.json`) and the
Xbox 360 prototype symbols' (nv-rs's engine map).

    py -3.14 -m tools.disasm.fnv_names 0x741500 0093e860       # names of these addresses
    py -3.14 -m tools.disasm.fnv_names --find "CaravanMenu::"   # functions whose name in either source matches

A function inside another (a crash or disassembly address) prints the function holding it.

See: docs/fork/research/fnv_decomp.md#names
"""

import argparse
import bisect
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / 'references' / 'fnv_decomp' / 'build' / 'units.json'
ENGINE_MAP = ROOT / 'references' / 'nv-rs' / 'engine_map.tsv'
#: A decomp name made from an address (FUN_00741500, fnv_00741500, a *_shell class), not a real one.
PLACEHOLDER = re.compile(r'(FUN_|fnv_|DAT_)[0-9a-f]{8}|_shell|__Dummy_', re.I)


def demangle(symbol: str) -> str:
    """`Class::Method` from an MSVC symbol as units.json writes it (`?Method@Class@@...`; a template class keeps
    its name, not its arguments); others unchanged."""
    if not symbol.startswith('?'):
        return symbol.lstrip('_')
    names = []
    for part in symbol[1:].split('@@')[0].split('@'):
        names.append(part.removeprefix('?$'))
        if part.startswith('?$'):
            break
    return '::'.join(reversed([n for n in names if n]))


def decomp(path: Path = UNITS) -> dict:
    """{address: (name, size, source file)} of every fnv_decomp function."""
    out = {}
    for unit in json.loads(path.read_text(encoding='utf-8'))['units']:
        for f in unit['functions']:
            out[int(f['address'], 16)] = (demangle(f['symbol']), f['size'], unit['source'])
    return out


def engine_map(path: Path = ENGINE_MAP) -> dict:
    """{address: (Xbox name or '', how it was matched, source unit)} of every engine map function."""
    if not path.is_file():
        return {}
    lines = [line for line in path.read_text(encoding='utf-8').splitlines() if not line.startswith('#')]
    return {int(r['address'], 16): (r['name'], r['name_tier'], r['unit']) for r in csv.DictReader(lines, delimiter='\t')}


def holder(functions: dict, starts: list, address: int) -> 'int | None':
    """The start of the decomp function whose body holds `address`, or None."""
    at = bisect.bisect_right(starts, address) - 1
    if at < 0 or address >= starts[at] + functions[starts[at]][1]:
        return None
    return starts[at]


def line(address: int, functions: dict, xbox: dict) -> str:
    """One function's address, size, both names and source files."""
    name, size, source = functions.get(address, ('', 0, ''))
    x_name, tier, unit = xbox.get(address, ('', '', ''))
    mark = ' (placeholder)' if PLACEHOLDER.search(name) else ''
    xbox_part = f'  xbox={x_name} [{tier}] {unit}' if x_name else '  xbox=none'
    return f'{address:08x} {size:6}  decomp={name}{mark} {source}{xbox_part}'


def main(argv: list = None) -> None:
    """Print the names of the given addresses, or of every function a --find pattern matches."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('addresses', nargs='*', help='hex addresses, with or without 0x')
    ap.add_argument('--find', help='regex matched against both names (case-insensitive)')
    args = ap.parse_args(argv)
    functions, xbox = decomp(), engine_map()
    if not xbox:
        print(f'no engine map at {ENGINE_MAP}: Xbox names left out')
    starts = sorted(functions)
    for text in args.addresses:
        address = int(text, 16)
        start = holder(functions, starts, address)
        if start is None:
            print(f'{address:08x}  in no decomp function')
            continue
        offset = f'  (+0x{address - start:x})' if start != address else ''
        print(line(start, functions, xbox) + offset)
    if args.find:
        pattern = re.compile(args.find, re.I)
        hits = [a for a in starts if pattern.search(functions[a][0]) or pattern.search(xbox.get(a, ('',))[0])]
        for address in hits:
            print(line(address, functions, xbox))
        print(f'{len(hits)} functions')


if __name__ == '__main__':
    main()
