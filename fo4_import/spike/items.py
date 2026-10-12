"""FNV items, leveled items and containers as FO4 records, for the cell spike.

A misc item keeps its name, model, value and weight; a leveled item its
chance none, flags and the entries whose items convert; a container its
model, flags, weight and the contents that convert; a text note becomes a
paper note (BOOK). FNV's engine objects (FormID below ENGINE_IDS) that
Fallout4.esm has under the same FormID, type and EditorID are FO4's own
(the bottle cap, COC and X markers), and an item the replacement table
names as an `item` is that record itself (spike.replacements). Consumables and
ammunition are made by consumables.Consumables, weapons and armor by
equipment.Equipment; any other type is skipped and counted.

See: docs/fork/fo4_spikes.md#spike-2-items
"""

from pathlib import Path

from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import first_sub, walk
from fo4_import.pipeline.export_index import export_records

#: FNV's engine objects sit below this FormID.
ENGINE_IDS = 0x800
#: The portal marker: built into FNV's engine (FalloutNV.esm has no record), Fallout4.esm's PortalMarker STAT.
PORTAL_MARKER = 0x20
#: FNV record types an inventory may name, indexed for conversion (the rest are skipped).
ITEM_TYPES = ('MISC', 'LVLI', 'ALCH', 'WEAP', 'ARMO', 'AMMO', 'BOOK', 'KEYM', 'NOTE', 'CONT')
#: FO4 container DATA flags kept from FNV (same bit): Respawns.
CONTAINER_FLAGS = 0x2
#: FNV NOTE DATA type of a text note (0 sound, 2 image, 3 voice).
TEXT_NOTE = 1


def _edid(rec) -> str:
    """A plugin record's EditorID."""
    return (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')


def shared_engine_ids(fo4_esm: bytes, fnv: dict, types: tuple) -> dict:
    """{FNV FormID: FO4 FormID} of FNV engine objects Fallout4.esm has with the same FormID, type and EditorID,
    and the portal marker (PORTAL_MARKER).

    `fnv` is {FormID: (type, export record)}.
    """
    out = {PORTAL_MARKER: PORTAL_MARKER}
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
        named = {rec.get('EditorID'): fid for fid, (_, rec) in records.items()}
        self.names = {name.lower(): fid for name, fid in named.items() if name}
        self.shared = {**shared, **{named[e]: fid for e, fid in (stand_ins or {}).items() if e in named}}

    def by_name(self, edid: str) -> 'int | None':
        """item() of the FNV record named `edid` (any case), or None."""
        fid = self.names.get(edid.lower())
        return self.item(fid) if fid is not None else None

    def item(self, fnv_fid: int) -> 'int | None':
        """The FO4 record for an FNV item, leveled item or container; None when its type is not converted."""
        if fnv_fid in self.shared:
            return self.shared[fnv_fid]
        if fnv_fid not in self.made:
            self.made[fnv_fid] = None
            self.made[fnv_fid] = self._make(*self.records.get(fnv_fid, (None, None)))
        return self.made[fnv_fid]

    def _make(self, sig: str, rec: dict) -> 'int | None':
        """Write the FO4 record of a convertible FNV record; its FormID, or None (counted as skipped)."""
        maker = {'MISC': self._misc, 'KEYM': self._key, 'LVLI': self._leveled, 'CONT': self._container,
                 'NOTE': self._note}.get(sig)
        if sig in self.makers:
            made = self.makers[sig](int(rec['FormID'], 16), rec)
            if made is None:
                self.builder.counts[f'item skipped ({sig})'] += 1
            return made
        if maker is None:
            self.builder.counts[f'item skipped ({sig or "not exported"})'] += 1
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
        """A misc item (or a record of `sig` packed alike by `pack`)."""
        if 'Model.MODL' not in rec:
            return None
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        return self._write(sig, lambda fid: pack(
            fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds or _bounds(rec), int(rec.get('DATA.Value', 0)),
            float(rec.get('DATA.Weight', 0.0)), self._vmad(rec)), rec)

    def _vmad(self, rec: dict) -> bytes:
        """The VMAD attaching FNV item `rec`'s converted script; b'' without one."""
        return self.builder.scripts.vmad(int(rec['SCRI'], 16)) if 'SCRI' in rec else b''

    def _leveled(self, rec: dict) -> 'int | None':
        """A leveled item with the entries whose items convert; None when none do."""
        listed = _list(rec, 'Entry', ('Level', 'FormID', 'Count'))
        entries = [(level, self.item(fid), count) for level, fid, count in listed]
        entries = [e for e in entries if e[1] is not None]
        if not entries:
            return None
        return self._write('LVLI', lambda fid: R.pack_lvli(
            fid, f'FNV_{rec["EditorID"]}', int(rec.get('LVLD.ChanceNone', 0)), int(rec.get('LVLF.Flags', 0)),
            entries), rec)

    def _container(self, rec: dict) -> 'int | None':
        """A container with the contents that convert."""
        if 'Model.MODL' not in rec:
            return None
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        contents = [(self.item(fid), count) for fid, count in _list(rec, 'Item', ('FormID', 'Count'))]
        contents = [c for c in contents if c[0] is not None]
        return self._write('CONT', lambda fid: R.pack_cont(
            fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds or _bounds(rec), contents,
            int(rec.get('DATA.Flags', 0)) & CONTAINER_FLAGS, float(rec.get('DATA.Weight', 0.0)),
            (self.builder.sounds.field(rec, 'SNAM.OpenSound'), self.builder.sounds.field(rec, 'QNAM.CloseSound')),
            self._vmad(rec)), rec)

    def _note(self, rec: dict) -> 'int | None':
        """A text note as a paper note; None for sound, image and voice notes."""
        if int(rec.get('DATA.Type', -1)) != TEXT_NOTE:
            return None
        text = rec.get('TNAM.Text', '').replace(chr(13) + chr(10), chr(10))
        return self._write('BOOK', lambda fid: R.pack_book(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), text), rec)
