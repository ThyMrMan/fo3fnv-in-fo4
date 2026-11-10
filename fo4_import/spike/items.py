"""FNV items, leveled items and containers as FO4 records, for the cell spike.

A misc item keeps its name, model, value and weight; a leveled item its
chance none, flags and the entries whose items convert; a container its
model, flags, weight and the contents that convert; a book or note is the
cell builder's (spike.readables). FNV's engine objects (FormID below ENGINE_IDS) that
Fallout4.esm has under the same FormID, type and EditorID are FO4's own
(the bottle cap, COC and X markers), and an item the replacement table
names as an `item` is that record itself (spike.replacements). Consumables and
ammunition are made by consumables.Consumables, weapons and armor by
equipment.Equipment. A form list keeps the entries the build makes: items
(made now), and the forms the cell builder has already made (BUILT_MAPS:
placed bases, actors and their bases, globals, factions; its creatures) or
converts on demand (messages); each other entry is dropped and counted by
type, and a list whose every entry is dropped is not made (a script property
naming it stays unfilled; one FNV leaves empty is made empty). Any other type
is skipped and counted.

See: docs/fork/fo4_spikes.md#spike-2-items
See: docs/fork/fo4_tool_audit.md#fix-first
"""

import struct
from pathlib import Path

from fo4_import.base.install import source_walk
from fo4_import.spike import records as R
from fo4_import.spike.entry_condition import condition_of
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.stage_timer import charged
from script_convert.constants_falloutnv import ITEM_TYPE_CODES, ITEM_TYPE_LISTS

#: FNV's engine objects sit below this FormID.
ENGINE_IDS = 0x800
#: FNV's engine portal and plane markers (no FalloutNV.esm record), Fallout4.esm's PortalMarker and PlaneMarker.
PORTAL_MARKER, PLANE_MARKER = 0x20, 0x17
#: FNV casino item types FO4 lacks, each made a MISC carrying its keyword (EditorID).
CASINO_ITEMS = {'CCRD': 'F3NV_CaravanCard', 'CMNY': 'F3NV_CaravanMoney', 'CHIP': 'F3NV_CasinoChip'}
#: FO4's leveled list entry count (LLCT) is a byte; the derive_formid site of a longer list's parts (key: FormID, part).
MAX_ENTRIES, PART_SITE = 255, 'FNV LVLI part'
#: FNV record types an inventory may name, indexed for conversion (the rest are skipped).
ITEM_TYPES = ('MISC', 'LVLI', 'ALCH', 'WEAP', 'ARMO', 'AMMO', 'BOOK', 'KEYM', 'NOTE', 'CONT', 'FLST', 'IMOD',
              *CASINO_ITEMS)
#: FO4 container DATA flags kept from FNV (same bit): Respawns.
CONTAINER_FLAGS = 0x2
#: Item type list property -> its FO3/FNV type code (RemoveAllTypedItems).
TYPE_LIST_CODES = {name: code for code, name in ITEM_TYPE_LISTS.items()}
#: Cell builder maps {FNV FormID: FO4 FormID} of the non-item forms it has made, which a form list may hold.
BUILT_MAPS = ('made', 'actor_refs', 'npc_ids', 'globals', 'factions')


def _edid(rec) -> str:
    """A plugin record's EditorID."""
    return (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')


def shared_engine_ids(fo4_esm: bytes, fnv: dict, types: tuple) -> dict:
    """{FNV FormID: FO4 FormID} of FNV engine objects Fallout4.esm has with the same FormID, type and EditorID,
    and the portal and plane markers (PORTAL_MARKER, PLANE_MARKER).

    `fnv` is {FormID: (type, export record)}.
    """
    out = {PORTAL_MARKER: PORTAL_MARKER, PLANE_MARKER: PLANE_MARKER}
    for rec, _ in walk(fo4_esm, *(t.encode() for t in types)):
        if rec.form_id >= ENGINE_IDS or rec.form_id not in fnv:
            continue
        sig, fnv_rec = fnv[rec.form_id]
        edid = _edid(rec)
        if sig == rec.sig.decode() and edid == fnv_rec.get('EditorID'):
            out[rec.form_id] = rec.form_id
    return out


def index(export_dir: Path, types: tuple) -> dict:
    """{FormID: (type, export record)} of every exported record of `types`."""
    out = {}
    for sig in types:
        out.update({int(r['FormID'], 16): (sig, r) for r in export_records(export_dir, sig)})
    return out


def _bounds(rec: dict) -> tuple:
    """An export record's OBND."""
    return tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))


def _list(rec: dict, prefix: str, fields: tuple) -> list:
    """An export record's numbered entries `prefix`[i].field, as tuples of `fields` (FormIDs hex, rest int)."""
    out, i = [], 0
    while f'{prefix}[{i}].FormID' in rec:
        out.append(tuple(int(rec[f'{prefix}[{i}].{f}'], 16 if f == 'FormID' else 10) for f in fields))
        i += 1
    return out


class Items:
    """FO4 records for FNV items and containers, each made once, written through a cell builder."""

    def __init__(self, builder, records: dict, shared: dict, makers: 'dict | None' = None,
                 stand_ins: 'dict | None' = None):
        """Items made through `builder`, from index() `records`, sharing `shared` and `stand_ins` {FNV EditorID:
        FormID} (replacements.items).

        `makers` is {type: maker(FNV FormID, record) -> FormID or None} for the types made elsewhere
        (consumables, equipment); a type with no maker here or there is skipped.
        """
        self.builder, self.records, self.made, self.makers = builder, records, {}, makers or {}
        self.messages, self.type_lists, self.casino = None, set(), None
        named = {rec.get('EditorID'): fid for fid, (_, rec) in records.items()}
        self.names = {name.lower(): fid for name, fid in named.items() if name}
        self.shared = {**shared, **{named[e]: fid for e, fid in (stand_ins or {}).items() if e in named}}

    def by_name(self, edid: str) -> 'int | None':
        """item() of the FNV record named `edid` (any case), or None."""
        fid = self.names.get(edid.lower())
        return self.item(fid) if fid is not None else None

    def type_list(self, name: str) -> 'int | None':
        """Item type list `name`'s FormID (ITEM_TYPE_LISTS), written by write_type_lists; None for another name."""
        if name not in TYPE_LIST_CODES:
            return None
        self.type_lists.add(name)
        return self.builder.writer.derive_formid('FLST', name)

    def write_type_lists(self) -> None:
        """Write each type list a script names: the FO4 forms made for the FNV items of its type, made or shared.
        See: docs/fork/script_markers.md#removealltypeditems
        """
        for name in sorted(self.type_lists):
            sig = ITEM_TYPE_CODES[TYPE_LIST_CODES[name]]
            forms = {self.made.get(fnv) or self.shared.get(fnv) for fnv, (s, _) in self.records.items() if s == sig}
            self.builder.writer.add_record('FLST', R.pack_flst(self.type_list(name), name, sorted(forms - {None})))
        self.builder.counts['item type lists'] = len(self.type_lists)

    def wearable(self, fnv_fid: int, seen: tuple = ()) -> bool:
        """Whether an FNV item is worn: armor, or a leveled list of worn items only."""
        sig, rec = self.records.get(fnv_fid, (None, None))
        if sig != 'LVLI' or fnv_fid in seen:
            return sig == 'ARMO'
        entries = _list(rec, 'Entry', ('FormID',))
        return bool(entries) and all(self.wearable(entry, seen + (fnv_fid,)) for (entry,) in entries)

    def item(self, fnv_fid: int) -> 'int | None':
        """The FO4 record for an FNV item, leveled item or container; None when its type is not converted."""
        if fnv_fid in self.shared:
            return self.shared[fnv_fid]
        if fnv_fid not in self.made:
            self.made[fnv_fid] = None
            sig, rec = self.records.get(fnv_fid, (None, None))
            if sig is None:
                self.builder.counts[f'item skipped (not an item: {self._type(fnv_fid)})'] += 1
                return None
            self.made[fnv_fid] = charged(f'item {sig}', self._make, sig, rec)
        return self.made[fnv_fid]

    def _make(self, sig: str, rec: dict) -> 'int | None':
        """Write the FO4 record of a convertible FNV record; its FormID, or None (counted as skipped)."""
        maker = {'MISC': self._misc, 'KEYM': self._key, 'LVLI': self._leveled, 'CONT': self._container,
                 'NOTE': self._readable, 'BOOK': self._readable, 'FLST': self._form_list,
                 **dict.fromkeys(CASINO_ITEMS, self._casino)}.get(sig)
        if sig in self.makers:
            made = self.makers[sig](int(rec['FormID'], 16), rec)
            if made is None:
                self.builder.counts[f'item skipped ({sig})'] += 1
            return made
        if maker is None:
            self.builder.counts[f'item skipped ({sig})'] += 1
            return None
        return maker(rec)

    def _write(self, sig: str, record_of, rec: dict) -> int:
        """Add the record `record_of(FormID)` of type `sig` made from FNV `rec`; its FormID (FNV's)."""
        fid = self.builder.fnv_id(rec['FormID'])
        self.builder.writer.add_record(sig, record_of(fid))
        self.builder.counts[sig] += 1
        return fid

    def _key(self, rec: dict) -> 'int | None':
        """A key: a misc item's fields as a FO4 KEYM, which locks name."""
        return self._misc(rec, 'KEYM', R.pack_keym)

    def _misc(self, rec: dict, sig: str = 'MISC', pack=R.pack_misc) -> 'int | None':
        """A misc item (or a record of `sig` packed alike by `pack`); one FNV keeps only in inventory has no model,
        as Fallout4.esm's MS04_ShroudCostume."""
        model, bounds = self.builder.mesh(rec['Model.MODL']) if 'Model.MODL' in rec else ('', None)
        return self._write(sig, lambda fid: pack(
            fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds or _bounds(rec), int(rec.get('DATA.Value', 0)),
            float(rec.get('DATA.Weight', 0.0)), self._vmad(rec)), rec)

    def _casino(self, rec: dict) -> int:
        """A Caravan card, Caravan money or casino chip as a MISC with its CASINO_ITEMS keyword: FNV's name, model,
        bounds, script and value (DATA; a chip has none), read from the plugin, as the export holds their sizes only.
        See: docs/fork/fo4_casino_plan.md#items-built
        """
        if self.casino is None:
            sigs = (sig.encode() for sig in CASINO_ITEMS)
            self.casino = {r.form_id: dict(subrecords(r.body)) for r, _ in source_walk(*sigs)}
        subs, text = self.casino[int(rec['FormID'], 16)], lambda tag: subs.get(tag, b'').rstrip(b'\0').decode('cp1252')
        model, bounds = self.builder.mesh(text(b'MODL')) if b'MODL' in subs else ('', None)
        data, script = subs.get(b'DATA', b''), subs.get(b'SCRI')
        value = struct.unpack_from('<I', data)[0] if len(data) >= 4 else 0
        vmad = self.builder.scripts.vmad(struct.unpack('<I', script)[0]) if script else b''
        keyword = self.builder.type_keywords.keyword(CASINO_ITEMS[rec['Signature']])
        return self._write('MISC', lambda fid: R.pack_misc(
            fid, f'FNV_{rec["EditorID"]}', text(b'FULL'), model, bounds or struct.unpack('<6h', subs[b'OBND']), value,
            0.0, vmad, (keyword,)), rec)

    def _vmad(self, rec: dict) -> bytes:
        """The VMAD attaching FNV item `rec`'s converted script; b'' without one."""
        return self.builder.scripts.vmad(int(rec['SCRI'], 16)) if 'SCRI' in rec else b''

    def _leveled(self, rec: dict) -> 'int | None':
        """A leveled item with the entries whose items convert; None when none do."""
        listed, fnv = _list(rec, 'Entry', ('Level', 'FormID', 'Count')), int(rec['FormID'], 16)
        entries = [(level, self.item(fid), count, condition_of(fnv, i)) for i, (level, fid, count) in enumerate(listed)]
        entries = [e for e in entries if e[1] is not None]
        if not entries:
            return None
        flags = int(rec.get('LVLF.Flags', 0))
        return self._write('LVLI', lambda fid: R.pack_leveled(
            'LVLI', fid, f'FNV_{rec["EditorID"]}', int(rec.get('LVLD.ChanceNone', 0)), flags,
            self._parts(rec, entries, flags)), rec)

    def _parts(self, rec: dict, entries: list, flags: int) -> list:
        """FNV list `rec`'s `entries`; past MAX_ENTRIES, equal sub-lists of them (FNV's `flags`), one entry each.
        See: docs/fork/fo4_casino_plan.md#items-built
        """
        if len(entries) <= MAX_ENTRIES:
            return entries
        count = -(-len(entries) // MAX_ENTRIES)
        size, out = -(-len(entries) // count), []
        for i in range(count):
            fid = self.builder.writer.derive_formid(PART_SITE, f'{rec["FormID"]} {i}')
            self.builder.writer.add_record('LVLI', R.pack_leveled(
                'LVLI', fid, f'FNV_{rec["EditorID"]}_Part{i}', 0, flags, entries[i * size:(i + 1) * size]))
            out.append((1, fid, 1))
        self.builder.counts['LVLI split (over 255 entries)'] += 1
        return out

    def _container(self, rec: dict) -> 'int | None':
        """A container with the contents that convert."""
        if 'Model.MODL' not in rec:
            return None
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        fnv = int(rec['FormID'], 16)
        contents = [(self.item(fid), count, condition_of(fnv, i))
                    for i, (fid, count) in enumerate(_list(rec, 'Item', ('FormID', 'Count')))]
        contents = [c for c in contents if c[0] is not None]
        return self._write('CONT', lambda fid: R.pack_cont(
            fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds or _bounds(rec), contents,
            int(rec.get('DATA.Flags', 0)) & CONTAINER_FLAGS, float(rec.get('DATA.Weight', 0.0)),
            (self.builder.sounds.field(rec, 'SNAM.OpenSound'), self.builder.sounds.field(rec, 'QNAM.CloseSound')),
            self._vmad(rec), self.builder.destruction.of(fnv)), rec)

    def _readable(self, rec: dict) -> 'int | None':
        """A book or note: the cell builder's record of it (spike.readables)."""
        return self.builder.readable(int(rec['FormID'], 16), rec['Signature'], rec)

    def _form_list(self, rec: dict) -> 'int | None':
        """A form list of the entries the build makes (_entry; one FNV leaves empty, for scripts to fill, is made
        empty); each other entry counted by type; None, counted, when every entry is dropped."""
        listed = [int(rec[f'LNAM[{i}]'], 16) for i in range(_count(rec, 'LNAM'))]
        made = [(fid, self._entry(fid)) for fid in listed]
        for fid in (fid for fid, entry in made if entry is None):
            self.builder.counts[f'form list entry dropped ({self._type(fid)})'] += 1
        entries = [entry for _, entry in made if entry is not None]
        if listed and not entries:
            self.builder.counts['form list not made (no entry converts)'] += 1
            return None
        return self._write('FLST', lambda fid: R.pack_flst(
            fid, f'FNV_{rec.get("EditorID", rec["FormID"])}', entries), rec)

    def _entry(self, fid: int) -> 'int | None':
        """The FO4 form of FNV form list entry `fid`: an item (made now), else _built()."""
        if fid in self.records or fid in self.shared:
            return self.item(fid)
        return self._built(fid)

    def _built(self, fid: int) -> 'int | None':
        """The FO4 form the cell builder has made for FNV non-item `fid` (BUILT_MAPS, its creatures), else the
        FNV message `fid` converted (attach.ObjectScripts.message); None."""
        maps = [getattr(self.builder, name, {}) for name in BUILT_MAPS]
        maps.append(getattr(getattr(self.builder, 'creatures', None), 'made', {}))
        made = next((found[fid] for found in maps if found.get(fid)), None)
        scripts = getattr(self.builder, 'scripts', None)
        if made is not None or scripts is None:
            return made
        if self.messages is None:
            self.messages = {int(r['FormID'], 16): edid for edid, r in scripts.messages.items()}
        return scripts.message(self.messages[fid]) if fid in self.messages else None

    def _type(self, fid: int) -> str:
        """FNV form `fid`'s record type (the builder's index of the source plugin)."""
        return getattr(self.builder, 'fnv_types', {}).get(fid, 'not in the source plugin')


def _count(rec: dict, key: str) -> int:
    """How many `key`[i] an export record has."""
    i = 0
    while f'{key}[{i}]' in rec:
        i += 1
    return i
