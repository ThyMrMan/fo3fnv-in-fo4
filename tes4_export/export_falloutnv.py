"""
FO3/FNV export: the whole-file context its record exporters need.

Some FO3/FNV fields cannot be read from a record alone. LTEX names its texture
through a TNAM pointing at a TXST, so the TXST group has to be indexed before
any LTEX can be formatted. That is a property of the FILE, not of a record
type, so it lives beside export.py rather than in record_types/.

See: docs/commentary/tes4_export_falloutnv.md#ltex-moved-its-texture-to-a-txst
"""

import mmap
import os
import struct

from .record_types.common import escape_value
from .record_types.falloutnv import (EFFECT_TYPES, FALLOUT_BASE_EXPORTERS,
                                     MGEF_EDITOR_IDS, SUPERSEDED_ACTOR_KEYS,
                                     SUPERSEDED_EFFECT_KEYS, SUPERSEDED_IDLE_KEYS,
                                     export_deltas)
from .record_types.quest_falloutnv import SUPERSEDED_QUEST_KEYS
from .tes4_reader import Record, get_string, get_subrecord, parse_subrecords, read_group_records

#: TXST FormID -> its TX00 diffuse path, rebuilt per source file.
_TEXTURE_SETS = {}

#: Source path whose TXST records this process has already indexed.
_INDEXED_SOURCE = [None]

#: TES4-layout CSTY keys; FO3/FNV lay CSTD and CSAD out differently, so they would be misread.
_TES4_COMBAT_STYLE_KEYS = ("CSTD.", "CSAD.")

#: LTEX ICON is relative to Textures\\Landscape\\; FO3/FNV TX00 spells that prefix out.
_LANDSCAPE_PREFIX = 'landscape' + chr(92)


def base_exporter(sig: str):
    """The exporter for a FO3/FNV-only base-object type, or None."""
    return FALLOUT_BASE_EXPORTERS.get(sig)


def superseded_keys(rec: Record) -> tuple:
    """KEY= prefixes format_record drops, this game re-emitting them itself."""
    if rec.type in ("CREA", "NPC_"):
        return SUPERSEDED_ACTOR_KEYS
    if rec.type in EFFECT_TYPES:
        return SUPERSEDED_EFFECT_KEYS
    if rec.type == "QUST":
        return SUPERSEDED_QUEST_KEYS
    if rec.type == "CSTY":
        return _TES4_COMBAT_STYLE_KEYS
    if rec.type == "IDLE":
        return SUPERSEDED_IDLE_KEYS
    return ()


def export_lines(rec: Record) -> list:
    """Every FO3/FNV-only line for one record: its deltas, plus LTEX's texture."""
    lines = []
    if rec.type == "LTEX":
        icon = _ltex_icon_path(rec)
        if icon:
            lines.append(f"ICON={escape_value(icon)}")
    lines.extend(export_deltas(rec))
    return lines


def prepare_source(mm, size: int, hdr_size: int, source_path: str) -> None:
    """Index this file's TXST and MGEF records, and its masters' (read beside it), once per process.

    Export workers are spawned with no initializer and never receive the
    parent's globals, so each builds the index itself.  An FO3/FNV effect
    names its MGEF by FormID, and the import keys its effect registry on the
    EditorID; a DLC's effects mostly name its master's.
    """
    if _INDEXED_SOURCE[0] == source_path:
        return
    _TEXTURE_SETS.clear()
    MGEF_EDITOR_IDS.clear()
    for index, name in enumerate(_masters(mm, size, hdr_size)):
        path = os.path.join(os.path.dirname(source_path), name)
        if os.path.isfile(path):
            with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as master:
                _index(master, len(master), hdr_size, lambda fid, i=index, own=len(_masters(
                    master, len(master), hdr_size)): i << 24 | fid & 0xFFFFFF if fid >> 24 == own else None)
    _index(mm, size, hdr_size, lambda fid: fid)
    _INDEXED_SOURCE[0] = source_path


def _masters(mm, size: int, hdr_size: int) -> list:
    """A plugin's master file names (its header's MAST), in order."""
    end = min(size, hdr_size + struct.unpack_from('<I', mm, 4)[0])
    return [get_string(s) for s in parse_subrecords(bytes(mm[hdr_size:end])) if s.type == 'MAST']


def _index(mm, size: int, hdr_size: int, renumber) -> None:
    """Add a plugin's TXST diffuse paths and MGEF EditorIDs to the indexes, each FormID through `renumber` (None:
    not one of this plugin's own, skipped): a master's own records read as the exported plugin names them.
    See: docs/commentary/tes4_export_falloutnv.md#master-effects
    """
    for rec in read_group_records(mm, size, hdr_size, b'TXST'):
        tx00, fid = get_subrecord(rec, 'TX00'), renumber(rec.form_id)
        if tx00 and fid is not None:
            _TEXTURE_SETS[fid] = get_string(tx00)
    for rec in read_group_records(mm, size, hdr_size, b'MGEF'):
        edid, fid = get_subrecord(rec, 'EDID'), renumber(rec.form_id)
        if edid and fid is not None:
            MGEF_EDITOR_IDS[fid] = get_string(edid)


def _ltex_icon_path(rec: Record) -> str:
    """The landscape texture a FO3/FNV LTEX names, in Oblivion's ICON form.

    Relative to Textures\\Landscape\\, which is what convert_LTEX
    expects; empty when the TNAM resolves to nothing.
    """
    tnam = get_subrecord(rec, 'TNAM')
    if not tnam or len(tnam.data) < 4:
        return ''
    path = _TEXTURE_SETS.get(struct.unpack_from('<I', tnam.data, 0)[0], '')
    normalized = path.replace('/', chr(92))
    if normalized.lower().startswith(_LANDSCAPE_PREFIX):
        return normalized[len(_LANDSCAPE_PREFIX):]
    return normalized
