"""Generate fo4_import/data/hk2014_layouts.json: Havok 2014 class layouts for the classes vanilla FO4 actor files use.

Reads hkxpack-style class descriptions (one XML per class, from a classxml folder the user supplies) and keeps the
classes named in the `__classnames__` sections of the game's actor .hkx files (behaviors, characters, projects,
skeletons, a sample of clips), plus their parents and member struct types. Each class keeps its parent, signature
and members (name, offset, type, subtype, struct type, fixed array size, flags).

    python tools/generators/hk2014_layouts.py <classxml folder> [-o fo4_import/data/hk2014_layouts.json]

See: docs/fork/fo4_spikes.md#own-rig-code
"""

import argparse
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from fo4_import.base.ba2 import Archive
from fo4_import.base.install import FALLOUT4_DIR

OUT = Path(__file__).resolve().parents[2] / 'fo4_import' / 'data' / 'hk2014_layouts.json'
#: Clips sampled per archive: every FO4 clip names the same handful of classes.
CLIP_SAMPLE = 20


def classnames(data: bytes) -> set:
    """Class names in a packfile's `__classnames__` section."""
    first = 0x40 + struct.unpack_from('<H', data, 0x3E)[0]
    for i in range(struct.unpack_from('<i', data, 0x14)[0]):
        base = first + i * 0x40
        if data[base:base + 16].split(b'\0')[0] == b'__classnames__':
            start = struct.unpack_from('<I', data, base + 0x14)[0]
            end = start + struct.unpack_from('<I', data, base + 0x18)[0]
            names, pos = set(), start
            while pos + 5 < end and data[pos + 4] == 9:
                stop = data.index(b'\0', pos + 5)
                names.add(data[pos + 5:stop].decode('latin-1'))
                pos = stop + 1
            return names
    return set()


def vanilla_classes() -> set:
    """Every class named by the game's actor .hkx files (clips sampled)."""
    found, clips = set(), 0
    for ba2 in sorted((FALLOUT4_DIR / 'Data').glob('Fallout4 - *.ba2')):
        archive = Archive(str(ba2))
        for name in sorted(n for n in archive.entries if n.endswith('.hkx') and n.startswith('meshes\\actors\\')):
            if '\\animations\\' in name:
                clips += 1
                if clips > CLIP_SAMPLE:
                    continue
            found |= classnames(archive.read(name))
    return found


def layout(e) -> dict:
    """One class description as the JSON entry."""
    members = [[m.get('name'), int(m.get('offset')), m.get('vtype'), m.get('vsubtype'), m.get('ctype'),
                int(m.get('arrsize')), m.get('flags')] for m in e.iter('member')]
    return {'parent': e.get('parent'), 'signature': e.get('signature'), 'members': members}


def closure(raw: dict, wanted: set) -> dict:
    """`wanted` with every parent and member struct type it needs, as JSON entries."""
    out, todo = {}, sorted(wanted)
    while todo:
        cls = todo.pop()
        if cls in out or cls not in raw:
            continue
        out[cls] = layout(raw[cls])
        todo += [c for c in [out[cls]['parent']] + [m[4] for m in out[cls]['members']] if c]
    return dict(sorted(out.items()))


def main():
    """Read the class folder, scan the game's actor files, write the layout table."""
    p = argparse.ArgumentParser()
    p.add_argument('classxml', type=Path)
    p.add_argument('-o', '--out', type=Path, default=OUT)
    args = p.parse_args()
    raw = {}
    for path in sorted(args.classxml.glob('*.xml')):
        e = ET.fromstring(path.read_text(encoding='utf-8', errors='replace'))
        raw[e.get('name')] = e
    wanted = vanilla_classes()
    table = closure(raw, wanted)
    args.out.write_text(json.dumps(table, indent=0, separators=(',', ':')) + '\n', encoding='utf-8')
    missing = sorted(wanted - set(raw))
    print(f'{len(wanted)} classes in vanilla actor files, {len(table)} written with parents and members;'
          f' undescribed: {missing}')


if __name__ == '__main__':
    main()
