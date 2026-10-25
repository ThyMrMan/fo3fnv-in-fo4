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
import struct
from pathlib import Path

import numpy as np

from asset_convert.texture.landscape_normals import SPECULAR_ALPHA
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.grass import Grasses
from fo4_import.spike.land_layers import blend_borders, limit_textures, quadrant_mix
from fo4_import.spike.navmesh import grid_parent
from fo4_import.spike.music import music_of
from fo4_import.spike.regions import regions_of
from fo4_import.spike.weather_imagespace import world_imagespace
from fo4_import.spike.weathers import climate
from fo4_import.nif.convert_static import fo4_texture, smoothness, spec_map_path
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import spec_map
from fo4_import.spike.statics import copy_texture, stage_derived
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_group, pack_subrecord
from tes5_import.navmesh.world import decode_vhgt

CELL_UNITS = 4096.0
#: A cell's landscape squares per side and their size (33 VHGT points a side).
LAND_SQUARES = 32
LAND_SPACING = CELL_UNITS / LAND_SQUARES
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
#: XCLW of a cell at its worldspace's default water height (FLT_MAX, as 36,320 of Fallout4.esm's exterior cells).
DEFAULT_WATER = 3.4028234663852886e+38
#: Exterior group types: world children, cell block, sub-block, cell children, persistent, temporary.
WORLD_CHILDREN, BLOCK, SUB_BLOCK, CELL_CHILDREN, PERSISTENT_CHILDREN, TEMPORARY_CHILDREN = 1, 4, 5, 6, 8, 9


class Exterior:
    """The FNV cells, land and references of one rectangle of a worldspace's cells (or all of them); `refs` lists
    every reference placed, `locations` its spike.locations.Locations once made."""

    def __init__(self, export_dir: Path, all_refs: list, world: str, lo: 'tuple | None' = None,
                 hi: 'tuple | None' = None):
        """The cells of FNV worldspace `world` from grid `lo` to `hi` (x, y; both included); every cell without."""
        self.export_dir, self.locations = export_dir, None
        self.world = next(r for r in export_records(export_dir, 'WRLD') if r.get('EditorID') == world)
        cells = [r for r in export_records(export_dir, 'CELL')
                 if r.get('ParentWRLD') == self.world['FormID']]
        self.persistent_cell = next(r['FormID'] for r in cells if int(r['RecordFlags']) & PERSISTENT)
        self.cells = {(int(r['XCLC.X']), int(r['XCLC.Y'])): r for r in cells if 'XCLC.X' in r and not
                      int(r['RecordFlags']) & PERSISTENT and _within(int(r['XCLC.X']), int(r['XCLC.Y']), lo, hi)}
        self.own = own = {r['FormID']: grid for grid, r in self.cells.items()}
        self.by_cell = {grid: [] for grid in self.cells}
        self.persistent = []
        for ref in all_refs:
            if ref.get('ParentCELL') in own:
                self.by_cell[own[ref['ParentCELL']]].append(ref)
            elif ref.get('ParentCELL') == self.persistent_cell and _grid(ref) in self.cells:
                self.persistent.append(ref)
        self.refs = self.persistent + [r for refs in self.by_cell.values() for r in refs]
        self.land = {r['ParentCELL']: r for r in export_records(export_dir, 'LAND') if r['ParentCELL'] in own}
        self.textures, self.made, self.heights = {}, {}, {}
        self.grasses = Grasses(export_dir)

    def add_persistent(self, refs: list) -> list:
        """Add persistent `refs` from past the block to its persistent cell."""
        self.persistent += refs
        self.refs = self.persistent + [r for grid in self.by_cell.values() for r in grid]
        return self.refs

    def on_ground(self, ref: dict, pos: tuple) -> tuple:
        """`ref`'s position `pos`, raised to ground() when below it in the block.
        See: docs/fork/fo4_pipeline.md#actors-on-the-ground
        """
        ground = self.ground(pos[0], pos[1]) if self.holds(ref) else None
        return pos if ground is None or pos[2] >= ground else (pos[0], pos[1], ground)

    def ground(self, x: float, y: float) -> 'float | None':
        """The highest corner of the landscape square at (x, y); None outside the block or without land."""
        grid = (math.floor(x / CELL_UNITS), math.floor(y / CELL_UNITS))
        if grid not in self.heights:
            land = self.land.get(self.cells[grid]['FormID'], {}) if grid in self.cells else {}
            self.heights[grid] = decode_vhgt(land['VHGT']) if land.get('VHGT') else None
        heights = self.heights[grid]
        if heights is None:
            return None
        col = min(int((x - grid[0] * CELL_UNITS) / LAND_SPACING), LAND_SQUARES - 1)
        row = min(int((y - grid[1] * CELL_UNITS) / LAND_SPACING), LAND_SQUARES - 1)
        return float(heights[row:row + 2, col:col + 2].max())

    def holds(self, ref: dict) -> bool:
        """Whether FNV reference `ref` stands in the block (by cell, or by position)."""
        cell = ref.get('ParentCELL')
        return cell in self.own or cell == self.persistent_cell and _grid(ref) in self.cells

    def placement_order(self) -> list:
        """Every reference in group()'s order: the persistent cell's, then each cell's."""
        return self.persistent + [r for grid in sorted(self.cells) for r in self.by_cell[grid]]

    def pathing(self, builder) -> dict:
        """{FNV cell: (FO4 worldspace, grid)}: each grid cell's navmesh pathing cell."""
        world = builder.fnv_id(self.world['FormID'])
        return {r['FormID']: (world, grid_parent(*grid)) for grid, r in self.cells.items()}

    def group(self, builder, place, data_dir: Path, navmesh: dict, actors: dict = None) -> bytes:
        """The WRLD group's body: worldspace, persistent cell, grid cells; `place(refs)` packs (persistent, temporary).

        `navmesh` holds each FNV cell's NAVM records, `actors` its ACHRs (persistent, temporary): persistent ones
        go to the persistent cell. Records made here (LTEX, TXST) are added to `builder.writer`.
        """
        world, persistent_cell = builder.fnv_id(self.world['FormID']), builder.fnv_id(self.persistent_cell)
        builder.world_imagespace = world_imagespace(int(self.world['FormID'], 16))
        actors, regions = actors or {}, regions_of(builder)
        zones = music_of(builder).zones(world, int(self.persistent_cell, 16),
                                        {grid: int(r['FormID'], 16) for grid, r in self.cells.items()})
        cells, kept = {}, place(self.persistent)[0] + b''.join(actors.get(self.persistent_cell, (b'', b'')))
        lands = {grid: self.land.get(self.cells[grid]['FormID']) for grid in sorted(self.cells)}
        grassy = frozenset(k for k, r in self._ltex_records().items() if _grass_count(r))
        mixes = limit_textures(blend_borders({grid: quadrant_mix(land) for grid, land in lands.items() if land}), grassy)
        for grid in sorted(self.cells):
            persistent, temporary = place(self.by_cell[grid])
            people = actors.get(self.cells[grid]['FormID'], (b'', b''))
            kept, temporary = kept + persistent + people[0], temporary + people[1]
            land = lands[grid]
            land_record = self._land(builder, land, mixes.get(grid), data_dir) if land else b''
            navm = navmesh.get(self.cells[grid]['FormID'], b'')
            zone = builder.zones.get(int(self.cells[grid].get('XEZN.EncounterZone', '0'), 16), 0)
            water = float(self.cells[grid].get('XCLW.WaterHeight', DEFAULT_WATER))
            cells[grid] = (builder.fnv_id(self.cells[grid]['FormID']), land_record + navm + temporary,
                           (self.locations.of_grid(grid), zone), water,
                           regions.xclr(int(self.cells[grid]['FormID'], 16),
                                        zones.get(int(self.cells[grid]['FormID'], 16), ())))
        record = self._world(builder, world)
        children = _cell(persistent_cell, PERSISTENT, (0, 0), kept, b'')
        children += _blocks({grid: _cell(fid, 0, grid, b'', temp, spot, water, xclr)
                             for grid, (fid, temp, spot, water, xclr) in cells.items()})
        builder.counts['exterior cells'] = len(cells)
        return record + pack_group(WORLD_CHILDREN, struct.pack('<I', world), children)

    def _world(self, builder, fid: int) -> bytes:
        """The WRLD record: FNV's name, location, climate (weathers.py) and the block's bounds, the Commonwealth's
        settings."""
        template = next(r for r, _ in walk(builder.fo4, b'WRLD') if r.form_id == WORLD_TEMPLATE)
        kept = {t: d for t, d in subrecords(template.body) if t in WORLD_COPIED}
        fnv_climate = climate(builder, int(self.world.get('CNAM.Climate', '0'), 16))
        if fnv_climate:
            kept[b'CNAM'] = struct.pack('<I', fnv_climate)
        kept.update(_heights(self.world, kept))
        xs, ys = [g[0] for g in self.cells], [g[1] for g in self.cells]
        bounds = (struct.pack('<2f', min(xs) * CELL_UNITS, min(ys) * CELL_UNITS),
                  struct.pack('<2f', (max(xs) + 1) * CELL_UNITS, (max(ys) + 1) * CELL_UNITS))
        subs = pack_subrecord('EDID', f'FNV_{self.world["EditorID"]}\0'.encode())
        subs += pack_subrecord('FULL', (self.world.get('FULL', self.world['EditorID']) + '\0').encode('cp1252'))
        subs += pack_subrecord('XLCN', struct.pack('<I', self.locations.root))
        subs += b''.join(pack_subrecord(t.decode(), kept[t]) for t in WORLD_COPIED[:-2] if t in kept)
        subs += pack_subrecord('DATA', kept[b'DATA']) + pack_subrecord('NAM0', bounds[0])
        subs += pack_subrecord('NAM9', bounds[1]) + pack_subrecord('ZNAM', struct.pack('<I', music_of(builder).silence()))
        subs += pack_subrecord('XWEM', kept[b'XWEM']) if b'XWEM' in kept else b''
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

    A DXT1 normal map has no specular alpha (all FNV ground's): the dim mask Skyrim's conversion gives it. The
    specular map is named for the LTEX's glossiness (spec_map_path); every texture goes through statics.copy_texture
    and stage_derived (once per run, not while the staged copy is current).
    """
    rel = 'textures\\landscape\\' + rec['ICON'].replace('/', '\\').lower()
    normal_rel = rel[:-4] + '_n.dds'
    out = []
    for src in (rel, normal_rel):
        found = (export_dir / src.replace('\\', '/')).exists()
        if found:
            copy_texture(export_dir, data_dir, src)
        out.append(fo4_texture(src) if found else '')
    if not out[1]:
        return out[0], '', ''
    glossiness, normal = float(rec.get('SNAM.Specular', 30)), export_dir / normal_rel.replace('\\', '/')
    with open(normal, 'rb') as f:
        dxt1 = f.read(88)[84:88] == b'DXT1'
    specular = spec_map_path(normal_rel, glossiness)
    stage_derived(data_dir, specular, spec_map, (normal,), smoothness(glossiness), SPECULAR_ALPHA if dxt1 else None)
    return out[0], out[1], specular


def _within(x: int, y: int, lo: 'tuple | None', hi: 'tuple | None') -> bool:
    """Whether grid cell (x, y) is in `lo`..`hi` (included); always when unbounded."""
    return lo is None or lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]


def _grid(ref: dict) -> tuple:
    """The grid cell a reference stands in."""
    return math.floor(float(ref['PosX']) / CELL_UNITS), math.floor(float(ref['PosY']) / CELL_UNITS)


def _heights(world: dict, template: dict) -> dict:
    """{DNAM, NAM4}: FNV worldspace `world`'s default land and water heights and LOD water height, each where FNV
    has it (else `template`'s, the Commonwealth's).
    See: docs/fork/fo4_pipeline.md#water-heights
    """
    land, water = struct.unpack('<2f', template[b'DNAM'])
    out = {b'DNAM': struct.pack('<2f', float(world.get('DNAM.DefaultLandHeight', land)),
                                float(world.get('DNAM.DefaultWaterHeight', water)))}
    return {**out, b'NAM4': struct.pack('<f', float(world['NAM4.LODWaterHeight']))} if 'NAM4.LODWaterHeight' in world \
        else out


def _cell(fid: int, flags: int, grid: tuple, persistent: bytes, temporary: bytes, place: tuple = (0, 0),
          water: float = DEFAULT_WATER, regions: bytes = b'') -> bytes:
    """An exterior CELL and its children group; `place` its (location, encounter zone), 0 for none; `water` its
    water height (DEFAULT_WATER: the worldspace's); `regions` its XCLR (spike.regions)."""
    subs = pack_subrecord('DATA', struct.pack('<H', CELL_DATA)) + pack_subrecord('XCLC', struct.pack('<iiI', *grid, 0))
    subs += pack_subrecord('LTMP', bytes(4)) + pack_subrecord('XCLW', struct.pack('<f', water)) + regions
    subs += b''.join(pack_subrecord(tag, struct.pack('<I', form)) for tag, form in zip(('XLCN', 'XEZN'), place) if form)
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
