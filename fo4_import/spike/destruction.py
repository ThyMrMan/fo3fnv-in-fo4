"""FNV destructible objects' destruction data (DEST) as FO4's: health, stages, their explosions, debris and models.

FNV and FO4 write the same layout (xEdit wbDEST): a DEST header, then per stage a DSTD, an optional model
(DMDL, DMDT) and a DSTF end marker. FO4's extras (DAMC, DSTA, DMDC, DMDS) are optional and left out, and so is
DMDT (FO4's lists the model's textures by hash). The export holds none of it, so it is read from the source plugin.
A stage's explosion is a copy of its Fallout4.esm stand-in (the same EditorID, else STAND_INS) with FNV's numbers
(ProjectileCopies.explosion); its debris is Fallout4.esm's of the same EditorID, else none; its model is
converted (CellBuilder.mesh).

See: docs/fork/fo4_pipeline.md#damage-stages
"""

import struct

from fo4_import.base.install import source_walk
from fo4_import.pipeline.export_index import export_file, export_records
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV base types that carry destruction data and convert to an FO4 type that keeps it (MSTT, ACTI, CONT).
TYPES = (b'MSTT', b'ACTI', b'CONT')
#: Subrecords of the destruction block, in order; the ones FO4 shares with FNV are written.
DEST_TAGS = frozenset((b'DEST', b'DSTD', b'DMDL', b'DMDT', b'DSTF'))
WRITTEN = (b'DEST', b'DSTD', b'DMDL', b'DSTF')
#: DSTD: health %, index, model damage stage, flags, self damage per second, explosion, debris, debris count.
STAGE = struct.Struct('<4BiIIi')
#: FNV explosion EditorID -> the Fallout4.esm explosion standing in (none of these has a namesake).
STAND_INS = {
    'SmallNukeExplosion': 'CarNukeLargeVehicles', 'MediumExplosion': 'CarExplosion',
    'LargeExplosion': 'CarExplosion', 'MotorcycleExplosion': 'CarNukeSmallVehicles',
    'VMS08MonorailExplosion': 'CarNukeLargeVehicles', 'FFE08Explosion': 'CarNukeLargeVehicles',
    'NellisMunitionsExplosion': 'CarExplosion', 'VertibirdExplosion': 'VertibirdDeathExplosion',
    'GrenadeFragExplosion': 'fragGrenadeExplosion', 'AmmoBoxExplosion': 'fragGrenadeExplosion',
    'MineFragExplosion': 'fragMineExplosion', 'GrenadePlasmaExplosion': 'plasmaGrenadeExplosion',
    'ElectricBoxExplosion': 'ElectricalExplosionSmall', 'ElectricBoxExplosionSecurtronVault': 'ElectricalExplosionSmall',
    'vHDGeneratorExplosion': 'ElectricalExplosionSmall', 'HVRadioExplosion': 'ElectricalExplosionSmall',
    'GasTrapFireBurst': 'ExplosionTrapGas', 'V22GasTrapFireBurst': 'ExplosionTrapGas',
    'ExplosionFlamerCritEffect': 'ExplosionTrapGas', 'BloatFlyExplosion': 'GoreInsectSmallExplosion',
}


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


class Destruction:
    """The FO4 destruction subrecords of one build's FNV bases, their explosions and models made through its
    builder."""

    def __init__(self, builder):
        """Read the source's destruction blocks, Fallout4.esm's explosions and debris."""
        self.builder, self.blocks = builder, destruction_blocks(source_walk(*TYPES))
        self.explosions, self.debris = fo4_names(builder.fo4, b'EXPL'), fo4_names(builder.fo4, b'DEBR')
        self.debris_names = {}

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
        debris = self._debris(debris)
        return STAGE.pack(*head, self._explosion(explosion), debris, count if debris else 0)

    def _explosion(self, fnv: int) -> int:
        """The FO4 explosion for FNV explosion `fnv`: a copy of its stand-in with FNV's numbers; 0 for none."""
        copies = self.builder.projectiles.copies
        name = copies.explosions.get(fnv, {}).get('EditorID', '')
        stand_in = self.explosions.get(name) or self.explosions.get(STAND_INS.get(name, ''))
        if fnv and not stand_in:
            self.builder.counts[f'destruction explosion left out ({name or f"{fnv:08X}"})'] += 1
        return copies.explosion(stand_in, fnv) if stand_in else 0

    def _debris(self, fnv: int) -> int:
        """Fallout4.esm's debris of FNV debris `fnv`'s EditorID; 0 for none (counted)."""
        if not fnv:
            return 0
        if not self.debris_names:
            self.debris_names = {int(r['FormID'], 16): r['EditorID']
                                 for r in export_records(self.builder.export_dir, 'DEBR')}
        name = self.debris_names.get(fnv, f'{fnv:08X}')
        if name not in self.debris:
            self.builder.counts[f'destruction debris left out ({name})'] += 1
        return self.debris.get(name, 0)

    def _model(self, model: str) -> 'bytes | None':
        """A stage's FNV `model` converted, as its DMDL; None (the stage keeps its look) when no export holds it."""
        if not export_file(self.builder.export_dir, 'meshes', model.replace('/', chr(92)).lower()).is_file():
            self.builder.counts['destruction stage model left out (in no archive)'] += 1
            return None
        return f'{self.builder.mesh(model)[0]}\0'.encode('cp1252')
