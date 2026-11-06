"""Object LOD for Fallout 4: the STAT's flag and MNAM, LODGen's reference rows, the atlas packing and map, the
pass's input, the far mesh reduction of strips, and the unattended runner."""

import collections
import struct
import sys
import types
from pathlib import Path

import pytest

from asset_convert.lod.lod_far_gen import generate_far_nif, shapes_from_strips
from asset_convert.lod.lod_gen import LOD16_MIN_SIZE
from core.unattended import run_unattended
from fo4_import.nif import convert_static as S
from fo4_import.nif import file as F
from fo4_import.pipeline import lod_atlas as A
from fo4_import.pipeline import object_lod as P
from fo4_import.spike import cell as C
from fo4_import.spike import object_lod as O
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import first_sub
from pyffi.formats.nif import NifFormat

MEGATON_WALL = Path('export/Fallout3.esm/meshes/architecture/megaton/megatonextwall02dest.nif')


class Builder:
    """The parts of CellBuilder ObjectLod reads."""

    def __init__(self):
        """No meshes, counts empty."""
        self.export_dir, self.data_dir, self.meshes, self.counts = Path('.'), Path('.'), {}, collections.Counter()


def _lod():
    """An ObjectLod with base 0x10 named and the worldspace W being placed."""
    lod = O.ObjectLod(Builder())
    lod.bases[0x10] = 'Base\t00008000\t\tmeshes\\fnv\\a.nif\tmeshes\\fnv\\a_lod.nif\tmeshes\\fnv\\a_lod.nif\t\t'
    lod.begin('W')
    return lod


def test_stat_keeps_the_flag_and_writes_four_260_byte_lod_paths():
    """MNAM is four zero-padded 260-byte paths after DNAM, as all 3,436 of Fallout4.esm's; flags on the record."""
    rec = R.pack_stat(0x800, 'S', 'fnv\\s.nif', (0,) * 6, O.VISIBLE_DISTANT, ('fnv\\s_lod.nif', 'fnv\\s_lod.nif', '', ''))
    assert struct.unpack_from('<I', rec, 8)[0] == 0x8000
    mnam = first_sub(rec[24:], b'MNAM')
    assert len(mnam) == 4 * R.LOD_PATH and mnam[:14] == b'fnv\\s_lod.nif\0' and mnam[2 * R.LOD_PATH] == 0
    assert rec.index(b'MNAM') > rec.index(b'DNAM')


def test_a_static_without_lod_has_no_mnam():
    """No lods: no MNAM, flags 0, as before."""
    rec = R.pack_stat(0x800, 'S', 'fnv\\s.nif', (0,) * 6)
    assert first_sub(rec[24:], b'MNAM') is None and struct.unpack_from('<I', rec, 8)[0] == 0


def test_mnam_levels_follow_size():
    """Levels 4 and 8 always; 16 from LOD16_MIN_SIZE across; never 32."""
    assert O.mnam('m', LOD16_MIN_SIZE - 1) == ('m', 'm', '', '')
    assert O.mnam('m', LOD16_MIN_SIZE) == ('m', 'm', 'm', '')


def test_a_row_is_the_refr_as_written_in_degrees():
    """FormID, flags, position, rotation in degrees, scale, then the base's entry and the empty tail."""
    lod = _lod()
    lod.add(R.pack_refr(0x1234, 0x10, (1.0, 2.0, 3.0), (0.0, 0.0, 3.14159265), 2.0, persistent=False), 0)
    fields = lod.rows[0].split('\t')
    assert fields[:9] == ['00001234', '00000000', '1.0000', '2.0000', '3.0000', '0.0000', '0.0000', '180.0000',
                          '2.0000']
    assert fields[9] == 'Base' and fields[13] == 'meshes\\fnv\\a_lod.nif' and len(fields) == 27


def test_rows_skip_other_bases_disabled_refs_and_refs_outside_a_worldspace():
    """Only bases with LOD; a disabled ref only when FNV flags it Visible When Distant; nothing when no worldspace."""
    lod = _lod()
    lod.add(R.pack_refr(1, 0x11, (0,) * 3, (0,) * 3), 0)
    lod.add(R.pack_refr(2, 0x10, (0,) * 3, (0,) * 3, disabled=True), 0)
    lod.add(R.pack_refr(3, 0x10, (0,) * 3, (0,) * 3, disabled=True), O.VISIBLE_DISTANT)
    assert [row[:8] for row in lod.rows] == ['00000003']
    lod.world = None
    lod.add(R.pack_refr(4, 0x10, (0,) * 3, (0,) * 3), 0)
    assert len(lod.rows) == 1


def test_pack_fits_rows_into_the_smallest_square():
    """Tallest first, left to right; 512 holds four 256s; a 600 texture needs 1024."""
    side, places = A.pack({n: (256, 256) for n in 'abcd'})
    assert side == 512 and sorted(places.values()) == [(0, 0), (0, 256), (256, 0), (256, 256)]
    assert A.pack({'a': (600, 64), 'b': (64, 64)})[0] == 1024
    assert A.pack({n: (512, 512) for n in range(65)}) is None


def test_map_lines_are_xedits_atlas_map():
    """Texture, size, place, atlas path (lowercase, under textures), atlas size."""
    found = {'textures\\fnv\\a.dds': (None, (64, 32), True)}
    line = A.map_lines('FNV_W', found, 512, {'textures\\fnv\\a.dds': (64, 0)})[0]
    assert line == 'textures\\fnv\\a.dds\t64\t32\t64\t0\ttextures\\terrain\\fnv_w\\objects\\fnv_w.objects.dds\t512\t512'


def test_tiles_take_textures_within_the_uv_range_and_size(tmp_path):
    """Our own textures whose UVs stay within 1.5 and that are at most 512 a side."""
    tex = tmp_path / 'textures'
    tex.mkdir()
    for name, side in (('a', 256), ('b', 1024), ('c', 64)):
        (tex / f'{name}.dds').write_bytes(b'DDS ' + struct.pack('<4I', 124, 0, side, side) + bytes(108))
    ranges = {'textures\\fnv\\a.dds': (0.0, 1.0, True), 'textures\\fnv\\b.dds': (0.0, 1.0, True),
              'textures\\fnv\\c.dds': (0.0, 4.0, True), 'textures\\other\\d.dds': (0.0, 1.0, True)}
    assert list(A.tiles(tmp_path, ranges)) == ['textures\\fnv\\a.dds'] and A.tiles(tmp_path, ranges)[
        'textures\\fnv\\a.dds'][2]


def test_the_input_header_is_fo4s(tmp_path):
    """GameMode FO4, the grid from LODSettings, xEdit's FO4 settings, atlas tolerance 0.5, an absolute Data path."""
    (tmp_path / 'LODSettings').mkdir()
    (tmp_path / 'LODSettings' / 'W.lod').write_bytes(struct.pack('<hhIII', -64, -64, 128, 4, 32))
    assert P.lod_settings(tmp_path, 'W') == (-64, -64, 128, 4, 32)
    head = P.header('W', P.lod_settings(tmp_path, 'W')[:2], tmp_path, Path('map.txt'))
    assert head[:3] == ['GameMode=FO4', 'Worldspace=W', 'CellSW=-64 -64'] and 'AtlasTolerance=0.5' in head
    assert head[-2].startswith('PathData=') and head[-2].endswith('\\') and head[-1] == 'TextureAtlasMap=map.txt'
    assert P.lod_settings(tmp_path, 'X') is None


def _tile(*sets: list) -> bytes:
    """A NIF of specular lighting shaders, one per texture set of `sets`."""
    nif = F.NifFile()
    for slots in sets:
        nif.blocks += [('BSLightingShaderProperty', S.lighting_shader(nif, '', len(nif.blocks) + 1, P.SPECULAR)),
                       ('BSShaderTextureSet', {'textures': slots + [''] * (10 - len(slots))})]
    return F.write(nif)


def test_tiles_get_vanillas_specular():
    """An atlas shape without a specular map names the atlas's; its own texture without one turns specular off."""
    atlas = 'Data\\textures\\terrain\\w\\objects\\w.objects.dds'
    nif = F.read(P.with_specular(_tile([atlas, 'n.dds'], ['Data\\Textures\\a.dds'], ['b.dds'] + [''] * 6 + ['b_s.dds'])))
    shaders = [(b['flags1'] & P.SPECULAR, nif.blocks[b['texture_set']][1]['textures'][7])
               for k, b in nif.blocks if k == 'BSLightingShaderProperty']
    assert shaders == [(1, 'Data\\textures\\terrain\\w\\objects\\w.objects_s.dds'), (0, ''), (1, 'b_s.dds')]


def test_only_the_worlds_lod_levels_are_installed_each_with_specular(tmp_path):
    """A world whose LODSettings stop at level 8 gets no level-16 tile, and a kept tile is finished as installed."""
    kept = tmp_path / 'kept'
    kept.mkdir()
    for name in ('FNV_W.4.-10.-8.bto', 'FNV_W.8.-10.-8.bto', 'FNV_W.16.-10.-8.bto'):
        (kept / name).write_bytes(_tile(['Data\\textures\\terrain\\w\\objects\\w.objects.dds']))
    assert P.install(kept, tmp_path, 'FNV_W', (4, 8)) == 2
    installed = sorted((tmp_path / 'Meshes/Terrain/FNV_W/Objects').iterdir())
    assert [p.name for p in installed] == ['FNV_W.4.-10.-8.bto', 'FNV_W.8.-10.-8.bto']
    nif = F.read(installed[0].read_bytes())
    assert nif.blocks[1][1]['textures'][7] == 'Data\\textures\\terrain\\w\\objects\\w.objects_s.dds'


def test_lod_meshes_are_the_rows_lod_columns():
    """Each LOD mesh once, under Meshes; the full model is not one."""
    lod = _lod()
    lod.add(R.pack_refr(1, 0x10, (0,) * 3, (0,) * 3), 0)
    assert P.lod_meshes(lod.rows) == ['fnv\\a_lod.nif']


@pytest.mark.skipif(not MEGATON_WALL.is_file(), reason='needs the Fallout 3 export')
def test_strips_become_shapes_before_reduction(tmp_path):
    """Megaton's walls are all NiTriStrips, which the reducer skips: they become shapes and reduce."""
    data = NifFormat.Data()
    with open(MEGATON_WALL, 'rb') as f:
        data.read(f)
    assert shapes_from_strips(data) == 9
    assert generate_far_nif(MEGATON_WALL, tmp_path / 'far.nif')


def test_unattended_run_is_killed_at_its_timeout():
    """A 60 s child is ended after 1 s, timed out, its output kept."""
    out, _, timed_out = run_unattended([sys.executable, '-c', 'import time; print("hi", flush=True); time.sleep(60)'], 1)
    assert timed_out and out == 'hi'


def test_unattended_run_returns_the_exit_code():
    """A child ending on its own: its code, not timed out."""
    _, code, timed_out = run_unattended([sys.executable, '-c', 'raise SystemExit(3)'], 30)
    assert code == 3 and not timed_out


def test_a_dlc_build_leaves_a_master_worldspace_to_the_masters_lod(monkeypatch):
    """_world_groups: the plugin's own worldspace writes its LOD lists; a master's worldspace writes its group only."""
    log = []
    monkeypatch.setattr(C.terrain_lod, 'write', lambda *args: log.append(('terrain', args[3])) or 1)
    lod = types.SimpleNamespace(begin=lambda w: log.append(('begin', w)), write=lambda d: log.append(('write',)) or 0)
    builder = types.SimpleNamespace(base=lambda fid: None, object_lod=lod, counts=collections.Counter(),
                                    ids=types.SimpleNamespace(is_own=lambda fid: fid >> 24 >= 1),
                                    writer=types.SimpleNamespace(add_raw_group=lambda sig, g: log.append(('group', g))))

    def world(fid: str, edid: str):
        """A built worldspace stand-in."""
        return types.SimpleNamespace(placement_order=list, world={'FormID': fid, 'EditorID': edid}, fo4_edid=edid,
                                     export_dir=None, group=lambda b, *p: edid)
    C._world_groups(builder, [world('000DA726', 'Mojave'), world('01000800', 'Zion')], (None, None))
    assert log == [('group', 'Mojave'), ('begin', 'Zion'), ('group', 'Zion'), ('write',), ('terrain', 'Zion')]
    assert builder.counts["master worldspaces left to the master's LOD"] == 1
