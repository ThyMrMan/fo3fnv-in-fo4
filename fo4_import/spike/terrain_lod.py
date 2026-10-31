"""FNV's prebuilt terrain LOD as Fallout 4's.

Each FNV tile (meshes/landscape/lod/<world>/<world>.level<L>.x<X>.y<Y>.nif,
named by its south-west cell) becomes Meshes/Terrain/<FO4 world>/<FO4 world>.<L>.<X>.<Y>.btr:
one land shape scaled by the level, positions in tile units (world / level).
FNV lays its tile textures out mirrored on both axes (u = 1 - x, v = y),
FO4 as u = x, v = 1 - y, and reads a tile's normal map by name; both
textures turn half a turn and the UVs follow. The normal map is model space
in both games, FNV's x, y, z in RGB and FO4's x, z, y, so green and blue swap.
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
from fo4_import.nif.blocks import SHADER_LOD_LAND
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
    """The LODSettings file of tiles `found` (tiles()): south-west cell, size in cells, lowest and highest level."""
    top = max(level for level, *_ in found)
    xs, ys = [x for level, x, _, _ in found if level == top], [y for level, _, y, _ in found if level == top]
    size = max(max(xs) - min(xs), max(ys) - min(ys)) + top
    return struct.pack('<hhIII', min(xs), min(ys), size, MIN_LEVEL, top)


def land_shape(path: Path) -> tuple:
    """(positions, uvs, triangles) as arrays of the FNV tile at `path`'s land: its shaded shape (the other, a
    BSSegmentedTriShape with no properties, is the tile's LOD water).
    See: docs/fork/fo4_pipeline.md#terrain-lod
    """
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    land = next(b for b in data.blocks if isinstance(b, NifFormat.NiTriShape)
                and any(isinstance(p, NifFormat.BSShaderPPLightingProperty) for p in b.get_properties()))
    shape = land.data
    return (np.array([(v.x, v.y, v.z) for v in shape.vertices], float),
            np.array([(t.u, t.v) for t in shape.uv_sets[0]], float),
            np.array([(t.v_1, t.v_2, t.v_3) for t in shape.triangles], int))


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


def _multi_bound_node(child: int, bound: int) -> bytes:
    """A BSMultiBoundNode named 'chunk' (string 0) holding `child`, its multi-bound `bound`, culling 1."""
    head = F.BLOCKS['NiNode'][1]({'name': 0, 'extra': [], 'controller': -1, 'flags': FLAGS,
                                  'translation': (0.0, 0.0, 0.0), 'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
                                  'scale': 1.0, 'collision': -1, 'children': [child]})
    return head + struct.pack('<iI', bound, 1)


def btr(path: Path, level: int, textures: tuple) -> bytes:
    """The .btr of the FNV tile at `path` of `level`, textured by (diffuse, normal) Data paths."""
    pos, uv, tris = land_shape(path)
    local, tris = tile_units(pos, without_skirts(pos, tris), level)
    uv = 1 - uv
    lo, hi = local.min(axis=0), local.max(axis=0)
    centre, half = (lo + hi) / 2, (hi - lo) / 2
    nif = F.NifFile(strings=['chunk', 'Land', ''])
    shape = {'name': 1, 'extra': [], 'controller': -1, 'flags': FLAGS, 'translation': (0.0, 0.0, 0.0),
             'rotation': (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), 'scale': float(level), 'collision': -1,
             'bound': (*centre, float(np.linalg.norm(half))), 'skin': -1, 'shader': 2, 'alpha_property': -1,
             'vertex_desc': VERTEX_DESC, 'triangles': [tuple(map(int, t)) for t in tris],
             'vertices': [{'position': tuple(p), 'bitangent_x': 0, 'uv': tuple(t)} for p, t in zip(local, uv)]}
    nif.blocks = [('BSMultiBoundNode', _multi_bound_node(1, 4)), ('BSTriShape', shape),
                  ('BSLightingShaderProperty', {**SHADER, 'shader_type': SHADER_LOD_LAND, 'name': 2, 'texture_set': 3,
                                                'root_material': 2}),
                  ('BSShaderTextureSet', {'textures': [*textures] + [''] * 8}),
                  ('BSMultiBound', struct.pack('<i', 5)),
                  ('BSMultiBoundAABB', struct.pack('<6f', *(centre * level), *(half * level)))]
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
