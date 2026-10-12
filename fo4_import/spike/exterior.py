"""A rectangle of an FNV worldspace's cells as an FO4 worldspace, for the cell spike.

The cells keep their land (heights, normals,
colors, and every texture as blended shares: land_layers.py) and
references; the
persistent references standing in the block (doors) go in the worldspace's
persistent cell. The worldspace takes the Commonwealth's climate, water and
map settings. Landscape textures become LTEX records with FO4 texture sets:
FNV's diffuse and normal map, and a specular map from the normal map's
alpha, and the grasses FNV grows on them (grass.py). A cell's navmeshes
(navmesh.py) go in its temporary group, pathing cell (world, grid). LOD is
not converted.
Records keep FNV's FormIDs; a texture set's is hashed from its LTEX.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import math
import shutil
import struct
from pathlib import Path

import numpy as np

from asset_convert.texture.landscape_normals import SPECULAR_ALPHA
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.grass import Grasses
from fo4_import.spike.land_layers import blend_borders, limit_textures, quadrant_mix
from fo4_import.spike.navmesh import grid_parent
from fo4_import.spike.weathers import climate
from fo4_import.nif.convert_static import fo4_texture, smoothness, spec_image
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import normal_map
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_group, pack_subrecord

CELL_UNITS = 4096.0
#: Fallout4.esm's Commonwealth, whose climate, water and map settings the worldspace takes.
WORLD_TEMPLATE = 0x3C
WORLD_COPIED = (b'CNAM', b'NAM2', b'NAM3', b'NAM4', b'DNAM', b'MNAM', b'ONAM', b'NAMA', b'DATA', b'XWEM')
#: Smallest share written: a texture or vertex below it is left out.
MIN_SHARE = 1e-4
#: BTXT layer of a base texture: vanilla's -1 (every one of the 2,000+ sampled), never an alpha layer's index.
BASE_LAYER = -1
#: FNV's default land texture (FalloutNV.exe sDefaultLandDiffuseTexture), drawn for texture 0 and a missing base.
DEFAULT_LAND_TEXTURE = 'dirtwasteland01.dds'
#: Material type of vanilla landscape textures (FO4 MATT), and the CELL DATA flag Has Water vanilla sets.
LAND_MATERIAL, CELL_DATA = 0x12F35, 0x02
#: Record flags of a persistent cell, and the persistent flag of a reference.
PERSISTENT = 0x400
#: Exterior group types: world children, cell block, sub-block, cell children, persistent, temporary.
WORLD_CHILDREN, BLOCK, SUB_BLOCK, CELL_CHILDREN, PERSISTENT_CHILDREN, TEMPORARY_CHILDREN = 1, 4, 5, 6, 8, 9


class Exterior:
    """The FNV cells, land and references of one rectangle of cells; `refs` lists every reference placed."""

    def __init__(self, export_dir: Path, all_refs: list, world: str, lo: tuple, hi: tuple):
        """The cells of FNV worldspace `world` from grid `lo` to `hi` (x, y; both included)."""
        self.export_dir = export_dir
        self.world = next(r for r in export_records(export_dir, 'WRLD') if r.get('EditorID') == world)
        cells = [r for r in export_records(export_dir, 'CELL')
                 if r.get('ParentWRLD') == self.world['FormID']]
        self.persistent_cell = next(r['FormID'] for r in cells if int(r['RecordFlags']) & PERSISTENT)
        self.cells = {(int(r['XCLC.X']), int(r['XCLC.Y'])): r for r in cells if 'XCLC.X' in r and not
                      int(r['RecordFlags']) & PERSISTENT and lo[0] <= int(r['XCLC.X']) <= hi[0]
                      and lo[1] <= int(r['XCLC.Y']) <= hi[1]}
        own = {r['FormID']: grid for grid, r in self.cells.items()}
        self.by_cell = {grid: [] for grid in self.cells}
        self.persistent = []
        for ref in all_refs:
            if ref.get('ParentCELL') in own:
                self.by_cell[own[ref['ParentCELL']]].append(ref)
            elif ref.get('ParentCELL') == self.persistent_cell and _grid(ref) in self.cells:
                self.persistent.append(ref)
        self.refs = self.persistent + [r for refs in self.by_cell.values() for r in refs]
        self.land = {r['ParentCELL']: r for r in export_records(export_dir, 'LAND') if r['ParentCELL'] in own}
        self.textures, self.made = {}, {}
        self.grasses = Grasses(export_dir)

    def placement_order(self) -> list:
        """Every reference in group()'s order: the persistent cell's, then each cell's."""
        return self.persistent + [r for grid in sorted(self.cells) for r in self.by_cell[grid]]

    def pathing(self, builder) -> dict:
        """{FNV cell: (FO4 worldspace, grid)}: each grid cell's navmesh pathing cell."""
        world = builder.fnv_id(self.world['FormID'])
        return {r['FormID']: (world, grid_parent(*grid)) for grid, r in self.cells.items()}

    def group(self, builder, place, data_dir: Path, navmesh: dict) -> bytes:
        """The WRLD group's body: worldspace, persistent cell, grid cells; `place(refs)` packs (persistent, temporary).

        `navmesh` holds each FNV cell's NAVM records. Records made here (LTEX, TXST) are added to `builder.writer`.
        """
        world, persistent_cell = builder.fnv_id(self.world['FormID']), builder.fnv_id(self.persistent_cell)
        cells, kept = {}, place(self.persistent)[0]
        lands = {grid: self.land.get(self.cells[grid]['FormID']) for grid in sorted(self.cells)}
        mixes = limit_textures(blend_borders({grid: quadrant_mix(land) for grid, land in lands.items() if land}))
        for grid in sorted(self.cells):
            persistent, temporary = place(self.by_cell[grid])
            kept += persistent
            land = lands[grid]
            land_record = self._land(builder, land, mixes.get(grid), data_dir) if land else b''
            navm = navmesh.get(self.cells[grid]['FormID'], b'')
            cells[grid] = (builder.fnv_id(self.cells[grid]['FormID']), land_record + navm + temporary)
        record = self._world(builder, world)
        children = _cell(persistent_cell, PERSISTENT, (0, 0), kept, b'')
        children += _blocks({grid: _cell(fid, 0, grid, b'', temp) for grid, (fid, temp) in cells.items()})
        builder.counts['exterior cells'] = len(cells)
        return record + pack_group(WORLD_CHILDREN, struct.pack('<I', world), children)

    def _world(self, builder, fid: int) -> bytes:
        """The WRLD record: FNV's name, climate (weathers.py) and the block's bounds, the Commonwealth's settings."""
        template = next(r for r, _ in walk(builder.fo4, b'WRLD') if r.form_id == WORLD_TEMPLATE)
        kept = {t: d for t, d in subrecords(template.body) if t in WORLD_COPIED}
        fnv_climate = climate(builder, int(self.world.get('CNAM.Climate', '0'), 16))
        if fnv_climate:
            kept[b'CNAM'] = struct.pack('<I', fnv_climate)
        xs, ys = [g[0] for g in self.cells], [g[1] for g in self.cells]
        bounds = (struct.pack('<2f', min(xs) * CELL_UNITS, min(ys) * CELL_UNITS),
                  struct.pack('<2f', (max(xs) + 1) * CELL_UNITS, (max(ys) + 1) * CELL_UNITS))
        subs = pack_subrecord('EDID', f'FNV_{self.world["EditorID"]}\0'.encode())
        subs += pack_subrecord('FULL', (self.world.get('FULL', self.world['EditorID']) + '\0').encode('cp1252'))
        subs += b''.join(pack_subrecord(t.decode(), kept[t]) for t in WORLD_COPIED[:-2] if t in kept)
        subs += pack_subrecord('DATA', kept[b'DATA']) + pack_subrecord('NAM0', bounds[0])
        subs += pack_subrecord('NAM9', bounds[1]) + (pack_subrecord('XWEM', kept[b'XWEM']) if b'XWEM' in kept else b'')
        return pack_fo4_record('WRLD', fid, 0, subs)

    def _land(self, builder, rec: dict, mix: dict, data_dir: Path) -> bytes:
        """The FO4 LAND of FNV LAND `rec`: its vertex data and, per quadrant, its limited `mix` (land_layers): the
        heaviest texture as the base (FO4 draws the base first), the rest as alpha layers with their shares."""
        subs = pack_subrecord('DATA', struct.pack('<I', int(rec.get('DATA.Flags', 0))))
        subs += b''.join(pack_subrecord(t, bytes.fromhex(rec[t])) for t in ('VNML', 'VHGT', 'VCLR') if rec.get(t))
        for quad in range(4):
            layers = {}
            for texture, shares in mix[quad]:
                fo4 = self._ltex(builder, texture, data_dir)
                layers[fo4] = layers.get(fo4, 0) + shares
            (base, _), *alpha = layers.items()
            subs += pack_subrecord('BTXT', struct.pack('<IBBh', base, quad, 0, BASE_LAYER))
            for layer, (fo4, shares) in enumerate(alpha):
                subs += pack_subrecord('ATXT', struct.pack('<IBBH', fo4, quad, 0, layer))
                subs += pack_subrecord('VTXT', b''.join(struct.pack('<HHf', pos, 0, shares[pos])
                                                        for pos in np.flatnonzero(shares > MIN_SHARE)))
        builder.counts['LAND'] += 1
        return pack_fo4_record('LAND', builder.fnv_id(rec['FormID']), 0, subs)

    def _ltex(self, builder, fnv: 'str | None', data_dir: Path) -> int:
        """The FO4 LTEX for FNV LTEX FormID `fnv`, made once; for none (0), FNV's default texture's (FO4's own
        default is another texture). See: docs/fork/fo4_spikes.md#spike-4-exterior"""
        if not fnv or int(fnv, 16) == 0:
            fnv = min((k for k, r in self._ltex_records().items() if r.get('ICON', '').lower() == DEFAULT_LAND_TEXTURE),
                      default=None)
            if fnv is None:
                return 0
        if fnv not in self.made:
            rec = self.textures.get(fnv) or self._ltex_records().get(fnv)
            self.made[fnv] = self._write_ltex(builder, rec, data_dir) if rec and rec.get('ICON') else 0
        return self.made[fnv]

    def _ltex_records(self) -> dict:
        """FNV's LTEX records by FormID, read once."""
        if not self.textures:
            self.textures = {r['FormID']: r for r in export_records(self.export_dir, 'LTEX')}
        return self.textures

    def _write_ltex(self, builder, rec: dict, data_dir: Path) -> int:
        """An LTEX and its texture set for FNV LTEX `rec`, textures written into `data_dir`; the LTEX FormID."""
        txst, ltex = builder.new_id(f'TXST {rec["FormID"]}'), builder.fnv_id(rec['FormID'])
        diffuse, normal, specular = _landscape_textures(self.export_dir, rec, data_dir)
        edid = f'FNV_{rec["EditorID"]}'
        sets = pack_subrecord('EDID', f'{edid}_TXST\0'.encode()) + pack_subrecord('OBND', bytes(12))
        sets += b''.join(pack_subrecord(t, (p + '\0').encode()) for t, p in (('TX00', diffuse), ('TX01', normal),
                                                                            ('TX07', specular)) if p)
        builder.writer.add_record('TXST', pack_fo4_record('TXST', txst, 0, sets + pack_subrecord('DNAM', bytes(2))))
        subs = pack_subrecord('EDID', f'{edid}\0'.encode()) + pack_subrecord('TNAM', struct.pack('<I', txst))
        subs += pack_subrecord('MNAM', struct.pack('<I', LAND_MATERIAL))
        subs += pack_subrecord('HNAM', bytes([int(rec.get('HNAM.Friction', 30)), int(rec.get('HNAM.Restitution', 30))]))
        subs += pack_subrecord('SNAM', bytes([int(rec.get('SNAM.Specular', 30))]))
        grown = (self.grasses.grass(builder, int(rec[f'Grass[{i}]'], 16)) for i in range(_grass_count(rec)))
        subs += b''.join(pack_subrecord('GNAM', struct.pack('<I', g)) for g in grown if g)
        builder.writer.add_record('LTEX', pack_fo4_record('LTEX', ltex, 0, subs))
        builder.counts['LTEX'] += 1
        return ltex


def _grass_count(rec: dict) -> int:
    """How many grasses FNV LTEX `rec` lists (Grass[0]...)."""
    return sum(1 for k in rec if k.startswith('Grass['))


def _landscape_textures(export_dir: Path, rec: dict, data_dir: Path) -> tuple:
    """(diffuse, normal, specular) texture paths of an FNV LTEX under FO4's Textures; '' where FNV has none.

    A DXT1 normal map has no specular alpha (all FNV ground's): the dim mask Skyrim's conversion gives it.
    """
    rel = 'textures\\landscape\\' + rec['ICON'].replace('/', '\\').lower()
    normal_rel = rel[:-4] + '_n.dds'
    out = []
    for src in (rel, normal_rel):
        source = export_dir / src.replace('\\', '/')
        target = fo4_texture(src) if source.exists() else ''
        if target:
            (data_dir / 'Textures' / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, data_dir / 'Textures' / target)
        out.append(target)
    specular = ''
    if out[1]:
        specular = out[1][:-6] + '_s.dds'
        normal = (export_dir / normal_rel.replace('\\', '/')).read_bytes()
        image = spec_image(normal, smoothness(float(rec.get('SNAM.Specular', 30))))
        if normal[84:88] == b'DXT1':
            image[:, :, 0] = SPECULAR_ALPHA
        (data_dir / 'Textures' / specular).write_bytes(normal_map(image))
    return out[0], out[1], specular


def _grid(ref: dict) -> tuple:
    """The grid cell a reference stands in."""
    return math.floor(float(ref['PosX']) / CELL_UNITS), math.floor(float(ref['PosY']) / CELL_UNITS)


def _cell(fid: int, flags: int, grid: tuple, persistent: bytes, temporary: bytes) -> bytes:
    """An exterior CELL and its children group."""
    subs = pack_subrecord('DATA', struct.pack('<H', CELL_DATA)) + pack_subrecord('XCLC', struct.pack('<iiI', *grid, 0))
    subs += pack_subrecord('LTMP', bytes(4)) + pack_subrecord('XCLW', struct.pack('<f', 3.4028234663852886e+38))
    label = struct.pack('<I', fid)
    kids = (pack_group(PERSISTENT_CHILDREN, label, persistent) if persistent else b'') + (
        pack_group(TEMPORARY_CHILDREN, label, temporary) if temporary else b'')
    return pack_fo4_record('CELL', fid, flags, subs) + (pack_group(CELL_CHILDREN, label, kids) if kids else b'')


def _blocks(cells: dict) -> bytes:
    """Grid cells {(x, y): CELL and children} in block (32 cells) and sub-block (8 cells) groups, labelled (y, x)."""
    blocks = {}
    for (x, y), body in sorted(cells.items()):
        sub = blocks.setdefault((y // 32, x // 32), {})
        sub[(y // 8, x // 8)] = sub.get((y // 8, x // 8), b'') + body
    return b''.join(pack_group(BLOCK, struct.pack('<hh', *b), b''.join(
        pack_group(SUB_BLOCK, struct.pack('<hh', *s), body) for s, body in sorted(subs.items())))
        for b, subs in sorted(blocks.items()))
