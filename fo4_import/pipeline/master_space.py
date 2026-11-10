"""A master's export records in its dependent's FormID numbering.

A FormID's top byte indexes its plugin's master list (its own records take the next index), so a master's records
read behind a plugin with several masters (a mod on FalloutNV.esm and the DLCs) name forms by the master's list,
not the plugin's: Honest Hearts' own 01xxxxxx is 02xxxxxx in a mod listing Dead Money first. byte_map() gives the
master's index -> the plugin's, renumber_record() rewrites a record's FormID fields through it: the keys
data/export_formid_keys.json classifies as FormIDs, conditions by xEdit's parameter types, navmesh door and edge
links. A key it classifies neither way is counted in UNCLASSIFIED, which the build reports. A single-master
plugin's map is the identity and is never applied.

See: docs/fork/fo4_plugin_layout.md#multi-master
"""

import collections
import functools
import json
import re
import struct
from pathlib import Path

from tools.dialog.tes4_ctda_dump import xedit_table

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'export_formid_keys.json'
HEX = re.compile(r'^[0-9A-Fa-f]{8}$')
#: A raw dump's hex: longer than one value, with a hex letter (so a long decimal is not one).
BLOB = re.compile(r'^(?=.*[A-Fa-f])[0-9A-Fa-f]{9,}$')
#: Keys the exporter writes raw subrecord bytes under: a bare signature, `.Raw`, `Hex`.
RAW_KEY = re.compile(r'^[A-Z0-9_]{4}(\[\])?$|\.Raw$|Hex$')
INDEX = re.compile(r'\[\d+\]')
#: FNV CTDA: flags, comparison value (a global's FormID with USE_GLOBAL), function, two params, run on, reference.
CTDA = struct.Struct('<B3xIH2xIIII')
USE_GLOBAL, RUN_REFERENCE = 0x04, 2
#: FNV NVDP (door ref, triangle) and NVEX (type, navmesh, triangle) entries: (stride, FormID offset).
LINKS = {'NVDP': (8, 0), 'NVEX': (10, 4)}
#: Keys met while renumbering that the table classifies neither way: {key: count}; the build reports them.
UNCLASSIFIED = collections.Counter()


@functools.cache
def table() -> dict:
    """data/export_formid_keys.json, its lists as sets."""
    raw = json.loads(TABLE.read_text(encoding='utf-8'))
    return {key: set(value) if isinstance(value, list) else value for key, value in raw.items()}


@functools.cache
def condition_slots(game: str) -> dict:
    """{condition function: its FormID parameter slots} for `game` (xEdit)."""
    return xedit_table(game).form_slots


def byte_map(child_masters: list, master: str, master_masters: list) -> tuple:
    """`master`'s FormID index -> the child's: its masters', then its own, by the child's master list."""
    lower = [m.lower() for m in child_masters]
    missing = [m for m in (*master_masters, master) if m.lower() not in lower]
    if missing:
        raise SystemExit(f'{master}: its masters {missing} are not masters of the plugin built on it')
    return tuple(lower.index(m.lower()) for m in (*master_masters, master))


def identity(mapping: tuple) -> bool:
    """Whether `mapping` changes no index."""
    return mapping == tuple(range(len(mapping)))


def renumber(fid: int, mapping: tuple) -> int:
    """FormID `fid` through `mapping`; an index past it (no such master) as is."""
    byte = fid >> 24
    return mapping[byte] << 24 | fid & 0xFFFFFF if fid and byte < len(mapping) else fid


def renumber_record(rec: dict, mapping: tuple, game: str) -> dict:
    """Export record `rec`, its FormID fields through `mapping` (`game`: fnv, fo3)."""
    return {key: _value(INDEX.sub('[]', key), value, mapping, game) if isinstance(value, str) else value
            for key, value in rec.items()}


def _value(key: str, value: str, mapping: tuple, game: str) -> str:
    """One export value, renumbered when the table names `key` a FormID or a known blob."""
    known = table()
    if key == 'FormID' or key in known['formid']:
        return f'{renumber(int(value, 16), mapping):08X}' if HEX.match(value) else value
    if key.endswith(known['blobs']['conditions']):
        return _condition(value, mapping, game)
    if key in LINKS:
        return _links(value, mapping, *LINKS[key])
    if (HEX.match(value) and key not in known['not_formid']) or (
            BLOB.match(value) and RAW_KEY.search(key) and key not in known['not_formid_blobs']):
        UNCLASSIFIED[key] += 1
    return value


def _condition(raw_hex: str, mapping: tuple, game: str) -> str:
    """An exported condition's hex, renumbered (condition_bytes)."""
    return condition_bytes(bytes.fromhex(raw_hex), mapping, game).hex()


def condition_bytes(data: bytes, mapping: tuple, game: str) -> bytes:
    """An FNV/FO3 condition with its global, FormID params and reference renumbered (shorter: as is)."""
    raw = bytearray(data)
    if len(raw) < CTDA.size:
        return data
    flags, value, func, p1, p2, run_on, ref = CTDA.unpack_from(raw)
    slots = condition_slots(game).get(func, set())
    CTDA.pack_into(raw, 0, flags, renumber(value, mapping) if flags & USE_GLOBAL else value, func,
                   renumber(p1, mapping) if 1 in slots else p1, renumber(p2, mapping) if 2 in slots else p2,
                   run_on, renumber(ref, mapping) if run_on == RUN_REFERENCE else ref)
    return bytes(raw)


def _links(raw_hex: str, mapping: tuple, stride: int, at: int) -> str:
    """Navmesh link entries' hex (`stride` bytes each, a FormID at `at`) renumbered."""
    raw = bytearray(bytes.fromhex(raw_hex))
    for start in range(0, len(raw) - stride + 1, stride):
        struct.pack_into('<I', raw, start + at, renumber(struct.unpack_from('<I', raw, start + at)[0], mapping))
    return raw.hex()
