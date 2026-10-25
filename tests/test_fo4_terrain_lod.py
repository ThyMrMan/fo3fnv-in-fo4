"""FNV's prebuilt terrain LOD as FO4's: the LOD settings file and a converted tile."""

import struct
from pathlib import Path

import numpy as np
import pytest

from fo4_import.nif import file as F
from fo4_import.spike import terrain_lod as T

TILE = Path('export/FalloutNV.esm/meshes/landscape/lod/wastelandnv/wastelandnv.level16.x0.y0.nif')


def test_lod_settings_name_the_grid_from_the_top_level_tiles():
    """South-west cell and size come from the highest level's tiles; levels 4 to it."""
    found = [(32, x, y, None) for x in (-64, -32, 0, 32) for y in (-64, -32, 0, 32)] + [(4, -64, -64, None)]
    assert struct.unpack('<hhIII', T.lod_settings(found)) == (-64, -64, 128, 4, 32)


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
                                          'BSShaderTextureSet', 'BSMultiBound', 'BSMultiBoundAABB']
    shape = nif.blocks[1][1]
    pos = np.array([v['position'] for v in shape['vertices']], float)
    tris = np.array(shape['triangles'])
    normal = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    assert shape['scale'] == 16.0 and pos[:, :2].min() == 0 and pos[:, :2].max() == 4096
    assert np.linalg.norm(normal, axis=1).min() > 0 and (normal[:, 2] > 0).mean() > 0.9
    uv = np.array([v['uv'] for v in shape['vertices']], float)
    assert np.abs(uv - np.stack([pos[:, 0] / 4096, 1 - pos[:, 1] / 4096], axis=1)).max() < 1e-3
    assert nif.blocks[2][1]['shader_type'] == 18 and nif.blocks[3][1]['textures'][:2] == ['d.dds', 'n_msn.dds']
