"""FNV's prebuilt terrain LOD as Fallout 4's.

Each FNV tile (meshes/landscape/lod/<world>/<world>.level<L>.x<X>.y<Y>.nif,
named by its south-west cell) becomes Meshes/Terrain/<FO4 world>/<FO4 world>.<L>.<X>.<Y>.btr:
one land shape scaled by the level, positions in tile units (world / level).
FNV lays its tile textures out mirrored on both axes (u = 1 - x, v = y),
FO4 as u = x, v = 1 - y, and reads a tile's normal map by name; both
textures turn half a turn and the UVs follow. The normal map is model space
in both games, FNV's x, y, z in RGB and FO4's x, z, y, so green and blue swap.
The tile's LOD water (its unshaded shapes) becomes vanilla's WATER node: one
flat, effect-shaded shape, cut by cell into 16 segments at level 4 so the
engine hides the loaded cells' water, as Commonwealth tiles are laid out.
LODSettings/<FO4 world>.lod names the tile grid.

See: docs/fork/fo4_pipeline.md#terrain-lod
"""

import re
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.ba2_pack import stage_texture
from fo4_import.face.texture import TEXCONV
from fo4_import.nif import file as F
from fo4_import.nif.blocks import SHADER_LOD_LAND, pack_tri_shape
from fo4_import.pipeline.work_cache import cached
from fo4_import.pipeline.export_index import asset_root
from pyffi.formats.nif import NifFormat

apply_patches()

#: An FNV tile's file name: level, south-west cell x and y.
TILE_RE = re.compile(r'\.level(\d+)\.x(-?\d+)\.y(-?\d+)\.nif$', re.I)
#: Every vanilla .btr's vertex layout: half-float position (unused W) and UV, 12 bytes.
VERTEX_DESC = 0x300000000203
#: Lowest LOD level FO4 draws (every vanilla LODSettings file's).
MIN_LEVEL = 4
#: The work cache's site of a converted tile.
SITE = 'terrain_lod'
#: Bumped when the written files change; part of each texture's signature.
VERSION = 2
#: Vanilla's LOD-land shader fields beside the shader type, name and texture set (commonwealth.4.0.0.btr's).
SHADER = {'extra': [], 'controller': -1, 'flags1': 0x80401000, 'flags2': 3, 'uv_offset': (0.0, 0.0),
          'uv_scale': (1.0, 1.0), 'emissive_color': (0.0, 0.0, 0.0), 'emissive_multiple': 1.0, 'clamp': 0,
          'alpha': 1.0, 'refraction': 0.0, 'smoothness': 0.0, 'specular_color': (1.0, 1.0, 1.0),
          'specular_strength': 1.0, 'subsurface_rolloff': 0.0, 'rimlight_power': 3.4028234663852886e38,
          'backlight_power': 0.0, 'grayscale_scale': 1.0, 'fresnel_power': 5.0, 'wetness': (-1.0,) * 6}
#: The node and shape flags of every vanilla tile.
FLAGS = 14
#: Every vanilla tile's water vertex layout: half-float position (unused W) only, 8 bytes.
WATER_DESC = 0x100000000002
#: Vanilla's LOD water effect shader (every Commonwealth tile's WATER shape's), the name string empty.
WATER_SHADER = {'name': 2, 'extra': [], 'controller': -1, 'flags1': 0x80000000, 'flags2': 1, 'uv_offset': (0.0, 0.0),
                'uv_scale': (1.0, 1.0), 'source_texture': '', 'clamp': 3, 'lighting_influence': 255, 'env_min_lod': 0,
                'unused': 0, 'falloff': (0.0, 0.0, 0.0, 0.0), 'base_color': (1.0, 1.0, 1.0, 1.0),
                'base_color_scale': 1.0, 'soft_depth': 100.0, 'greyscale': '', 'env_map': '', 'normal': '',
                'env_mask': '', 'env_map_scale': 1.0}
#: Cells across a lowest-level tile; its water is cut into this many squared segments, one per cell.
SEGMENT_CELLS = 4
#: A segment's parent array index when it has none.
NO_PARENT = 0xFFFFFFFF


def tiles(export_dir: Path, world: str) -> list:
    """[(level, x, y, mesh)] of FNV world `world`'s LOD tiles with both their textures, sorted (Lucky38World
    ships a level-4 mesh at x-16 y-12 with none).
    See: docs/fork/fo4_pipeline.md#terrain-lod
    """
    folder = asset_root(export_dir, 'meshes', 'landscape', 'lod', world.lower())
    found = ((TILE_RE.search(p.name), p) for p in folder.glob('*.nif')) if folder.is_dir() else ()
    textures = asset_root(export_dir, 'textures', 'landscape', 'lod', world.lower())
    return sorted((int(m[1]), int(m[2]), int(m[3]), p) for m, p in found if m and all(
        (textures / kind / f'{world.lower()}.n.level{m[1]}.x{m[2]}.y{m[3]}.dds').is_file()
        for kind in ('diffuse', 'normals')))


def lod_settings(found: list) -> bytes:
    """The LODSettings file of tiles `found` (tiles()): south-west cell, size in cells (a power-of-two count of
    top-level tiles across, as every vanilla grid), lowest and highest level.
    See: docs/fork/fo4_pipeline.md#terrain-lod
    """
    top = max(level for level, *_ in found)
    xs, ys = [x for level, x, _, _ in found if level == top], [y for level, _, y, _ in found if level == top]
    across = (max(max(xs) - min(xs), max(ys) - min(ys)) + top) // top
    return struct.pack('<hhIII', min(xs), min(ys), top * (1 << (across - 1).bit_length()), MIN_LEVEL, top)


def read_tile(path: Path):
    """The pyffi data of the FNV tile at `path`."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    return data


def _shaded(block) -> bool:
    """Whether shape `block` has a BSShaderPPLightingProperty (a tile's land)."""
    return any(isinstance(p, NifFormat.BSShaderPPLightingProperty) for p in block.get_properties())


def land_shape(data) -> tuple:
    """(positions, uvs, triangles) as arrays of FNV tile `data`'s (read_tile) land: its shaded shape (the others,
    with no properties, are the tile's LOD water).
    See: docs/fork/fo4_pipeline.md#terrain-lod
    """
    land = next(b for b in data.blocks if isinstance(b, NifFormat.NiTriShape) and _shaded(b))
    shape = land.data
    return (np.array([(v.x, v.y, v.z) for v in shape.vertices], float),
            np.array([(t.u, t.v) for t in shape.uv_sets[0]], float),
            np.array([(t.v_1, t.v_2, t.v_3) for t in shape.triangles], int))


def water_shape(data) -> tuple:
    """(positions, triangles) of FNV tile `data`'s (read_tile) LOD water, its unshaded shapes joined, in the tile's frame
    as the land's, without the skirts (walls with no area seen from above); only the vertices kept triangles use.
    See: docs/fork/fo4_pipeline.md#distant-water
    """
    pos, tris = [np.zeros((0, 3))], [np.zeros((0, 3), int)]
    for block in data.blocks:
        if isinstance(block, NifFormat.NiTriShape) and not _shaded(block) and block.data.num_triangles:
            tris.append(np.array([(t.v_1, t.v_2, t.v_3) for t in block.data.triangles], int) + sum(map(len, pos)))
            pos.append(np.array([(v.x, v.y, v.z) for v in block.data.vertices], float))
    pos, tris = np.concatenate(pos), np.concatenate(tris)
    flat = np.pad(pos[:, :2], ((0, 0), (0, 1)))
    seen = np.cross(flat[tris[:, 1]] - flat[tris[:, 0]], flat[tris[:, 2]] - flat[tris[:, 0]])[:, 2]
    used, tris = np.unique(tris[seen != 0], return_inverse=True)
    return pos[used], tris.reshape(-1, 3)


def without_skirts(pos: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """`tris` without FNV's skirts: a border vertex (on the tile's outer edge) under another at the same x, y
    hangs a skirt, and every triangle touching one goes.
    See: docs/fork/fo4_pipeline.md#terrain-lod
    """
    lo, hi = pos[:, :2].min(axis=0), pos[:, :2].max(axis=0)
    border = np.any((pos[:, :2] == lo) | (pos[:, :2] == hi), axis=1)
    top = {}
    for x, y, z in pos[border]:
        top[(x, y)] = max(top.get((x, y), z), z)
    skirt = border & np.array([z < top.get((x, y), z) for x, y, z in pos])
    return tris[~skirt[tris].any(axis=1)]


def tile_units(pos: np.ndarray, tris: np.ndarray, level: int) -> tuple:
    """(half-float tile-unit positions, the triangles with area in them)."""
    local = (pos / level).astype(np.float16).astype(float)
    area = np.linalg.norm(np.cross(local[tris[:, 1]] - local[tris[:, 0]], local[tris[:, 2]] - local[tris[:, 0]]), axis=1)
    return local, tris[area > 0]


def _multi_bound_node(name: int, children: list, bound: int) -> bytes:
    """A BSMultiBoundNode named string `name` holding `children`, its multi-bound `bound`, culling 1."""
    head = F.BLOCKS['NiNode'][1]({'name': name, 'extra': [], 'controller': -1, 'flags': FLAGS,
                                  'translation': (0.0, 0.0, 0.0), 'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
                                  'scale': 1.0, 'collision': -1, 'children': children})
    return head + struct.pack('<iI', bound, 1)


def _shape(name: int, local: np.ndarray, tris: np.ndarray, level: int, shader: int, vertices: tuple) -> dict:
    """A tile BSTriShape's fields: (vertex layout, vertex dicts) `vertices` at `local` positions (tile units)
    scaled by `level`."""
    lo, hi = local.min(axis=0), local.max(axis=0)
    return {'name': name, 'extra': [], 'controller': -1, 'flags': FLAGS, 'translation': (0.0, 0.0, 0.0),
            'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), 'scale': float(level), 'collision': -1,
            'bound': (*(lo + hi) / 2, float(np.linalg.norm((hi - lo) / 2))), 'skin': -1, 'shader': shader,
            'alpha_property': -1, 'vertex_desc': vertices[0], 'triangles': [tuple(map(int, t)) for t in tris],
            'vertices': vertices[1]}


def _aabb(local: np.ndarray, level: int) -> bytes:
    """A BSMultiBoundAABB of `local` positions at `level`, in world units."""
    lo, hi = local.min(axis=0), local.max(axis=0)
    return struct.pack('<6f', *((lo + hi) / 2 * level), *((hi - lo) / 2 * level))


def by_cell(local: np.ndarray, tris: np.ndarray, level: int) -> tuple:
    """(`tris` ordered by segment, triangles per segment): one per cell (module notes).
    See: docs/fork/fo4_pipeline.md#distant-water
    """
    cell = np.clip(local[tris].mean(axis=1)[:, :2] * level // 4096, 0, SEGMENT_CELLS - 1).astype(int)
    segment = cell[:, 0] * SEGMENT_CELLS + cell[:, 1]
    return tris[np.argsort(segment, kind='stable')], np.bincount(segment, minlength=SEGMENT_CELLS ** 2)


def segments(counts: np.ndarray) -> bytes:
    """A BSSubIndexTriShape trailer of segments of `counts` triangles; an empty one starts at 0.
    See: docs/fork/fo4_pipeline.md#distant-water
    """
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]]) * 3
    out = struct.pack('<3I', int(counts.sum()), len(counts), len(counts))
    return out + b''.join(struct.pack('<4I', int(s) if n else 0, int(n), NO_PARENT, 0) for s, n in zip(starts, counts))


def _water_blocks(data, level: int, first: int) -> list:
    """The WATER node's blocks (node, shape, effect shader, multi-bound, AABB) of FNV tile `data`, the node at
    block `first`; [] when the tile has no water. Level 4's shape is cut into segments by cell."""
    pos, tris = water_shape(data)
    local, tris = tile_units(pos, tris, level)
    if not len(tris):
        return []
    used, tris = np.unique(tris, return_inverse=True)
    local, tris = local[used], tris.reshape(-1, 3)
    if level == MIN_LEVEL:
        tris, counts = by_cell(local, tris, level)
    fields = _shape(2, local, tris, level, first + 2, (WATER_DESC, [{'position': tuple(p), 'bitangent_x': 0}
                                                                    for p in local]))
    shape = ('BSSubIndexTriShape', pack_tri_shape(fields) + segments(counts)) if level == MIN_LEVEL \
        else ('BSTriShape', fields)
    return [('BSMultiBoundNode', _multi_bound_node(3, [first + 1], first + 3)), shape,
            ('BSEffectShaderProperty', dict(WATER_SHADER)), ('BSMultiBound', struct.pack('<i', first + 4)),
            ('BSMultiBoundAABB', _aabb(local, level))]


def btr(path: Path, level: int, textures: tuple) -> bytes:
    """The .btr of the FNV tile at `path` of `level`, textured by (diffuse, normal) Data paths: the land, then the
    WATER node when the tile has water, in vanilla's block order."""
    data = read_tile(path)
    pos, uv, tris = land_shape(data)
    local, tris = tile_units(pos, without_skirts(pos, tris), level)
    uv = 1 - uv
    water = _water_blocks(data, level, 4)
    nif = F.NifFile(strings=['chunk', 'Land', ''] + ['WATER'] * bool(water))
    land = _shape(1, local, tris, level, 2, (VERTEX_DESC, [{'position': tuple(p), 'bitangent_x': 0, 'uv': tuple(t)}
                                                           for p, t in zip(local, uv)]))
    bound = 4 + len(water)
    nif.blocks = [('BSMultiBoundNode', _multi_bound_node(0, [1] + [4] * bool(water), bound)), ('BSTriShape', land),
                  ('BSLightingShaderProperty', {**SHADER, 'shader_type': SHADER_LOD_LAND, 'name': 2, 'texture_set': 3,
                                                'root_material': 2}),
                  ('BSShaderTextureSet', {'textures': [*textures] + [''] * 8}), *water,
                  ('BSMultiBound', struct.pack('<i', bound + 1)), ('BSMultiBoundAABB', _aabb(local, level))]
    return F.write(nif)


def lod_texture(source: Path, target: Path, normals: bool) -> None:
    """FNV LOD texture `source` in FO4's layout (turned half a turn, as FO4 lays it out), a normal map's green and blue
    swapped, as BC1 with mips at `target`."""
    rgba = np.asarray(Image.open(source).convert('RGBA'))[::-1, ::-1]
    rgba = rgba[:, :, [0, 2, 1, 3]] if normals else rgba
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / f'{target.stem}.png'
        Image.fromarray(np.ascontiguousarray(rgba), 'RGBA').save(png)
        subprocess.run([str(TEXCONV), '-nologo', '-f', 'BC1_UNORM', '-m', '0', '-o', tmp, str(png)],
                       check=True, capture_output=True, **POPEN_FLAGS)
        target.write_bytes((Path(tmp) / f'{target.stem}.dds').read_bytes())


def _signature(path: Path) -> str:
    """VERSION and `path`'s size and time: a texture's signature."""
    stat = path.stat()
    return f'terrain lod {VERSION} {stat.st_size} {stat.st_mtime_ns}'


def _texture_jobs(export_dir: Path, world: str, fo4_world: str, tile: tuple) -> list:
    """[(rel under Textures, plan)] of one tile's diffuse and normal map (stage_texture plans)."""
    level, x, y, _ = tile
    source = asset_root(export_dir, 'textures', 'landscape', 'lod', world.lower())
    name = f'{world.lower()}.n.level{level}.x{x}.y{y}.dds'
    stem = f'Terrain\\{fo4_world}\\{fo4_world}.{level}.{x}.{y}'
    diffuse, normals = source / 'diffuse' / name, source / 'normals' / name
    return [(f'{stem}.dds', lambda: (_signature(diffuse), lambda t: lod_texture(diffuse, t, False))),
            (f'{stem}_msn.dds', lambda: (_signature(normals), lambda t: lod_texture(normals, t, True)))]


def write(export_dir: Path, data_dir: Path, world: str, fo4_world: str) -> int:
    """Write FNV worldspace `world`'s terrain LOD as FO4 worldspace EditorID `fo4_world`'s into `data_dir`
    (meshes loose and work-cached, textures staged for the texture BA2); the tile count, 0 when FNV has none."""
    found = tiles(export_dir, world)
    if not found:
        return 0
    meshes = Path(data_dir) / 'Meshes' / 'Terrain' / fo4_world
    meshes.mkdir(parents=True, exist_ok=True)
    settings = Path(data_dir) / 'LODSettings' / f'{fo4_world}.lod'
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_bytes(lod_settings(found))
    jobs = [job for tile in found for job in _texture_jobs(export_dir, world, fo4_world, tile)]
    stage_texture(data_dir, *jobs[0])
    with ThreadPoolExecutor() as pool:
        list(pool.map(lambda job: stage_texture(data_dir, *job), jobs[1:]))
    for level, x, y, path in found:
        stem = f'Data\\Textures\\Terrain\\{fo4_world}\\{fo4_world}.{level}.{x}.{y}'
        names = (f'{stem}.dds', f'{stem}_msn.dds')
        made = cached(SITE, __name__, (path.read_bytes(), level, names), lambda: btr(path, level, names))
        (meshes / f'{fo4_world}.{level}.{x}.{y}.btr').write_bytes(made)
    return len(found)
