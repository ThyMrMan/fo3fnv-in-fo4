"""FNV destructible objects' destruction data (DEST) as FO4's: health, stages, their explosions, debris and models.

FNV and FO4 write the same layout (xEdit wbDEST): a DEST header, then per stage a DSTD, an optional model
(DMDL, DMDT) and a DSTF end marker. FO4's extras (DAMC, DSTA, DMDC, DMDS) are optional and left out, and so is
DMDT (FO4's lists the model's textures by hash). The export holds none of it, so it is read from the source plugin.
A stage's explosion is a copy of its Fallout4.esm stand-in (explosion_routes) with FNV's numbers
(ProjectileCopies.explosion); its debris is Fallout4.esm's of the same EditorID, else FNV's own converted (the
same DEBR layout, xEdit wbDebrisModel); its model is converted (CellBuilder.mesh).

See: docs/fork/fo4_pipeline.md#damage-stages
"""

import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike.explosion_routes import ExplosionRoutes, effect_kinds
from tes5_import.base.tes5_reader import first_sub, subrecords, walk, zstr
from tes5_import.base.writer import pack_subrecord

#: FNV base types that carry destruction data and convert to an FO4 type that keeps it (MSTT, ACTI, CONT).
TYPES = (b'MSTT', b'ACTI', b'CONT')
#: Subrecords of the destruction block, in order; the ones FO4 shares with FNV are written.
DEST_TAGS = frozenset((b'DEST', b'DSTD', b'DMDL', b'DMDT', b'DSTF'))
WRITTEN = (b'DEST', b'DSTD', b'DMDL', b'DSTF')
#: DSTD: health %, index, model damage stage, flags, self damage per second, explosion, debris, debris count.
STAGE = struct.Struct('<4BiIIi')
#: derive_formid site of an FNV debris converted (key: FNV FormID).
DEBRIS_SITE = 'FNV DEBR copy'


def fo4_names(fo4: bytes, sig: bytes) -> dict:
    """{EditorID: FormID} of Fallout4.esm's `sig` records."""
    return {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252'): r.form_id for r, _ in walk(fo4, sig)}


def destruction_blocks(records) -> dict:
    """{FormID: [(tag, data)] of its destruction block} of plugin `records` ((rec, stack) pairs) that have one."""
    out = {}
    for rec, _ in records:
        subs = subrecords(rec.body)
        block = [(tag, data) for tag, data in subs if tag in DEST_TAGS]
        if block and block[0][0] == b'DEST':
            out[rec.form_id] = block
    return out


def debris_models(body: bytes) -> list:
    """[(percentage, model, has collision)] of a DEBR record `body`, in order."""
    out = []
    for tag, data in subrecords(body):
        if tag == b'DATA':
            model = zstr(data[1:])
            out.append((data[0], model, data[len(model) + 2] if len(data) > len(model) + 2 else 0))
    return out


class Destruction:
    """The FO4 destruction subrecords of one build's FNV bases, their explosions and models made through its
    builder."""

    def __init__(self, builder):
        """Read the source's destruction blocks, Fallout4.esm's explosions and debris."""
        self.builder, self.blocks = builder, destruction_blocks(source_walk(*TYPES))
        self.explosions, self.debris = fo4_names(builder.fo4, b'EXPL'), fo4_names(builder.fo4, b'DEBR')
        self.routes, self.stand_ins, self.fnv_debris, self.made_debris = None, {}, None, {}

    def of(self, fnv: int) -> bytes:
        """FNV base `fnv`'s destruction data as FO4 subrecords (WRITTEN); b'' without any."""
        out = b''
        for tag, data in self.blocks.get(fnv, ()):
            if tag == b'DSTD':
                data = self._stage(data)
            elif tag == b'DMDL':
                data = self._model(data.rstrip(b'\0').decode('cp1252'))
            if tag in WRITTEN and data is not None:
                out += pack_subrecord(tag.decode(), data)
        return out

    def _stage(self, data: bytes) -> bytes:
        """FNV DSTD `data` with FO4's explosion and debris (unmapped: none, count 0)."""
        *head, explosion, debris, count = STAGE.unpack(data)
        debris = self.debris_of(debris)
        return STAGE.pack(*head, self.explosion(explosion), debris, count if debris else 0)

    def explosion(self, fnv: int) -> int:
        """The FO4 explosion for FNV explosion `fnv`: a copy of its routed stand-in with FNV's numbers; 0 for none.
        Each explosion's route is counted once."""
        copies = self.builder.projectiles.copies
        if fnv not in self.stand_ins:
            self.stand_ins[fnv] = self._route(copies.explosions.get(fnv, {}), fnv) if fnv else None
        stand_in = self.stand_ins[fnv]
        return copies.explosion(stand_in, fnv) if stand_in else 0

    def _route(self, rec: dict, fnv: int) -> 'int | None':
        """Fallout4.esm's stand-in for FNV EXPL `rec` (ExplosionRoutes.route), counted; None."""
        if self.routes is None:
            copies = self.builder.projectiles.copies
            self.routes = ExplosionRoutes(self.explosions, copies.explosions, lambda: effect_kinds(
                copies.enchantments, export_records(self.builder.export_dir, 'MGEF')))
        found = self.routes.route(rec) if rec else None
        name = rec.get('EditorID') or f'{fnv:08X}'
        if not found:
            self.builder.counts[f'destruction explosion left out ({name})'] += 1
            return None
        self.builder.counts[f'destruction explosion route ({found[0]})'] += 1
        return self.explosions[found[1]]

    def debris_of(self, fnv: int) -> int:
        """Fallout4.esm's debris of FNV debris `fnv`'s EditorID, else FNV's converted (_own_debris); 0 for none."""
        if not fnv:
            return 0
        if self.fnv_debris is None:
            self.fnv_debris = {r.form_id: r for r, _ in source_walk(b'DEBR')}
        if fnv not in self.made_debris:
            rec = self.fnv_debris.get(fnv)
            name = zstr(first_sub(rec.body, b'EDID') or b'') if rec else f'{fnv:08X}'
            self.made_debris[fnv] = self.debris.get(name) or (self._own_debris(rec, name) if rec else 0)
            if not self.made_debris[fnv]:
                self.builder.counts[f'destruction debris left out ({name})'] += 1
        return self.made_debris[fnv]

    def _own_debris(self, rec, name: str) -> int:
        """FNV DEBR `rec` written as FO4's, each model an export holds converted (MODT dropped); 0 with none."""
        data = b''
        for percent, model, collision in debris_models(rec.body):
            if self._in_export(model):
                data += pack_subrecord('DATA', bytes((percent,)) + self._model(model) + bytes((collision,)))
        if not data:
            return 0
        fid = self.builder.writer.derive_formid(DEBRIS_SITE, rec.form_id)
        body = pack_subrecord('EDID', f'FNV_{name}\0'.encode('cp1252')) + data
        self.builder.writer.add_record('DEBR', pack_fo4_record('DEBR', fid, 0, body))
        self.builder.counts['DEBR (converted)'] += 1
        return fid

    def _in_export(self, model: str) -> bool:
        """Whether an export holds FNV `model`."""
        return export_file(self.builder.export_dir, 'meshes', model.replace('/', chr(92)).lower()).is_file()

    def _model(self, model: str) -> 'bytes | None':
        """A stage's FNV `model` converted, as its DMDL; None (the stage keeps its look) when no export holds it."""
        if not self._in_export(model):
            self.builder.counts['destruction stage model left out (in no archive)'] += 1
            return None
        return f'{self.builder.mesh(model)[0]}\0'.encode('cp1252')
