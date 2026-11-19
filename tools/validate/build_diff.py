"""Before/after check of a Fallout 4 build: what one change did to a built plugin and its generated scripts.

    python tools/validate/build_diff.py snapshot <name> --plugin <built .esm> --scripts <generated .psc folder>
    python tools/validate/build_diff.py diff <name> --plugin <built .esm> --scripts <generated .psc folder>
        [--sig PACK] [--script NAME] [--list N]

`snapshot` copies the plugin and every .psc into temp/build_snapshots/<name>/. `diff` compares the current build
with it: records added, removed and changed per signature (with EditorIDs and the subrecords that changed),
and scripts added, removed and changed (with their changed line counts and the lines themselves for --script).

See: docs/fork/fo4_scene_driving_plan.md#fnv-check
"""

import argparse
import difflib
import mmap
import shutil
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from tools.esm.esm_diff import iter_records, iter_top_groups

ROOT = Path(__file__).resolve().parents[2] / 'temp' / 'build_snapshots'
#: Record flag: the body is a 4-byte size and zlib data.
COMPRESSED = 0x40000
HEADER = 24


def records(path: Path) -> dict:
    """{(signature, FormID): record bytes} of every record in the plugin at `path`."""
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return {(sig, fid): bytes(blob) for _, start, end in iter_top_groups(mm)
                for sig, fid, blob in iter_records(mm, start, end)}


def subrecords(blob: bytes) -> list:
    """[(tag, data)] of one record, decompressed (an XXXX size prefix honored)."""
    flags = struct.unpack_from('<I', blob, 8)[0]
    body = zlib.decompress(blob[HEADER + 4:]) if flags & COMPRESSED else blob[HEADER:]
    out, pos, big = [], 0, None
    while pos + 6 <= len(body):
        tag, size = body[pos:pos + 4].decode('ascii', 'replace'), struct.unpack_from('<H', body, pos + 4)[0]
        size, big = (big, None) if big is not None else (size, None)
        data = body[pos + 6:pos + 6 + size]
        if tag == 'XXXX':
            big = struct.unpack('<I', data)[0]
        else:
            out.append((tag, data))
        pos += 6 + size
    return out


def edid(blob: bytes) -> str:
    """A record's EditorID, or ''."""
    return next((d.rstrip(b'\0').decode('cp1252', 'replace') for t, d in subrecords(blob) if t == 'EDID'), '')


def changed_tags(a: bytes, b: bytes) -> list:
    """The subrecord tags whose data differs between two versions of a record (in b's order; +/- for counts)."""
    sa, sb = defaultdict(list), defaultdict(list)
    for tag, data in subrecords(a):
        sa[tag].append(data)
    for tag, data in subrecords(b):
        sb[tag].append(data)
    tags = list(dict.fromkeys([*sb, *sa]))
    return [tag + ('+' if len(sb[tag]) > len(sa[tag]) else '-' if len(sb[tag]) < len(sa[tag]) else '')
            for tag in tags if sa[tag] != sb[tag]]


def snapshot(name: str, plugin: Path, scripts: Path) -> None:
    """Copy `plugin` and every .psc under `scripts` into ROOT/<name>."""
    out = ROOT / name
    shutil.rmtree(out, ignore_errors=True)
    (out / 'scripts').mkdir(parents=True)
    shutil.copy2(plugin, out / plugin.name)
    for psc in scripts.glob('*.psc'):
        shutil.copy2(psc, out / 'scripts' / psc.name)
    print(f'snapshot {name}: {plugin.name}, {len(list((out / "scripts").glob("*.psc")))} scripts -> {out}')


def diff_records(old: Path, new: Path, sig: str, shown: int) -> None:
    """Print added/removed/changed records per signature; with `sig`, every one of that signature."""
    a, b = records(old), records(new)
    kinds = defaultdict(lambda: Counter())
    rows = defaultdict(list)
    for key in sorted(set(a) | set(b)):
        if a.get(key) == b.get(key):
            continue
        mark = '+' if key not in a else '-' if key not in b else '~'
        kinds[key[0]][mark] += 1
        blob = b.get(key) or a.get(key)
        tags = ' '.join(changed_tags(a[key], b[key])) if mark == '~' else ''
        rows[key[0]].append(f'      {mark} {key[1]:08X} {edid(blob)} {tags}'.rstrip())
    print(f'RECORDS: {sum(sum(c.values()) for c in kinds.values())} differ')
    for s in sorted(kinds):
        print(f'  {s}: ' + ' '.join(f'{m}{n}' for m, n in sorted(kinds[s].items())))
        for row in rows[s][:None if s == sig else shown]:
            print(row)


def diff_scripts(old: Path, new: Path, name: str, shown: int) -> None:
    """Print added/removed/changed scripts with changed line counts; with `name`, that script's diff."""
    a, b = {p.name: p for p in old.glob('*.psc')}, {p.name: p for p in new.glob('*.psc')}
    added, removed = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    changed = []
    for script in sorted(set(a) & set(b)):
        la, lb = a[script].read_text('utf-8', 'replace').splitlines(), b[script].read_text('utf-8', 'replace').splitlines()
        if la != lb:
            delta = [l for l in difflib.unified_diff(la, lb, lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
            changed.append((script, sum(l[0] == '+' for l in delta), sum(l[0] == '-' for l in delta), delta))
    print(f'SCRIPTS: +{len(added)} -{len(removed)} ~{len(changed)}')
    for tag, names in (('+', added), ('-', removed)):
        for script in names[:shown]:
            print(f'  {tag} {script}')
    for script, plus, minus, delta in changed[:None if name else shown]:
        if not name or name.lower() in script.lower():
            print(f'  ~ {script} +{plus} -{minus}')
            for line in delta[:200] if name else ():
                print(f'      {line}')


def main() -> int:
    """Run `snapshot` or `diff` (module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('action', choices=('snapshot', 'diff'))
    ap.add_argument('name')
    ap.add_argument('--plugin', type=Path, required=True)
    ap.add_argument('--scripts', type=Path, required=True)
    ap.add_argument('--sig', default='', help='list every changed record of this signature')
    ap.add_argument('--script', default='', help='print the changed lines of scripts whose name contains this')
    ap.add_argument('--list', type=int, default=15, help='rows listed per group')
    args = ap.parse_args()
    if args.action == 'snapshot':
        snapshot(args.name, args.plugin, args.scripts)
        return 0
    base = ROOT / args.name
    diff_records(base / args.plugin.name, args.plugin, args.sig, args.list)
    diff_scripts(base / 'scripts', args.scripts, args.script, args.list)
    return 0


if __name__ == '__main__':
    sys.exit(main())
