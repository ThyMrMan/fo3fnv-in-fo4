"""A block of an FNV worldspace as an FO4 worldspace, for the cell spike.

The cells within `radius` of a grid cell keep their land (heights, normals,
colors and every texture layer: FO4's LAND is FNV's) and references; the
persistent references standing in the block (doors) go in the worldspace's
persistent cell. The worldspace takes the Commonwealth's climate, water and
map settings. Landscape textures become LTEX records with FO4 texture sets:
FNV's diffuse and normal map, and a specular map from the normal map's
alpha. Grass, trees (SpeedTree) and LOD are not converted. Records made here
take ids from EXTERIOR_FIRST on, so the interior's ids do not move.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import math
import shutil
import struct
from pathlib import Path

from asset_convert.texture.dds_codec import write_normal_dds
from asset_convert.texture.landscape_normals import SPECULAR_ALPHA
from fo4_import.base.writer import pack_fo4_record
from fo4_import.nif.convert_static import fo4_texture, smoothness, spec_image
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.text_reader import parse_export_file
from tes5_import.base.writer import pack_group, pack_subrecord

#: First object id of the exterior's own records, past the interior's sequential ids.
EXTERIOR_FIRST = 0x100000
CELL_UNITS = 4096.0
#: Fallout4.esm's Commonwealth, whose climate, water and map settings the worldspace takes.
WORLD_TEMPLATE = 0x3C
WORLD_COPIED = (b'CNAM', b'NAM2', b'NAM3', b'NAM4', b'DNAM', b'MNAM', b'ONAM', b'NAMA', b'DATA', b'XWEM')
#: BTXT layer of a base texture: vanilla's -1 (every one of the 2,000+ sampled), never an alpha layer's index.
BASE_LAYER = -1
#: Material type of vanilla landscape textures (FO4 MATT), and the CELL DATA flag Has Water vanilla sets.
LAND_MATERIAL, CELL_DATA = 0x12F35, 0x02
#: Record flags of a persistent cell, and the persistent flag of a reference.
PERSISTENT = 0x400
#: Exterior group types: world children, cell block, sub-block, cell children, persistent, temporary.
WORLD_CHILDREN, BLOCK, SUB_BLOCK, CELL_CHILDREN, PERSISTENT_CHILDREN, TEMPORARY_CHILDREN = 1, 4, 5, 6, 8, 9


class Exterior:
    """The FNV cells, land and references of one block; `refs` lists every reference placed."""

    def __init__(self, export_dir: Path, all_refs: list, world: str, center: tuple, radius: int):
        """The block of FNV worldspace `world` within `radius` cells of `center` (grid x, y)."""
        self.export_dir, self.next = export_dir, EXTERIOR_FIRST
        self.world = next(r for r in parse_export_file(str(export_dir / 'WRLD.txt')) if r.get('EditorID') == world)
        cells = [r for r in parse_export_file(str(export_dir / 'CELL.txt'))
                 if r.get('ParentWRLD') == self.world['FormID']]
        self.persistent_cell = next(r['FormID'] for r in cells if int(r['RecordFlags']) & PERSISTENT)
        self.cells = {(int(r['XCLC.X']), int(r['XCLC.Y'])): r for r in cells if 'XCLC.X' in r and not
                      int(r['RecordFlags']) & PERSISTENT and max(abs(int(r['XCLC.X']) - center[0]),
                                                                abs(int(r['XCLC.Y']) - center[1])) <= radius}
        own = {r['FormID']: grid for grid, r in self.cells.items()}
        self.by_cell = {grid: [] for grid in self.cells}
        self.persistent = []
        for ref in all_refs:
            if ref.get('ParentCELL') in own:
                self.by_cell[own[ref['ParentCELL']]].append(ref)
            elif ref.get('ParentCELL') == self.persistent_cell and _grid(ref) in self.cells:
                self.persistent.append(ref)
        self.refs = self.persistent + [r for refs in self.by_cell.values() for r in refs]
        self.land = {r['ParentCELL']: r for r in parse_export_file(str(export_dir / 'LAND.txt')) if r['ParentCELL'] in own}
        self.textures, self.made = {}, {}

    def new_id(self, plugin_index: int) -> int:
        """The next exterior FormID in plugin `plugin_index`."""
        self.next += 1
        return plugin_index << 24 | self.next - 1

    def ids(self, plugin_index: int) -> dict:
        """{FNV reference FormID: FO4 FormID} of every reference in the block."""
        return {r['FormID']: self.new_id(plugin_index) for r in self.refs}

    def placement_order(self) -> list:
        """Every reference in group()'s order: the persistent cell's, then each cell's."""
        return self.persistent + [r for grid in sorted(self.cells) for r in self.by_cell[grid]]

    def group(self, builder, place, data_dir: Path) -> bytes:
        """The WRLD group's body: worldspace, persistent cell, grid cells; `place(refs)` packs (persistent, temporary).

        Records made here (LTEX, TXST) are added to `builder.writer`.
        """
        index = builder.next_id >> 24
        world, persistent_cell = self.new_id(index), self.new_id(index)
        cells, kept = {}, place(self.persistent)[0]
        for grid in sorted(self.cells):
            persistent, temporary = place(self.by_cell[grid])
            kept += persistent
            land = self.land.get(self.cells[grid]['FormID'])
            land_record = self._land(builder, land, data_dir) if land else b''
            cells[grid] = (self.new_id(index), land_record + temporary)
        record = self._world(builder, world)
        children = _cell(persistent_cell, PERSISTENT, (0, 0), kept, b'')
        children += _blocks({grid: _cell(fid, 0, grid, b'', temp) for grid, (fid, temp) in cells.items()})
        builder.counts['exterior cells'] = len(cells)
        builder.next_id = max(builder.next_id, index << 24 | self.next)
        return record + pack_group(WORLD_CHILDREN, struct.pack('<I', world), children)

    def _world(self, builder, fid: int) -> bytes:
        """The WRLD record: FNV's name and the block's bounds, the Commonwealth's settings."""
        template = next(r for r, _ in walk(builder.fo4, b'WRLD') if r.form_id == WORLD_TEMPLATE)
        kept = {t: d for t, d in subrecords(template.body) if t in WORLD_COPIED}
        xs, ys = [g[0] for g in self.cells], [g[1] for g in self.cells]
        bounds = (struct.pack('<2f', min(xs) * CELL_UNITS, min(ys) * CELL_UNITS),
                  struct.pack('<2f', (max(xs) + 1) * CELL_UNITS, (max(ys) + 1) * CELL_UNITS))
        subs = pack_subrecord('EDID', f'FNV_{self.world["EditorID"]}\0'.encode())
        subs += pack_subrecord('FULL', (self.world.get('FULL', self.world['EditorID']) + '\0').encode('cp1252'))
        subs += b''.join(pack_subrecord(t.decode(), kept[t]) for t in WORLD_COPIED[:-2] if t in kept)
        subs += pack_subrecord('DATA', kept[b'DATA']) + pack_subrecord('NAM0', bounds[0])
        subs += pack_subrecord('NAM9', bounds[1]) + (pack_subrecord('XWEM', kept[b'XWEM']) if b'XWEM' in kept else b'')
        return pack_fo4_record('WRLD', fid, 0, subs)

    def _land(self, builder, rec: dict, data_dir: Path) -> bytes:
        """The FO4 LAND of FNV LAND `rec`: its vertex data and texture layers, per quadrant in FNV's layer order."""
        subs = pack_subrecord('DATA', struct.pack('<I', int(rec.get('DATA.Flags', 0))))
        subs += b''.join(pack_subrecord(t, bytes.fromhex(rec[t])) for t in ('VNML', 'VHGT', 'VCLR') if rec.get(t))
        base, alpha = {}, {}
        for i in range(int(rec.get('LayerCount', 0))):
            key = f'Layer[{i}]'
            if rec[f'{key}.Type'] == 'BASE':
                base.setdefault(int(rec[f'{key}.BTXT.Quadrant']), rec[f'{key}.BTXT.Texture'])
            else:
                alpha.setdefault(int(rec[f'{key}.ATXT.Quadrant']), []).append((int(rec[f'{key}.ATXT.Layer']), key))
        for quad in sorted(set(base) | set(alpha)):
            subs += pack_subrecord('BTXT', struct.pack('<IBBh', self._ltex(builder, base.get(quad), data_dir), quad, 0,
                                                       BASE_LAYER))
            for layer, (_, key) in enumerate(sorted(alpha.get(quad, []))):
                subs += pack_subrecord('ATXT', struct.pack('<IBBH', self._ltex(builder, rec[f'{key}.ATXT.Texture'],
                                                                               data_dir), quad, 0, layer))
                subs += pack_subrecord('VTXT', b''.join(struct.pack('<HHf', int(rec[f'{key}.VT[{v}].Pos']), 0,
                                                                    float(rec[f'{key}.VT[{v}].Opacity']))
                                                        for v in range(int(rec[f'{key}.VTXTCount']))))
        builder.counts['LAND'] += 1
        return pack_fo4_record('LAND', self.new_id(builder.next_id >> 24), 0, subs)

    def _ltex(self, builder, fnv: 'str | None', data_dir: Path) -> int:
        """The FO4 LTEX for FNV LTEX FormID `fnv`, made once; 0 (the default texture) for none."""
        if not fnv or int(fnv, 16) == 0:
            return 0
        if fnv not in self.made:
            rec = self.textures.get(fnv) or self._ltex_records().get(fnv)
            self.made[fnv] = self._write_ltex(builder, rec, data_dir) if rec and rec.get('ICON') else 0
        return self.made[fnv]

    def _ltex_records(self) -> dict:
        """FNV's LTEX records by FormID, read once."""
        if not self.textures:
            self.textures = {r['FormID']: r for r in parse_export_file(str(self.export_dir / 'LTEX.txt'))}
        return self.textures

    def _write_ltex(self, builder, rec: dict, data_dir: Path) -> int:
        """An LTEX and its texture set for FNV LTEX `rec`, textures written into `data_dir`; the LTEX FormID."""
        index = builder.next_id >> 24
        txst, ltex = self.new_id(index), self.new_id(index)
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
        builder.writer.add_record('LTEX', pack_fo4_record('LTEX', ltex, 0, subs))
        builder.counts['LTEX'] += 1
        return ltex


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
        write_normal_dds(image, data_dir / 'Textures' / specular)
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
