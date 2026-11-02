"""Headless check that every FormID in a built Fallout 4 plugin resolves to a record in it or one of its masters.

    py -3.14 -m tools.validate.fo4_ref_check <plugin.esp> [--plugin-dirs DIR ...] [--show N]

Covers FO4Edit's "Could not be resolved" class only: script properties, conditions and FORMID_SUBS fields.
Exit 1 when anything is unresolved.

See: docs/reference/python_tools.md#fo4-ref-check
"""

import argparse
import collections
import struct
import sys
import time
from pathlib import Path

from fo4_import.base.dangling_scripts import Unreadable, object_offsets
from fo4_import.base.install import FALLOUT4_DIR
from tes5_import.base.tes5_reader import masters, subrecords, walk, zstr

#: Engine forms in Fallout4.esm's space (inclusive): PlayerRef 00000014 + xEdit's Core/Hardcoded/Fallout4.esp.
HARDCODED_RANGES = (
    (0x14, 0x14), (0x1A, 0x1A), (0x1C, 0x1C), (0x31, 0x31), (0x5B, 0x5B), (0x63, 0x63), (0x176, 0x176),
    (0x179, 0x179), (0x276, 0x276), (0x2BC, 0x2BF), (0x2C1, 0x2C1), (0x2CA, 0x2CB), (0x2CE, 0x2D3), (0x2D6, 0x2D6),
    (0x2D8, 0x2D9), (0x2DB, 0x2DB), (0x2DD, 0x2DE), (0x2E0, 0x2E0), (0x2E2, 0x2E2), (0x2E8, 0x2E8), (0x2EC, 0x2F2),
    (0x2F4, 0x2F5), (0x2F7, 0x2F7), (0x2F9, 0x332), (0x334, 0x343), (0x345, 0x34B), (0x34D, 0x357), (0x359, 0x35A),
    (0x35C, 0x36B), (0x373, 0x374), (0x376, 0x389))
HARDCODED = frozenset(i for start, end in HARDCODED_RANGES for i in range(start, end + 1))

#: A field holding one FormID at each offset.
ONE = (0, (0,))
#: A field that is an array of FormIDs.
ARRAY = (4, (0,))
#: A field a COMMON tag names that this record defines as data instead (no offsets read).
NOT_FORMID = (0, ())

#: {subrecord: (stride or 0 for once, offsets)} that are FormIDs on any record: xEdit's shared helpers (wbCNTO...).
COMMON = {
    b'KWDA': ARRAY, b'APPR': ARRAY, b'PRPS': (8, (0,)), b'CNTO': ONE, b'COED': ONE, b'EFID': ONE, b'ETYP': ONE,
    b'PTRN': ONE, b'YNAM': ONE, b'ZNAM': ONE, b'CUSD': ONE, b'NTRM': ONE, b'SPLO': ONE, b'EITM': ONE,
    b'XESP': ONE, b'XOWN': ONE,
}

#: {record: {subrecord: (stride, offsets)}}, each confirmed a FormID in wbDefinitionsFO4.pas; never guess one.
FORMID_SUBS = {
    b'REFR': {b'NAME': ONE, b'INAM': ONE, b'XEMI': ONE, b'XLKR': (0, (0, 4)), b'XTEL': (0, (0, 32)),
              b'XAPR': ONE, b'XLOC': (0, (4,)), b'XNDP': ONE, b'XPOD': ARRAY, b'XORD': ARRAY, b'XLRT': ARRAY,
              b'XEZN': ONE, b'XLCN': ONE, b'XLRL': ONE, b'XMBR': ONE, b'XTNM': ONE},
    b'ACHR': {b'NAME': ONE, b'XLKR': (0, (0, 4)), b'XAPR': ONE, b'XEZN': ONE, b'XLCN': ONE},
    b'PHZD': {b'NAME': ONE, b'XLKR': (0, (0, 4)), b'XAPR': ONE},
    b'CELL': {b'LTMP': ONE, b'XCAS': ONE, b'XCIM': ONE, b'XCMO': ONE, b'XEZN': ONE, b'XLCN': ONE,
              b'XCLR': ARRAY, b'XPRI': ARRAY, b'XCWT': ONE, b'XILL': ONE},
    b'WRLD': {b'CNAM': ONE, b'NAM2': ONE, b'ZNAM': ONE, b'XLCN': ONE},
    b'LAND': {b'ATXT': ONE, b'BTXT': ONE},
    b'INFO': {b'ANAM': ONE, b'LNAM': ONE, b'SNAM': ONE, b'TSCE': ONE, b'TRDA': (0, (0, 5)),
              b'TPIC': ONE, b'PNAM': ONE, b'DNAM': ONE, b'GNAM': ONE},
    b'DIAL': {b'BNAM': ONE, b'QNAM': ONE},
    b'DLBR': {b'QNAM': ONE, b'SNAM': ONE},
    b'SCEN': {b'PNAM': ONE, b'NETO': ONE, b'NPOT': ONE, b'NTOP': ONE, b'PTOP': ONE, b'QTOP': ONE},
    b'QUST': {b'ALFR': ONE, b'ALUA': ONE, b'ALDN': ONE, b'ALFV': ONE, b'ALDI': ONE, b'ALSP': ONE, b'ALFC': ONE,
              b'ALPC': ONE, b'VTCK': ONE, b'QSTA': (0, (8,))},
    b'PACK': {b'INAM': ONE, b'QNAM': ONE, b'PKCU': (0, (4,)), b'TPIC': ONE},
    b'NPC_': {b'ANAM': ONE, b'ATKR': ONE, b'CNAM': ONE, b'CSCR': ONE, b'DOFT': ONE, b'DPLT': ONE, b'ECOR': ONE,
              b'FTST': ONE, b'HCLF': ONE, b'INAM': ONE, b'PKID': ONE, b'PNAM': ONE, b'RNAM': ONE, b'TPLT': ONE,
              b'TPTA': ARRAY, b'VTCK': ONE, b'WNAM': ONE, b'ZNAM': ONE, b'SNAM': ONE, b'PRKR': ONE, b'RCLR': ONE,
              b'SPOR': ONE, b'OCOR': ONE, b'GWOR': ONE, b'FCPL': ONE, b'LTPT': ONE, b'LTPC': ONE},
    b'FACT': {b'XNAM': ONE, b'VENC': ONE, b'VEND': ONE, b'JAIL': ONE, b'WAIT': ONE, b'STOL': ONE, b'PLCN': ONE,
              b'CRGR': ONE, b'JOUT': ONE},
    b'OTFT': {b'INAM': ARRAY},
    b'FLST': {b'LNAM': ONE},
    b'LVLI': {b'LVLO': (0, (4,))},
    b'LVLN': {b'LVLO': (0, (4,))},
    b'CONT': {b'QNAM': ONE, b'SNAM': ONE},
    b'ACTI': {b'SNAM': ONE, b'WNAM': ONE},
    b'MSTT': {b'SNAM': ONE},
    b'LIGH': {b'SNAM': ONE},
    b'DOOR': {b'ANAM': ONE, b'BNAM': ONE, b'SNAM': ONE},
    b'ARMO': {b'RNAM': ONE},
    b'ARMA': {b'RNAM': ONE, b'SNDD': ONE, b'MO2S': ONE, b'MO3S': ONE, b'MO4S': ONE, b'MO5S': ONE},
    b'WEAP': {b'BAMT': ONE, b'BIDS': ONE, b'INAM': ONE, b'LNAM': ONE, b'WAMD': ONE, b'WZMD': ONE, b'CNAM': ONE,
              b'CRDT': (0, (8,)), b'FNAM': (0, (29,)),
              b'DNAM': (0, (0, 40, 44, 73, 77, 81, 85, 89, 93, 97, 101))},
    b'ALCH': {b'ENIT': (0, (8, 16))},
    b'ENCH': {b'ENIT': (0, (28, 32))},
    b'BOOK': {b'INAM': ONE},
    b'SOUN': {b'SDSC': ONE},
    b'SNDR': {b'GNAM': ONE, b'ONAM': ONE},
    b'REGN': {b'RDMO': ONE, b'WNAM': ONE, b'RDWT': (12, (0, 8))},
    b'CLMT': {b'WLST': (12, (0, 8))},
    b'OMOD': {b'FNAM': ARRAY, b'MNAM': ARRAY, b'LNAM': ONE},
    b'COBJ': {b'BNAM': ONE, b'CNAM': ONE, b'FNAM': ARRAY, b'FVPA': (8, (0,))},
    b'TERM': {b'TNAM': ONE},
    b'PERK': {b'NNAM': ONE},
    b'FURN': {b'SNAM': (24, (16,)), b'WNAM': ONE, b'NAM1': ONE},
    b'LTEX': {b'GNAM': ONE, b'MNAM': ONE, b'TNAM': ONE},
    b'IDLE': {b'ANAM': (0, (0, 4))},
    b'ASPC': {b'BNAM': ONE, b'RDAT': ONE, b'SNAM': ONE},
    b'LCTN': {b'MNAM': ONE, b'PNAM': ONE},
    b'MUSC': {b'TNAM': ARRAY},
    b'WATR': {b'INAM': ONE, b'SNAM': ONE, b'TNAM': ONE, b'XNAM': ONE, b'YNAM': ONE},
    b'WTHR': {b'GNAM': ONE, b'MNAM': ONE, b'NNAM': ONE, b'TNAM': ONE},
    b'SMQN': {b'NNAM': ONE, b'PNAM': ONE, b'SNAM': ONE},
    b'RACE': {b'ZNAM': NOT_FORMID},
    b'LSCR': {b'ZNAM': NOT_FORMID},
}

#: {subrecord: u32 type values at offset 0 for which offset 4 is a FormID} (wbPDTO, wbPLDT, wbPLVD, wbTargetData).
TYPED = {b'PDTO': {0}, b'PLDT': {0, 1, 4, 6}, b'PLVD': {0, 1, 4, 6}, b'PTDA': {0, 1, 3, 7}}

#: (record, subrecord) where 0xFFFFFFFF is a legal "none" (TRDA's emotion allows FFFF).
FFFF_OK = {(b'INFO', b'TRDA')}

#: Condition functions (FO4 index) whose parameter #1 / #2 is a form, from xEdit's wbConditionFunctions.
PARAM1_FORM = frozenset((
    1, 14, 27, 32, 42, 43, 44, 45, 47, 56, 58, 59, 60, 66, 67, 68, 69, 71, 72, 73, 74, 79, 84, 99, 109, 117, 122,
    131, 132, 136, 142, 149, 152, 161, 162, 163, 172, 180, 182, 193, 195, 197, 199, 214, 223, 228, 230, 246, 248,
    250, 258, 259, 261, 262, 264, 277, 278, 280, 310, 359, 362, 366, 370, 372, 373, 375, 376, 378, 398, 403, 408,
    409, 410, 414, 426, 438, 439, 444, 445, 448, 449, 450, 459, 463, 465, 477, 479, 493, 494, 497, 501, 506, 507,
    510, 511, 512, 513, 515, 516, 517, 518, 522, 523, 524, 525, 533, 534, 535, 543, 550, 552, 560, 561, 562, 563,
    565, 577, 584, 591, 592, 595, 603, 606, 617, 624, 625, 629, 637, 639, 640, 650, 651, 652, 661, 664, 678, 682,
    691, 693, 696, 697, 699, 705, 707, 713, 719, 720, 722, 736, 741, 742, 749, 753, 754, 766, 772, 773, 783, 802,
    804, 806, 807, 808, 809, 810))
PARAM2_FORM = frozenset((60, 180, 181, 230, 258, 280, 410, 576, 577, 591, 592, 596, 600, 601, 603, 604, 605, 606,
                         608, 610, 650))
#: Of those, the ones typed Reference, Actor or Package: an alias (Type & 2) or packdata (Type & 8) instead.
PARAM1_ALIASABLE = frozenset((
    1, 27, 32, 42, 43, 44, 45, 66, 79, 99, 122, 132, 136, 161, 162, 172, 180, 258, 259, 261, 370, 378, 403, 408,
    414, 438, 449, 463, 477, 512, 513, 515, 516, 517, 518, 522, 523, 524, 525, 577, 584, 603, 624, 639, 650, 652,
    678, 705, 719, 720, 753, 754, 772, 773, 802, 804, 806, 807, 808, 809, 810))
PARAM2_ALIASABLE = frozenset((60, 230, 577))
#: GetIsCurrentPackage keeps its package in parameter #1 when run on a quest alias.
GET_IS_CURRENT_PACKAGE = 161
#: CTDA Type flags and Run On values.
USE_GLOBAL, USE_ALIASES, USE_PACKDATA = 4, 2, 8
RUN_ON_REFERENCE, RUN_ON_QUEST_ALIAS = 2, 5


def ctda_formids(data: bytes) -> list:
    """(field name, FormID) of each form-typed field in one 32-byte FO4 CTDA."""
    if len(data) < 28:
        return []
    kind, comp, func, p1, p2, run_on, ref = struct.unpack_from('<B3xIH2xIIII', data)
    out = [('Comparison Global', comp)] if kind & USE_GLOBAL else []
    if func in PARAM1_FORM:
        if func not in PARAM1_ALIASABLE:
            out.append(('Parameter #1', p1))
        elif kind & USE_ALIASES:
            if run_on == RUN_ON_QUEST_ALIAS and func == GET_IS_CURRENT_PACKAGE:
                out.append(('Parameter #1', p1))
        elif not kind & USE_PACKDATA:
            out.append(('Parameter #1', p1))
    if func in PARAM2_FORM and not (func in PARAM2_ALIASABLE and kind & (USE_ALIASES | USE_PACKDATA)):
        out.append(('Parameter #2', p2))
    if run_on == RUN_ON_REFERENCE:
        out.append(('Reference', ref))
    return out


def field_formids(sig: bytes, tag: bytes, data: bytes) -> list:
    """FormIDs in one subrecord per COMMON / FORMID_SUBS / TYPED; [] for fields not listed."""
    if tag in TYPED:
        return [struct.unpack_from('<I', data, 4)[0]] if len(data) >= 8 and \
            struct.unpack_from('<I', data)[0] in TYPED[tag] else []
    spec = FORMID_SUBS.get(sig, {}).get(tag) or COMMON.get(tag)
    if spec is None:
        return []
    stride, offsets = spec
    starts = range(0, len(data), stride) if stride else (0,)
    return [struct.unpack_from('<I', data, s + o)[0] for s in starts for o in offsets if s + o + 4 <= len(data)]


def vmad_refs(sig: bytes, data: bytes) -> list:
    """(field, FormID) of each object property in one VMAD; [('VMAD?', None)] when it is not walkable."""
    try:
        return [('VMAD property', struct.unpack_from('<I', data, at)[0]) for at in object_offsets(sig, data)]
    except (Unreadable, struct.error, IndexError):
        return [('VMAD?', None)]


def record_refs(sig: bytes, body: bytes):
    """(field, FormID) of each FormID in one record body; field 'VMAD?' when its VMAD is not walkable."""
    for tag, data in subrecords(body):
        if tag == b'VMAD':
            yield from vmad_refs(sig, data)
        elif tag == b'CTDA':
            yield from ((f'CTDA {name}', fid) for name, fid in ctda_formids(data))
        else:
            none_ok = (sig, tag) in FFFF_OK
            yield from ((tag.decode('latin-1'), fid) for fid in field_formids(sig, tag, data)
                        if not (none_ok and fid == 0xFFFFFFFF))


def defined(path: Path, names: list) -> set:
    """FormIDs the file at `path` defines or overrides, restated in the load order `names` (lowercased)."""
    raw = path.read_bytes()
    own = masters(raw) + [path.name.lower()]
    slots = [names.index(n) if n in names else None for n in own]
    out = set()
    for record, _ in walk(raw, bodies=()):
        index = record.form_id >> 24
        slot = slots[index] if index < len(slots) else None
        if slot is not None:
            out.add(slot << 24 | record.form_id & 0xFFFFFF)
    return out


def find(name: str, dirs: list):
    """The first file `name` in `dirs`, or None."""
    return next((Path(d) / name for d in dirs if (Path(d) / name).is_file()), None)


def master_forms(plugin: Path, names: list, dirs: list) -> tuple:
    """(FormIDs the masters in load order `names` define, restated in it; names of masters not found)."""
    known, missing = set(HARDCODED) if names[0] == 'fallout4.esm' else set(), []
    for name in names[:-1]:
        path = find(name, [FALLOUT4_DIR / 'Data', plugin.parent, *dirs])
        if path is None:
            missing.append(name)
        else:
            known |= defined(path, names)
    return known, missing


def check(plugin: Path, dirs: list) -> dict:
    """{'unresolved': {(kind, record, field): [(record FormID, EditorID, FormID)]}, 'missing': [master names],
    'checked': n, 'unchecked': n, 'unreadable': n, 'records': n}."""
    raw = plugin.read_bytes()
    names = masters(raw) + [plugin.name.lower()]
    own = len(names) - 1
    known, missing = master_forms(plugin, names, dirs)
    skip = {names.index(n) for n in missing}
    found = collections.defaultdict(list)
    result = {'unresolved': found, 'missing': missing, 'checked': 0, 'unchecked': 0, 'unreadable': 0}
    bodies, edids = [record for record, _ in walk(raw)], {}
    result['records'] = len(bodies)
    known.update(record.form_id for record in bodies if record.form_id >> 24 <= own)
    for record in bodies:
        for field, fid in record_refs(record.sig, record.body):
            if fid is None:
                result['unreadable'] += 1
                continue
            if not fid:
                continue
            index = fid >> 24
            if index in skip:
                result['unchecked'] += 1
                continue
            result['checked'] += 1
            if fid in known:
                continue
            kind = 'no such master' if index > own else 'unresolved'
            if record.form_id not in edids:
                edids[record.form_id] = zstr(dict(subrecords(record.body)).get(b'EDID', b''))
            found[(kind, record.sig.decode(), field)].append((record.form_id, edids[record.form_id], fid))
    return result


def report(result: dict, show: int) -> int:
    """Print the findings grouped by kind and field; the number of unresolved references."""
    for name in result['missing']:
        print(f'# master {name} not found: its references are not judged')
    print(f"# {result['records']} records, {result['checked']} references checked, {result['unchecked']} into "
          f"missing masters, {result['unreadable']} VMADs not walkable")
    groups = result['unresolved']
    for (kind, sig, field), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f'{len(items):6d}  {kind}: {sig} {field}')
        for rec_fid, edid, fid in items[:show]:
            print(f'        {edid or "-"} [{sig}:{rec_fid:08X}] {field} -> [{fid:08X}]')
    total = sum(map(len, groups.values()))
    print(f'{total} unresolved references in {len(groups)} kinds')
    return total


def main() -> int:
    """Check the plugin; print what does not resolve; 1 when anything does not."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('plugin', type=Path)
    ap.add_argument('--plugin-dirs', nargs='*', default=(), help='Folders holding masters other than Fallout4.esm')
    ap.add_argument('--show', type=int, default=5, help='Examples per error kind')
    args = ap.parse_args()
    started = time.time()
    total = report(check(args.plugin.resolve(), args.plugin_dirs), args.show)
    print(f'# {time.time() - started:.1f} s')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
