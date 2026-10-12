"""FNV's NPCs as Fallout 4 NPCs, placed where FNV places them.

Each FNV NPC base becomes a copy of a vanilla body for its race and sex
(BODIES), with FNV's name, factions, AI packages, script, outfit (its worn
items) and inventory (the rest); a male human
also takes FNV's face fitted to FO4's sculpt regions, tints and head parts
(the fits are calibrated for male humans only). A template (TPLT) is
followed for each part its flags take from it; an NPC whose traits come
from a leveled list is not converted yet. Every actor placed in a built
cell is written in that cell, persistent as in FNV.

See: docs/fork/fo4_pipeline.md#npcs
"""

import struct
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import pack_fo4_record
from fo4_import.face import hair, sculpt, tint
from fo4_import.face.sculpt import FACE_SHAPE
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import cached
from fo4_import.spike import records as R
from fo4_import.spike.face_fit import sculpt_fit, tint_fit
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.head_parts import choose, head_parts_edit
from fo4_import.spike.placement import place, placement
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: (ghoul, female) -> the Fallout4.esm NPC a converted NPC starts from: DocWeathers, DoctorAmari, Jones, Holly.
BODIES = {(False, False): 0x12FCCB, (False, True): 0x09A680, (True, False): 0x3F239, (True, True): 0x3F23A}
#: Body subrecords a converted NPC leaves out: its factions and crime faction.
BODY_TIES = frozenset({b'SNAM', b'CRIF'})
#: FNV ACBS template flags: traits (race, face, sex, voice), factions, AI packages, inventory, script.
USE_TRAITS, USE_FACTIONS, USE_PACKAGES, USE_INVENTORY, USE_SCRIPT = 0x1, 0x4, 0x20, 0x100, 0x200
#: derive_formid site of an NPC's outfit (key: the FNV NPC's FormID).
OUTFIT_SITE = 'FNV OTFT'
#: FNV ACBS flag Female; reference record flag Persistent.
FEMALE, PERSISTENT = 0x1, 0x400
#: new_id keys of a converted NPC and its placed actor (the spike's, kept so no FormID moves).
NPC_KEY, ACHR_KEY = 'NPC_ {:08X} STH', 'ACHR {} STH'


def with_factions(snams: bytes):
    """A record edit putting faction subrecords `snams` right after ACBS, as FO4 orders them."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with the factions after ACBS."""
        out = b''
        for tag, data in subrecords(subs):
            out += pack_subrecord(tag.decode(), data) + (snams if tag == b'ACBS' else b'')
        return out
    return edit


def with_inventory(outfit: int, carried: list):
    """A record edit replacing the body's default outfit with `outfit` (0: none) and its inventory with `carried`
    [(item, count)]."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with the outfit and inventory replaced."""
        out = b''
        for tag, data in subrecords(subs):
            if tag == b'COCT' and carried:
                out += pack_subrecord('COCT', struct.pack('<I', len(carried)))
                out += b''.join(pack_subrecord('CNTO', struct.pack('<Ii', item, count)) for item, count in carried)
            elif tag == b'DOFT' and outfit:
                out += pack_subrecord('DOFT', struct.pack('<I', outfit))
            elif tag not in (b'COCT', b'CNTO', b'COED', b'DOFT'):
                out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def composed(*edits):
    """One record edit applying `edits` (None skipped) in order; None when there are none."""
    present = [e for e in edits if e is not None]

    def edit(subs: bytes) -> bytes:
        """The subrecords after every edit."""
        for step in present:
            subs = step(subs)
        return subs
    return edit if present else None


class Npcs:
    """FO4 NPCs for FNV NPC bases, each written once, and their placed actors."""

    def __init__(self, builder, export_dir: Path, form_map: dict):
        """Index FNV's NPCs and races; `form_map` maps the FNV forms packages name."""
        self.builder, self.export_dir, self.form_map = builder, export_dir, form_map
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'NPC_')}
        self.races = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'RACE')}
        self.bodies = {rec.form_id: rec for rec, _ in walk(builder.fo4, b'NPC_') if rec.form_id in BODIES.values()}
        self.assets, self.made = None, {}

    def source(self, fnv: int, flag: int) -> 'dict | None':
        """The NPC record FNV NPC `fnv` takes template part `flag` from (itself without one); None if a list."""
        rec = self.records.get(fnv)
        while rec is not None and int(rec.get('ACBS.TemplateFlags', 0)) & flag and 'TPLT.Template' in rec:
            rec = self.records.get(int(rec['TPLT.Template'], 16))
        return rec

    def base(self, fnv: int) -> 'int | None':
        """The FO4 NPC for FNV NPC `fnv`, written once (_make); None if not made."""
        if fnv not in self.made:
            self.made[fnv] = self._make(fnv)
        return self.made[fnv]

    def _make(self, fnv: int) -> 'int | None':
        """Write the FO4 NPC of FNV NPC `fnv` (class notes); its FormID."""
        npc, traits = self.records[fnv], self.source(fnv, USE_TRAITS)
        if traits is None:
            self.builder.counts['NPC_ skipped (traits from a leveled list)'] += 1
            return None
        ghoul = 'ghoul' in self.races.get(int(traits.get('RNAM.Race', '0'), 16), '').lower()
        female = bool(int(traits.get('ACBS.Flags', 0)) & FEMALE)
        body = self.bodies[BODIES[ghoul, female]]
        face = not (ghoul or female)
        morphs, edit = (self._face(traits) if face else (b'', None))
        fid = self.builder.new_id(NPC_KEY.format(fnv))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, body.body, body.flags, f'FNV_{npc["EditorID"]}', npc.get('FULL', ''),
            (FACE_SHAPE if face else frozenset()) | BODY_TIES, morphs,
            composed(edit, with_factions(self._factions(fnv)), self._packages(fnv), self._inventory(fnv))))
        self.builder.counts['NPC_'] += 1
        self.builder.npc_ids[fnv] = fid
        return fid

    def _factions(self, fnv: int) -> bytes:
        """FO4 SNAMs of the factions FNV NPC `fnv` (or its template) is in, through the converted factions."""
        rec = self.source(fnv, USE_FACTIONS) or {}
        out = b''
        for i in range(int(rec.get('FactionCount', 0))):
            faction = self.builder.factions.get(int(rec[f'Faction[{i}].FormID'], 16))
            if faction:
                out += pack_subrecord('SNAM', struct.pack('<Ib3x', faction, int(rec[f'Faction[{i}].Rank'])))
        return out

    def _inventory(self, fnv: int):
        """The edit giving FNV NPC `fnv` (or its template) its worn items as an outfit, the rest as inventory."""
        rec, items = self.source(fnv, USE_INVENTORY) or {}, self.builder.items
        worn, carried = [], []
        for i in range(int(rec.get('ItemCount', 0))):
            item = int(rec[f'Item[{i}].FormID'], 16)
            made = items.item(item)
            if made is not None and items.wearable(item):
                worn.append(made)
            elif made is not None:
                carried.append((made, int(rec[f'Item[{i}].Count'])))
        return with_inventory(self._outfit(fnv, worn), carried)

    def _outfit(self, fnv: int, worn: list) -> int:
        """An outfit of `worn` for FNV NPC `fnv`, written; 0 when it wears nothing."""
        if not worn:
            return 0
        fid = self.builder.writer.derive_formid(OUTFIT_SITE, fnv)
        body = pack_subrecord('EDID', f'FNV_{self.records[fnv]["EditorID"]}Outfit\0'.encode('cp1252'))
        body += pack_subrecord('INAM', b''.join(struct.pack('<I', f) for f in sorted(set(worn))))
        self.builder.writer.add_record('OTFT', pack_fo4_record('OTFT', fid, 0, body))
        self.builder.counts['OTFT'] += 1
        return fid

    def _packages(self, fnv: int):
        """The edit giving FNV NPC `fnv` its (or its template's) AI packages."""
        rec = self.source(fnv, USE_PACKAGES) or {}
        return R.packages_edit(self.builder.packages.for_npc(rec, self.form_map))

    def _face(self, npc: dict) -> tuple:
        """(sculpt morphs, edit giving tints and head parts) of male FNV NPC `npc`'s fitted face."""
        inputs = tuple(npc.get(k, '') for k in ('FGGS', 'FGGA', 'FGTS', 'RNAM.Race', 'HNAM.Hair', 'ENAM.Eyes',
                                                'HCLR.R', 'HCLR.G', 'HCLR.B', 'LNAM.HairLength'))
        bases = tuple(p.read_bytes() for p in (sculpt.basis_path(), tint.basis_path()) if p.exists())
        if len(bases) < 2:
            self.builder.counts['face fit skipped (no calibration)'] += 1
            return b'', None
        edid, key = npc['EditorID'], inputs + bases
        sculpted = cached('sculpt_fit', 'fo4_import.spike.face_fit', key, lambda: sculpt_fit(self.export_dir, edid))
        tinted = cached('tint_fit', 'fo4_import.spike.face_fit', key, lambda: tint_fit(self.export_dir, edid))
        self.assets = self.assets or hair.Fo4Assets(self.builder.fo4, Archives(FALLOUT4_DIR / 'Data'))
        chosen = cached('head_parts', 'fo4_import.spike.head_parts', key,
                        lambda: choose(self.export_dir, edid, self.assets, sculpt.load_basis()[2]))
        self.builder.counts['face fitted'] += 1
        return (sculpted or (b'',))[0], composed(_tint_edit(tinted), head_parts_edit(chosen, self.assets))

    def placed(self, refs: list, cell_of, ids: dict, owners: dict) -> dict:
        """{FNV cell: (persistent, temporary) ACHRs} of the actors `refs` placed in built cells (`cell_of(ref)`, None
        outside them); enable parents and linked references through `ids` {FNV hex: FO4}, owners through `owners`."""
        out = {}
        for ref in sorted(refs, key=lambda r: r['FormID']):
            cell = cell_of(ref)
            base = self.base(int(ref['NAME'], 16)) if cell and int(ref['NAME'], 16) in self.records else None
            if base is not None:
                slot = out.setdefault(cell, [b'', b''])
                slot[0 if int(ref['RecordFlags']) & PERSISTENT else 1] += self._actor(ref, base, ids, owners)
        return {cell: tuple(slot) for cell, slot in out.items()}

    def _actor(self, ref: dict, base: int, ids: dict, owners: dict) -> bytes:
        """The FO4 ACHR of FNV actor `ref` on `base`, with its script, parents and linked reference."""
        fnv = int(ref['NAME'], 16)
        achr = self.builder.new_id(ACHR_KEY.format(ref['FormID']))
        self.builder.actor_ids[ref['FormID']] = achr
        self.builder.scripts.named[ref.get('EditorID', '')] = achr
        script = self.source(fnv, USE_SCRIPT) or {}
        vmad = self.builder.scripts.vmad(int(script['SCRI'], 16)) if 'SCRI' in script else b''
        linked = ids.get(ref.get('XLKR.LinkedRef'), 0)
        extra = placement(int(ref['FormID'], 16), ids, owners)
        extra += pack_subrecord('XLKR', struct.pack('<II', 0, linked)) if linked else b''
        self.builder.counts['ACHR'] += 1
        return R.pack_achr(achr, base, *place(ref), vmad, extra, bool(int(ref['RecordFlags']) & PERSISTENT))


def _tint_edit(fitted):
    """A record edit giving fitted tint layers and skin tone (tint_fit's result); None without a fit."""
    if fitted is None:
        return None
    values, tone, _ = fitted
    basis, options = tint.load_basis(), skin_tone_layers()

    def edit(subs: bytes) -> bytes:
        """The record with the fitted tint layers and its skin tone scaled."""
        rest, kept = tint.without_tints(subs, options)
        rest = tint.with_tints(rest, tint.pack_layers(basis[1], values, kept, basis[3]))
        return tint.with_tone(rest, tone, options)
    return edit
