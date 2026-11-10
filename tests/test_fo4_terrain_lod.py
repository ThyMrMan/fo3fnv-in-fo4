"""FNV's prebuilt terrain LOD as FO4's: the LOD settings file and a converted tile."""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.nif import file as F
from fo4_import.nif.blocks import Reader, read_tri_shape
from fo4_import.spike import terrain_lod as T

TILE = Path('export/FalloutNV.esm/meshes/landscape/lod/wastelandnv/wastelandnv.level16.x0.y0.nif')
#: The Lake Mead tile west of The Fort: water 3,825 vertices with its skirts, land 1,773.
LAKE_MEAD = TILE.with_name('wastelandnv.level4.x28.y12.nif')
#: Vanilla Commonwealth level-4 tile blocks after the land's texture set (commonwealth.4.-12.-12.btr).
WATER_NODE = ['BSMultiBoundNode', 'BSSubIndexTriShape', 'BSEffectShaderProperty', 'BSMultiBound', 'BSMultiBoundAABB',
              'BSMultiBound', 'BSMultiBoundAABB']


def test_lod_settings_name_the_grid_from_the_top_level_tiles():
    """South-west cell and size come from the highest level's tiles; levels 4 to it."""
    found = [(32, x, y, None) for x in (-64, -32, 0, 32) for y in (-64, -32, 0, 32)] + [(4, -64, -64, None)]
    assert struct.unpack('<hhIII', T.lod_settings(found)) == (-64, -64, 128, 4, 32)


def test_lod_settings_round_the_grid_to_a_power_of_two_top_tiles_across():
    """Freeside's 3 level-8 tiles across give a 32-cell grid (4 across), as vanilla's 8 or 1; Freeside's 24 crashed."""
    found = [(8, x, y, None) for x in (-10, -2, 6) for y in (-8, 0, 8)]
    assert struct.unpack('<hhIII', T.lod_settings(found)) == (-10, -8, 32, 4, 8)


def test_a_tile_missing_a_texture_is_left_out(tmp_path):
    """Lucky38World ships tile meshes with no textures: a tile counts only with both its diffuse and normals."""
    meshes, textures = tmp_path / 'meshes/landscape/lod/w', tmp_path / 'textures/landscape/lod/w'
    for kind in ('diffuse', 'normals'):
        (textures / kind).mkdir(parents=True)
    meshes.mkdir(parents=True)
    for x in (0, 4):
        (meshes / f'w.level4.x{x}.y0.nif').write_bytes(b'')
    for kind in ('diffuse', 'normals'):
        (textures / kind / 'w.n.level4.x0.y0.dds').write_bytes(b'')
    (textures / 'diffuse' / 'w.n.level4.x4.y0.dds').write_bytes(b'')
    assert [(level, x, y) for level, x, y, _ in T.tiles(tmp_path, 'W')] == [(4, 0, 0)]


@pytest.mark.skipif(not TILE.exists(), reason='needs the FalloutNV.esm export')
def test_a_tile_becomes_one_scaled_land_shape_facing_up():
    """The land shape is scaled by its level with positions in tile units, drops the strips' zero-area stitches,
    faces up like vanilla's (over 90%), lays UVs out as vanilla (u = x, v = 1 - y) and names its two textures."""
    nif = F.read(T.btr(TILE, 16, ('d.dds', 'n_msn.dds')))
    assert [k for k, _ in nif.blocks] == ['BSMultiBoundNode', 'BSTriShape', 'BSLightingShaderProperty',
                                          'BSShaderTextureSet', WATER_NODE[0], 'BSTriShape', *WATER_NODE[2:]]
    shape = nif.blocks[1][1]
    pos = np.array([v['position'] for v in shape['vertices']], float)
    tris = np.array(shape['triangles'])
    normal = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    assert shape['scale'] == 16.0 and pos[:, :2].min() == 0 and pos[:, :2].max() == 4096
    assert np.linalg.norm(normal, axis=1).min() > 0 and (normal[:, 2] > 0).mean() > 0.9
    uv = np.array([v['uv'] for v in shape['vertices']], float)
    assert np.abs(uv - np.stack([pos[:, 0] / 4096, 1 - pos[:, 1] / 4096], axis=1)).max() < 1e-3
    assert nif.blocks[2][1]['shader_type'] == 18 and nif.blocks[3][1]['textures'][:2] == ['d.dds', 'n_msn.dds']


def test_segments_trailer_is_vanilla_s():
    """16 segments, start index 3 x the first triangle, an empty segment at 0, no parent (commonwealth.4.-12.-16)."""
    counts = np.zeros(16, int)
    counts[[3, 7, 8]] = 2
    trailer = T.segments(counts)
    assert struct.unpack_from('<3I', trailer) == (6, 16, 16) and len(trailer) == 12 + 16 * 16
    rows = [struct.unpack_from('<4I', trailer, 12 + 16 * j) for j in range(16)]
    assert rows[3] == (0, 2, T.NO_PARENT, 0) and rows[7] == (6, 2, T.NO_PARENT, 0) and rows[8][:2] == (12, 2)
    assert rows[0] == (0, 0, T.NO_PARENT, 0)


def test_by_cell_orders_triangles_by_the_cell_holding_their_centre():
    """Segment x * 4 + y of the level-4 tile's 4 x 4 cells (1,024 tile units each); edges clamp to the tile."""
    local = np.array([(0, 0, 0), (10, 0, 0), (0, 10, 0), (3000, 1100, 0), (3010, 1100, 0), (3000, 1110, 0),
                      (4100, 4100, 0), (4110, 4100, 0), (4100, 4110, 0)], float)
    tris, counts = T.by_cell(local, np.array([[6, 7, 8], [3, 4, 5], [0, 1, 2]]), 4)
    assert tris.tolist() == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    assert np.nonzero(counts)[0].tolist() == [0, 2 * 4 + 1, 15]


@pytest.mark.skipif(not LAKE_MEAD.exists(), reason='needs the FalloutNV.esm export')
def test_lake_mead_tile_carries_land_and_vanilla_s_water_node():
    """Land, then the WATER node laid out as vanilla's: half-float positions only, flat at Lake Mead's 2600 with the
    skirts gone, vanilla's effect shader, cut into 16 cell segments each holding only its cell's triangles."""
    nif = F.read(T.btr(LAKE_MEAD, 4, ('d.dds', 'n_msn.dds')))
    assert [k for k, _ in nif.blocks][4:] == WATER_NODE and nif.strings == ['chunk', 'Land', '', 'WATER']
    assert nif.blocks[0][1][-20:] == struct.pack('<5I', 2, 1, 4, 9, 1)
    assert nif.blocks[4][1][-16:] == struct.pack('<4I', 1, 5, 7, 1)
    reader = Reader(nif.blocks[5][1])
    shape = read_tri_shape(reader)
    trailer = nif.blocks[5][1][reader.pos:]
    pos = np.array([v['position'] for v in shape['vertices']], float)
    assert shape['vertex_desc'] == T.WATER_DESC and shape['scale'] == 4.0 and shape['shader'] == 6
    assert set(pos[:, 2] * 4) == {2600.0}
    assert nif.blocks[6][1] == T.WATER_SHADER
    tris = np.array(shape['triangles'])
    assert struct.unpack_from('<3I', trailer) == (len(tris), 16, 16)
    for j in range(16):
        start, count = struct.unpack_from('<2I', trailer, 12 + 16 * j)
        centre = pos[tris[start // 3:start // 3 + count]].mean(axis=1)
        assert (np.clip(centre[:, :2] // 1024, 0, 3) == (j // 4, j % 4)).all()
    assert struct.unpack('<6f', nif.blocks[8][1])[2::3] == (2600.0, 0.0)
