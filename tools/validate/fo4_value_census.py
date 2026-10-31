"""Find what a built Fallout 4 plugin writes that vanilla Fallout4.esm never does: tags, sizes, flag bits.

    py -3.14 -m tools.validate.fo4_value_census <plugin.esp> [--sigs PACK NPC_ ...] [--examples N]

For every record type the plugin holds, Fallout4.esm's records of that type
are read once and, per subrecord tag, the census keeps the sizes vanilla
writes and, for each 4-byte word of a fixed-size subrecord, the bits vanilla
ever sets there and its distinct values (up to WORD_VALUES). The plugin's
records are then checked against it:

- tag: a subrecord vanilla never writes on that record type;
- size: a size other than the one size vanilla always writes for that tag;
- bits: a word holding bits vanilla never sets at that offset, where vanilla's
  word takes at most WORD_VALUES distinct values (a flag or enum field; a
  FormID, float or text word has more and is not judged);
- record flags: header flag bits no vanilla record of that type sets.

A finding is a lead, not a defect: it says no vanilla record does this, which
is where FNV semantics leaked through (PKDT's Continue if PC near, 0 of 3,828
vanilla packages). Exit 1 when anything is found. Seconds per record type;
REFR (about a million in Fallout4.esm) is read only when named in --sigs.

See: docs/fork/fo4_pipeline.md#audit
"""

import argparse
import collections
import struct
import sys
from pathlib import Path

from fo4_import.base.install import FALLOUT4_ESM, file_masters
from tes5_import.base.tes5_reader import subrecords, walk

#: Distinct values above which a vanilla word is a FormID, float or text, not a flag or enum field.
WORD_VALUES = 64
#: Record types left out unless named: too many in Fallout4.esm to census by default.
HEAVY = frozenset({b'REFR', b'NAVM', b'LAND'})
#: Header flag bits any record may carry for the file's sake: compressed.
FILE_FLAGS = 0x40000


# ---------------------------------------------------------------------------
# The vanilla census
# ---------------------------------------------------------------------------


class Tag:
    """What vanilla writes for one (record type, subrecord tag): sizes, and per word its bits and values."""

    def __init__(self):
        """An empty census."""
        self.sizes, self.bits, self.values = set(), collections.Counter(), collections.defaultdict(set)

    def add(self, data: bytes) -> None:
        """Count one vanilla subrecord."""
        self.sizes.add(len(data))
        for off in range(0, len(data) - 3, 4):
            word = struct.unpack_from('<I', data, off)[0]
            self.bits[off] |= word
            if len(self.values[off]) <= WORD_VALUES:
                self.values[off].add(word)

    def judged(self, off: int) -> bool:
        """Whether vanilla's word at `off` is a flag or enum field (WORD_VALUES)."""
        return len(self.sizes) == 1 and len(self.values.get(off, ())) <= WORD_VALUES


def census(sigs: set) -> tuple:
    """({(sig, tag): Tag}, {sig: record flag bits}, {sig: record count}) of Fallout4.esm's records of `sigs`."""
    tags, flags, counts = collections.defaultdict(Tag), collections.Counter(), collections.Counter()
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), *sigs):
        counts[rec.sig] += 1
        flags[rec.sig] |= rec.flags
        for tag, data in subrecords(rec.body):
            tags[rec.sig, tag].add(data)
    return tags, flags, counts


# ---------------------------------------------------------------------------
# The plugin against it
# ---------------------------------------------------------------------------


def edid(subs: list, fid: int) -> str:
    """A record's EditorID, else its FormID."""
    return next((d.rstrip(b'\0').decode('latin1') for t, d in subs if t == b'EDID'), f'{fid:08X}')


def findings(raw: bytes, sigs: set, tags: dict, flags: dict, counts: dict, files: int) -> dict:
    """{finding: [record names]} of the plugin's records of `sigs` against the vanilla census; a word whose top
    byte is 1..`files` (a FormID in a master past Fallout4.esm, or the plugin's own) is not judged."""
    out = collections.defaultdict(list)
    for rec, _ in walk(raw, *sigs):
        sig, subs = rec.sig.decode(), list(subrecords(rec.body))
        name = edid(subs, rec.form_id)
        novel = rec.flags & ~flags[rec.sig] & ~FILE_FLAGS
        if novel:
            out[f'{sig} record flags 0x{novel:X}: no vanilla {sig} sets them'].append(name)
        for tag, data in subs:
            out_key = _judge(sig, tag.decode('latin1'), data, tags.get((rec.sig, tag)), counts[rec.sig], files)
            if out_key:
                out[out_key].append(name)
    return out


def _judge(sig: str, tag: str, data: bytes, seen: 'Tag | None', count: int, files: int) -> str:
    """The finding for one subrecord against vanilla's `seen`, or ''; `files` is the plugin's own load index."""
    if seen is None:
        return f'{sig} {tag}: tag no vanilla {sig} writes (of {count})'
    if len(seen.sizes) != 1:
        return ''
    if len(data) not in seen.sizes:
        return '' if _inline_string(data, seen) else f'{sig} {tag}: size {len(data)}, vanilla writes {min(seen.sizes)}'
    for off in range(0, len(data) - 3, 4):
        word = struct.unpack_from('<I', data, off)[0]
        novel = word & ~seen.bits[off]
        if novel and seen.judged(off) and not 0 < word >> 24 <= files:
            return f'{sig} {tag} +{off}: bits 0x{novel:X} no vanilla {sig} sets'
    return ''


def _inline_string(data: bytes, seen: Tag) -> bool:
    """Whether `data` is inline text where localized vanilla writes a string id."""
    return seen.sizes == {4} and data.endswith(b'\0') and all(b >= 0x20 or b in b'\t\r\n' for b in data[:-1])


def report(found: dict, examples: int) -> None:
    """Print each finding with its count and example records, most records first."""
    for key, names in sorted(found.items(), key=lambda kv: -len(kv[1])):
        print(f'{len(names):6d}  {key}')
        print('        ' + ', '.join(list(dict.fromkeys(names))[:examples]))


def main() -> int:
    """Census the plugin named on the command line against Fallout4.esm."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--sigs', nargs='*', default=[], help='record types to check (default: all but REFR/NAVM/LAND)')
    ap.add_argument('--examples', type=int, default=6)
    args = ap.parse_args()
    raw = args.plugin.read_bytes()
    present = {rec.sig for rec, _ in walk(raw, bodies=())} - {b'TES4', b'GRUP'}
    sigs = {s.encode() for s in args.sigs} & present if args.sigs else present - HEAVY
    tags, flags, counts = census(sigs)
    found = findings(raw, sigs, tags, flags, counts, len(file_masters(args.plugin)))
    report(found, args.examples)
    print(f'\n{len(found)} findings over {len(sigs)} record types')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
