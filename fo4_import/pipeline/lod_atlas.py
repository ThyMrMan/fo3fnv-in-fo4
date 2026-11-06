"""A worldspace's object LOD texture atlas: the diffuse, normal and specular maps of its LOD meshes' textures packed
into one image each, and the map file LODGenx64 reads to move each texture's UVs onto it.

The textures are the diffuses the converted LOD meshes' shapes name, whose
UVs stay within UV_RANGE and that are at most TILE_MAX texels a side, as
xEdit picks them; each is read from FNV's own file (the reverse of
fo4_texture), its normal map beside it, its specular map made from that
where the shapes name one, else black (the converter turned specular off).

See: docs/fork/fo4_pipeline.md#lod-atlas
"""

import functools
import io
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.texture.dds_codec import normal_dds
from asset_convert.texture.image_transcode import encode_dds
from fo4_import.base.ba2_pack import stage_texture
from fo4_import.nif import file as F
from fo4_import.nif.convert_static import GLOSSINESS, PREFIX, SLOT_SPECULAR, smoothness, spec_image
from fo4_import.pipeline.export_index import export_file
from fo4_import.pipeline.work_cache import signature

#: UVs a texture's shapes may reach and still go on the atlas (xEdit's AtlasTextureUVRange; AtlasTolerance is 0.5).
UV_RANGE = 1.5
#: Largest texture side the atlas takes (xEdit's AtlasTextureSize); bigger ones keep their own file.
TILE_MAX = 512
#: Atlas sides tried, smallest first (square: normal_dds packs squares; vanilla Diamond City's is 2048).
SIDES = (512, 1024, 2048, 4096)
#: A flat tangent-space normal, for a texture with no normal map.
FLAT_NORMAL = (128, 128, 255, 0)
#: The three atlas maps: file suffix and the work cache's site.
MAPS = (('', 'lod_atlas_diffuse'), ('_n', 'lod_atlas_normal'), ('_s', 'lod_atlas_specular'))


def atlas_path(world: str, suffix: str = '') -> str:
    """Atlas map `suffix` ('', '_n', '_s') of FO4 worldspace `world`, under Textures."""
    return f'Terrain\\{world}\\Objects\\{world}.Objects{suffix}.dds'


def shape_textures(nif) -> list:
    """[(diffuse path, UV array, names a specular map)] of a FO4 NIF's lit shapes that name a texture set."""
    blocks, out = nif.blocks, []
    for kind, block in blocks:
        if kind != 'BSTriShape' or isinstance(block, bytes) or block['shader'] < 0:
            continue
        shader = blocks[block['shader']][1]
        if isinstance(shader, bytes) or shader.get('texture_set', -1) < 0:
            continue
        slots = blocks[shader['texture_set']][1]['textures']
        diffuse = slots[0].lower()
        uvs = np.array([v['uv'] for v in block['vertices'] if 'uv' in v], dtype=np.float32).reshape(-1, 2)
        if diffuse and len(uvs):
            out.append((diffuse, uvs, bool(slots[SLOT_SPECULAR])))
    return out


def uv_ranges(data_dir: Path, meshes: list) -> dict:
    """{diffuse path: (lowest, highest UV, any names a specular map)} over the shapes of LOD meshes `meshes`
    (paths under Meshes)."""
    out = {}
    for mesh in meshes:
        path = Path(data_dir) / 'Meshes' / mesh
        for diffuse, uvs, specular in shape_textures(F.read(path.read_bytes())) if path.is_file() else ():
            low, high, spec = out.get(diffuse, (np.inf, -np.inf, False))
            out[diffuse] = (min(low, float(uvs.min())), max(high, float(uvs.max())), spec or specular)
    return out


def fnv_texture(export_dir: Path, fo4_path: str) -> 'Path | None':
    """FNV's file of FO4 texture path `fo4_path` (textures\\fnv\\...); None when it is not ours or missing."""
    parts = fo4_path.lower().split('\\')
    if parts[:2] != ['textures', PREFIX]:
        return None
    found = export_file(export_dir, 'textures', *parts[2:])
    return found if found.is_file() else None


def dds_size(path: Path) -> tuple:
    """(width, height) from a DDS header."""
    with open(path, 'rb') as f:
        height, width = struct.unpack('<12x2I', f.read(20))
    return width, height


def tiles(export_dir: Path, ranges: dict) -> dict:
    """{diffuse path: (FNV diffuse file, (width, height), specular)} of the textures the atlas takes (module
    notes)."""
    out = {}
    for diffuse, (low, high, specular) in sorted(ranges.items()):
        source = fnv_texture(export_dir, diffuse)
        if source is None or low < -UV_RANGE or high > UV_RANGE:
            continue
        size = dds_size(source)
        if max(size) <= TILE_MAX:
            out[diffuse] = (source, size, specular)
    return out


def pack(sizes: dict) -> 'tuple | None':
    """(side, {name: (x, y)}): `sizes` {name: (width, height)} placed in rows, tallest first, in the smallest SIDES
    square they fit; None when even the largest is too small."""
    order = sorted(sizes, key=lambda n: (-sizes[n][1], -sizes[n][0], n))
    for side in SIDES:
        places, x, y, row = {}, 0, 0, 0
        for name in order:
            width, height = sizes[name]
            if x + width > side:
                x, y, row = 0, y + row, 0
            if y + height > side or width > side:
                break
            places[name], x, row = (x, y), x + width, max(row, height)
        if len(places) == len(order):
            return side, places
    return None


def _normal_file(diffuse: Path) -> 'Path | None':
    """The FNV normal map beside `diffuse` (<stem>_n.dds), if any."""
    found = diffuse.with_name(f'{diffuse.stem}_n.dds')
    return found if found.is_file() else None


def _images(source: Path, specular: bool) -> tuple:
    """(diffuse RGBA, normal RGB, specular RGB) arrays of one FNV texture, the normal and specular at its size;
    the specular black unless `specular`."""
    diffuse = Image.open(source).convert('RGBA')
    normal_file, black = _normal_file(source), np.zeros((diffuse.height, diffuse.width, 3), np.uint8)
    if normal_file is None:
        flat = np.broadcast_to(np.array(FLAT_NORMAL, np.uint8), (diffuse.height, diffuse.width, 4))
        return np.asarray(diffuse), flat[:, :, :3], black
    normal = Image.open(normal_file).convert('RGBA').resize(diffuse.size, Image.LANCZOS)
    buffer = io.BytesIO()
    normal.save(buffer, 'PNG')
    spec = spec_image(buffer.getvalue(), smoothness(GLOSSINESS)) if specular else black
    return np.asarray(diffuse), np.asarray(normal)[:, :, :3], spec


def compose(found: dict, side: int, places: dict) -> tuple:
    """(diffuse, normal, specular DDS bytes) of the atlas: each texture of `found` (tiles()) at its place."""
    sheets = [np.zeros((side, side, 4), np.uint8), np.zeros((side, side, 3), np.uint8),
              np.zeros((side, side, 3), np.uint8)]
    sheets[1][:] = FLAT_NORMAL[:3]
    for name, (x, y) in places.items():
        for sheet, image in zip(sheets, _images(found[name][0], found[name][2])):
            sheet[y:y + image.shape[0], x:x + image.shape[1]] = image
    return encode_dds(Image.fromarray(sheets[0], 'RGBA')), normal_dds(sheets[1]), normal_dds(sheets[2])


def map_lines(world: str, found: dict, side: int, places: dict) -> list:
    """LODGen's atlas map lines: texture, size, place, atlas path, atlas size."""
    atlas = f'textures\\{atlas_path(world)}'.lower()
    return [f'{name}\t{w}\t{h}\t{places[name][0]}\t{places[name][1]}\t{atlas}\t{side}\t{side}'
            for name, (_, (w, h), _) in sorted(found.items())]


def _inputs(found: dict, side: int, places: dict) -> tuple:
    """Work-cache inputs: side; per texture place, specular, diffuse, normal bytes."""
    normals = {name: _normal_file(source) for name, (source, *_) in found.items()}
    return side, tuple((name, places[name], found[name][2], found[name][0].read_bytes(),
                        normals[name].read_bytes() if normals[name] else b'') for name in sorted(places))


def _plan(site: str, inputs: tuple, make) -> tuple:
    """stage_texture's (signature, writer) of work-cached `make`."""
    sign, get = signature(site, __name__, inputs, make)
    return sign, lambda target: target.write_bytes(get())


def build(export_dir: Path, data_dir: Path, world: str, meshes: list) -> list:
    """Stage FO4 worldspace `world`'s atlas for LOD meshes `meshes` into `data_dir`'s texture archive, work-cached;
    the atlas map lines ([] when no texture qualifies)."""
    found = tiles(export_dir, uv_ranges(data_dir, meshes))
    packed = pack({name: size for name, (_, size, _) in found.items()}) if found else None
    if packed is None:
        return []
    inputs, made = _inputs(found, *packed), functools.cache(functools.partial(compose, found, *packed))
    for index, (suffix, site) in enumerate(MAPS):
        make = functools.partial(lambda i: made()[i], index)
        stage_texture(data_dir, atlas_path(world, suffix), functools.partial(_plan, site, inputs, make))
    return map_lines(world, found, *packed)
