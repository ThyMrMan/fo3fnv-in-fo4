"""FNV placeable water (PWAT) as Fallout 4's: Fallout4.esm's own water tiles, typed by FNV's water.

FO4 places water as an activator with a water type (ACTI WNAM) on a generic
tile its reference scales: Water\\Water1024.nif (a 1024-unit square with
BSWaterShaderProperty and a convex volume on collision layer 11, water) or
WaterCircle1024.nif, 37 of Fallout4.esm's 45. A PWAT becomes such an
activator, and its reference becomes tiles (scol parts) covering its mesh:
squares of the shorter side in a row along the longer one; a mesh filling
under 90% of its extent is round and takes the circle. Its water type is a
copy of the Fallout4.esm placeable water type nearest in shallow and deep
color, drinking (XNAM) and contact (YNAM) spells as FNV's water: clean, or
irradiated when its drinking effect damages radiation (activators). FNV's
WATR colors (DNAM) and drinking spell (XNAM) are read from FalloutNV.esm.

See: docs/fork/fo4_pipeline.md#placeable-water
"""

import math
import struct
from pathlib import Path

import numpy as np
from pyffi.formats.nif import NifFormat

from fo4_import.base.install import source_esm
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.activators import irradiating
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Fallout4.esm's placeable water tiles, their side in game units.
SQUARE, ROUND, TILE = 'Water\\Water1024.nif', 'Water\\WaterCircle1024.nif', 1024.0
#: A mesh filling less of its extent than this is round (a circle fills pi / 4).
ROUND_FILL = 0.9
#: Byte offsets of the shallow and deep colors in a WATR's DNAM: FNV's, FO4's.
FNV_COLORS, FO4_COLORS = 40, 4
#: FO4 spells (drinking, contact) of clean and irradiated water.
CLEAN = ('WaterFountainCleanDrinking', None)
IRRADIATED = ('WaterRadiationDrinking', 'WaterRadiationHazard')
#: ledger site of a water type copy (key: the FNV WATR).
WATER_SITE = 'FNV placeable water type'


def _edid(body: bytes) -> str:
    """A record body's EditorID ('' without one)."""
    return (first_sub(body, b'EDID') or b'').rstrip(b'\0').decode('cp1252')


def _colors(dnam: bytes, at: int) -> np.ndarray:
    """The shallow and deep RGB colors at `at` in a WATR DNAM."""
    return np.array(list(dnam[at:at + 3]) + list(dnam[at + 4:at + 7]), dtype=float)


def mesh_shape(path: Path) -> tuple:
    """((x, y) centre, (width, length) along x and y, round) of the FNV water mesh at `path`, from its triangles."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    points, area = [], 0.0
    for block in data.blocks:
        if isinstance(block, (NifFormat.NiTriStripsData, NifFormat.NiTriShapeData)):
            verts = np.array([(v.x, v.y) for v in block.vertices])
            points.append(verts)
            for a, b, c in block.get_triangles():
                (x1, y1), (x2, y2) = verts[b] - verts[a], verts[c] - verts[a]
                area += abs(x1 * y2 - x2 * y1) / 2
    every = np.concatenate(points)
    low, high = every.min(axis=0), every.max(axis=0)
    size = high - low
    return tuple((low + high) / 2), tuple(size), area < ROUND_FILL * size[0] * size[1]


def tiles(center: tuple, size: tuple, round_: bool) -> list:
    """[(x, y, z, rx, ry, rz, scale)] of the TILE-sided tiles covering a mesh: one for a round one, else squares
    of the shorter side spaced evenly along the longer."""
    short, long_ = sorted(size)
    count = 1 if round_ else max(1, math.ceil(long_ / short - 1e-6))
    step = (long_ - short) / (count - 1) if count > 1 else 0.0
    along = 1 if size[1] >= size[0] else 0
    out = []
    for i in range(count):
        at = list(center)
        at[along] += -(long_ - short) / 2 + i * step
        out.append((at[0], at[1], 0.0, 0.0, 0.0, 0.0, short / TILE))
    return out


class PlaceableWater:
    """FO4 water activators and tiles for FNV PWATs, written through a cell builder."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV's waters and Fallout4.esm's placeable water types, tile activators and spells."""
        self.builder, self.meshes = builder, export_dir / 'meshes'
        self.spells = {int(r['FormID'], 16): r for r in export_records(export_dir, 'SPEL')}
        self.fnv = {r.form_id: dict(subrecords(r.body)) for r, _ in walk(source_esm(), b'WATR')}
        actis = [r for r, _ in walk(builder.fo4, b'ACTI') if first_sub(r.body, b'WNAM')]
        placed = {struct.unpack('<I', first_sub(r.body, b'WNAM'))[0] for r in actis}
        self.fo4 = {r.form_id: r.body for r, _ in walk(builder.fo4, b'WATR')
                    if r.form_id in placed and first_sub(r.body, b'XNAM')}
        self.templates = {(first_sub(r.body, b'MODL') or b'').rstrip(b'\0').decode(): r.body for r in actis}
        self.fo4_spells = {_edid(r.body): r.form_id for r, _ in walk(builder.fo4, b'SPEL')}
        self.types, self.shapes = {}, {}

    def shape(self, rec: dict) -> tuple:
        """mesh_shape() of FNV PWAT `rec`'s mesh, read once."""
        model = rec['Model.MODL'].replace('\\', '/').lower()
        if model not in self.shapes:
            self.shapes[model] = mesh_shape(self.meshes / model)
        return self.shapes[model]

    def parts(self, fnv_fid: int, rec: dict) -> list:
        """FNV PWAT `rec`'s tiles as scol parts [(its FormID, placement)]."""
        return [(fnv_fid, tile) for tile in tiles(*self.shape(rec))]

    def record(self, fid: int, rec: dict) -> int:
        """Write FNV PWAT `rec` as an ACTI on `fid`: the round or square tile's vanilla activator, FNV's EditorID
        and its water type (water_type); `fid`."""
        mesh = ROUND if self.shape(rec)[2] else SQUARE
        subs = []
        for tag, data in subrecords(self.templates[mesh]):
            if tag == b'EDID':
                data = f'FNV_{rec["EditorID"]}'.encode('cp1252') + b'\0'
            elif tag == b'WNAM':
                data = struct.pack('<I', self.water_type(int(rec['DNAM.Water'], 16)))
            subs.append(pack_subrecord(tag.decode(), data))
        self.builder.writer.add_record('ACTI', pack_fo4_record('ACTI', fid, 0, b''.join(subs)))
        self.builder.counts['placeable water'] += 1
        return fid

    def water_type(self, fnv_water: int) -> int:
        """The FO4 WATR made once for FNV WATR `fnv_water`: the nearest-colored placeable type, FNV's spells."""
        if fnv_water in self.types:
            return self.types[fnv_water]
        fnv = self.fnv[fnv_water]
        colors = _colors(fnv[b'DNAM'], FNV_COLORS)
        nearest = min(self.fo4, key=lambda w: np.abs(_colors(first_sub(self.fo4[w], b'DNAM'), FO4_COLORS)
                                                    - colors).sum())
        spell = struct.unpack('<I', fnv[b'XNAM'])[0] if b'XNAM' in fnv else 0
        drink, contact = IRRADIATED if irradiating(self.spells.get(spell, {})) else CLEAN
        spells = (self.fo4_spells[drink], self.fo4_spells[contact] if contact else 0)
        fid = self.builder.writer.derive_formid(WATER_SITE, f'{fnv_water:08X}')
        edid = 'FNV_' + fnv[b'EDID'].rstrip(b'\0').decode('cp1252')
        self.builder.writer.add_record('WATR', pack_fo4_record('WATR', fid, 0, retyped(self.fo4[nearest], edid, spells)))
        self.types[fnv_water] = fid
        return fid


def retyped(body: bytes, edid: str, spells: tuple) -> bytes:
    """WATR `body`'s subrecords as `edid`, its drinking spell (XNAM) and contact spell (YNAM; 0: none) `spells`."""
    out = b''
    for tag, data in subrecords(body):
        if tag == b'EDID':
            out += pack_string_subrecord('EDID', edid)
        elif tag == b'XNAM':
            out += pack_subrecord('XNAM', struct.pack('<I', spells[0]))
            out += pack_subrecord('YNAM', struct.pack('<I', spells[1])) if spells[1] else b''
        elif tag != b'YNAM':
            out += pack_subrecord(tag.decode(), data)
    return out
