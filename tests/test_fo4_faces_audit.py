"""Faces, FaceGen, voice, vendors and unbuilt creatures after the converter audit's speed and drop findings.

See: docs/fork/fo4_tool_audit.md#first-build
See: docs/fork/fo4_tool_audit.md#rebuild
"""

import collections
import pickle
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.writer import pack_fo4_header, pack_fo4_record
from fo4_import.face import memo
from fo4_import.face import texture as TX
from fo4_import.face.bake import align, surface
from fo4_import.face.fnv_head import FnvHead, head
from fo4_import.pipeline import work_cache
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import facegen as FG
from fo4_import.spike import npcs as N
from fo4_import.spike import vendors as VE
from fo4_import.spike import voice as V
from fo4_import.spike.creatures import Creatures
from tes5_import.base.writer import pack_group, pack_subrecord

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'


def _plugin(*records: tuple) -> bytes:
    """Plugin bytes holding `records` [(signature, FormID, subrecords)], a top group per signature."""
    groups = collections.defaultdict(bytes)
    for sig, fid, subs in records:
        groups[sig] += pack_fo4_record(sig, fid, 0, subs)
    return pack_fo4_header([], len(records), 0x800, 0, 'test') + b''.join(
        pack_group(0, sig.encode(), body) for sig, body in groups.items())


def _grid(n: int, scale: float, lift: float) -> tuple:
    """(points, UVs inside 0.2..0.8, triangles) of an n x n grid bulging toward +y, scaled and raised by `lift`."""
    x, z = (a.ravel() for a in np.meshgrid(np.linspace(-1, 1, n), np.linspace(-1, 1, n)))
    points = np.column_stack([x, 1 - 0.2 * (x ** 2 + z ** 2) + lift, z]) * scale
    uvs = 0.2 + 0.6 * np.column_stack([(x + 1) / 2, (1 - z) / 2])
    quads = [(r * n + c, r * n + c + 1, (r + 1) * n + c + 1, (r + 1) * n + c) for r in range(n - 1) for c in range(n - 1)]
    return points, uvs, np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])


def _old_face_texture(fo4_rgba, fo4: tuple, fnv: FnvHead, pieces: tuple, variant: str) -> tuple:
    """face_texture as it was before texel_map: the mapping per call, the padding from the filled texel mask."""
    points, uv, tris = fo4
    fnv_surface = surface(fnv.mean, fnv.triangles)
    s, r, t = align(points, fnv.mean, fnv_surface)
    rows, cols, where = TX.texel_points(points, uv, tris, fo4_rgba.shape[0])
    _, idx = cKDTree(fnv_surface[0]).query(s * where @ r.T + t)
    _, owner, bary = fnv_surface
    fnv_uv = (bary[idx][:, :, None] * fnv.uvs[fnv.triangles[owner[idx]]]).sum(1)
    colours = TX.bilinear(pieces[1] if variant == 'T1' else pieces[0] + pieces[1], fnv_uv)
    out = fo4_rgba.astype(float)
    fo4_median = np.median(out[rows, cols, :3], 0)
    out[rows, cols, :3] = colours + (out[rows, cols, :3] if variant == 'T1' else 0.0)
    tone = np.median(out[rows, cols, :3], 0) / fo4_median
    out[rows, cols, :3] /= tone
    filled = np.zeros(fo4_rgba.shape[:2], bool)
    filled[rows, cols] = True
    dist, (near_r, near_c) = distance_transform_edt(~filled, return_indices=True)
    pad = (dist > 0) & (dist <= TX.ISLAND_PADDING)
    out[pad, :3] = out[near_r[pad], near_c[pad], :3]
    return np.clip(out, 0, 255).astype(np.uint8), tone


def _npcs(records: dict, lists: dict = None, creatures: dict = None) -> N.Npcs:
    """An Npcs over FNV records {FormID: record}, with a counting builder and no Fallout4.esm."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records, npcs.lists, npcs.made = records, lists or {}, {}
    npcs.creatures = Creatures.__new__(Creatures)
    npcs.creatures.records = creatures or {}
    npcs.races = {0x19: 'Caucasian', 0x3B3E: 'Ghoul'}
    npcs.builder = SimpleNamespace(counts=collections.Counter())
    npcs.export_dir, npcs.assets = EXPORT, None
    return npcs


def _rec(fid: int, **fields) -> dict:
    """A human FNV NPC record with FormID `fid` and `fields`."""
    return {'FormID': f'{fid:08X}', 'EditorID': f'Npc{fid:X}', 'RNAM.Race': '00000019', **fields}


def _fail(*args):
    """Stands in for a fit that must not run."""
    raise AssertionError('fitted again')


def test_skin_tone_layers_come_from_the_bytes_given():
    """HumanRace's Skin Tone options, from the ESM bytes passed."""
    teti = [pack_subrecord('TETI', struct.pack('<HH', slot, index)) for slot, index in ((12, 5), (3, 6), (12, 9))]
    other = pack_subrecord('TETI', struct.pack('<HH', 12, 7))
    assert FG.skin_tone_layers(_plugin(('RACE', FG.HUMAN_RACE, b''.join(teti)), ('RACE', 0x1234, other))) == {5, 9}


def test_by_content_keeps_results_by_contents_read_only():
    """Equal contents give the kept, read-only result; new contents recompute; the oldest past KEPT is dropped."""
    calls = []

    @memo.by_content
    def doubled(values):
        """Two times `values`, counted."""
        calls.append(1)
        return values * 2
    first = doubled(np.arange(3))
    assert doubled(np.arange(3)) is first and len(calls) == 1
    with pytest.raises(ValueError):
        first[0] = 5
    for i in range(memo.KEPT):
        doubled(np.arange(3) + i + 1)
    doubled(np.arange(3))
    assert len(calls) == memo.KEPT + 2


def test_face_texture_is_unchanged_by_the_shared_texel_map():
    """face_texture, mapping kept or not, is byte for byte what the per-call mapping and mask padding gave."""
    rng = np.random.default_rng(0)
    fo4 = _grid(9, 1.0, 0.0)
    fnv_points, fnv_uvs, fnv_tris = _grid(7, 1.1, 0.1)
    fnv = FnvHead(fnv_points, fnv_tris, fnv_points, fnv_uvs)
    rgba = rng.integers(1, 256, (64, 64, 4), dtype=np.uint8)
    pieces = (rng.uniform(0, 200, (32, 32, 3)), rng.uniform(-20, 20, (32, 32, 3)))
    for variant in ('T1', 'T2', 'T1'):
        new, old = TX.face_texture(rgba, fo4, fnv, pieces, variant), _old_face_texture(rgba, fo4, fnv, pieces, variant)
        assert new[0].tobytes() == old[0].tobytes() and new[1].tobytes() == old[1].tobytes()
    assert not TX.texel_map(fo4, (fnv.mean, fnv.triangles, fnv.uvs), (64, 64))[2].flags.writeable


@pytest.mark.skipif(not (EXPORT / 'meshes' / 'characters' / 'head' / 'headhuman.nif').exists(),
                    reason='needs the FNV export')
def test_fnv_head_mesh_is_read_once():
    """Two NPCs on one head mesh share its read-only mean; each gets its own face."""
    one, two = (head(EXPORT / 'meshes', 'Characters\\Head\\HeadHuman.NIF', '', '') for _ in range(2))
    assert one.mean is two.mean and not one.mean.flags.writeable and one.npc is not two.npc
    assert np.array_equal(one.npc, one.mean)


def test_faces_follow_templates_and_lists(monkeypatch):
    """The faces warm_faces fits: an NPC's own, its traits template's, a leveled list entry's; no ghoul's."""
    monkeypatch.setattr(N, 'bases', lambda female: (b'sculpt', b'tint'))
    records = {1: _rec(1), 2: _rec(2, **{'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000003'}),
               3: _rec(3, **{'ACBS.Flags': '1'}), 4: _rec(4, **{'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000010'}),
               5: _rec(5), 6: _rec(6, **{'RNAM.Race': '00003B3E'})}
    lists = {0x10: {'FormID': '00000010', 'EntryCount': '1', 'Entry[0].Level': '1', 'Entry[0].FormID': '00000005',
                    'Entry[0].Count': '1'}}
    faces = _npcs(records, lists)._faces([1, 2, 4, 6])
    assert {fid: female for fid, (_, female) in faces.items()} == {1: False, 3: True, 5: False}


@pytest.mark.skipif(not (EXPORT / 'NPC_.txt').exists() or not FALLOUT4_ESM.exists()
                    or not N.tint.basis_path(True).exists(), reason='needs the FNV export, Fallout4.esm and the bases')
def test_warm_faces_stores_what_the_serial_fit_makes(monkeypatch, tmp_path):
    """A face fitted in a worker process is stored as base()'s serial fit makes it, byte for byte (even when the
    build has pinned child processes to one BLAS thread), and the serial pass then only reads it."""
    npcs = _npcs({int(r['FormID'], 16): r for r in export_records(EXPORT, 'NPC_')})
    npcs.builder.fo4 = FALLOUT4_ESM.read_bytes()
    npc = next(r for r in npcs.records.values() if r.get('EditorID') == 'PrimmNCRTrooper1')
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'serial')
    N.fit_face(EXPORT, npc, False, npcs._head_assets())
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'pool')
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    assert npcs.warm_faces([int(npc['FormID'], 16)], workers=1) == 1
    assert npcs.warm_faces([int(npc['FormID'], 16)], workers=1) == 0
    for name in ('sculpt_fit', 'tint_fit', 'choose'):
        monkeypatch.setattr(N, name, _fail)
    pooled = pickle.dumps(N.fit_face(EXPORT, npc, False, npcs.assets))
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'serial')
    assert pooled == pickle.dumps(N.fit_face(EXPORT, npc, False, npcs.assets))


def test_ck_timeout_scales_with_the_plugins_npcs(tmp_path):
    """The CK gets CK_FACE_SECONDS per NPC_ record in the plugin, never under the CK_TIMEOUT floor."""
    plugin = tmp_path / 'Faces.esp'
    plugin.write_bytes(_plugin(*[('NPC_', 0x800 + i, b'') for i in range(3)], ('RACE', 0x900, b'')))
    assert FG.npc_count(plugin) == 3
    assert FG.ck_timeout(3) == FG.CK_TIMEOUT
    assert FG.ck_timeout(2247) == 2247 * FG.CK_FACE_SECONDS > FG.CK_TIMEOUT


def test_prune_keeps_only_faces_of_the_plugins_npcs_from_the_last_export(tmp_path):
    """A FaceGeom NIF of an NPC_ the plugin dropped goes with its textures; a texture an older export left (no NIF)
    goes, loose or staged; a current NPC_'s face stays."""
    geom, loose = (tmp_path / folder / 'Spike.esp' for folder in FG.FACEGEN_DIRS)
    staged = tmp_path / FG.STAGING / FG.FACEGEN_DIRS[1] / 'Spike.esp'
    for folder in (geom, loose, staged):
        folder.mkdir(parents=True)
    for stem in ('00000801', '00000802'):
        (geom / f'{stem}.NIF').write_bytes(b'nif')
    for folder, stem in ((loose, '00000801'), (staged, '00000801'), (staged, '00000802'), (staged, '00000803')):
        (folder / f'{stem}_d.dds').write_bytes(b'dds')
    assert FG.prune('Spike.esp', tmp_path, [0x03000801]) == 3
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file()) == sorted(
        p.relative_to(tmp_path).as_posix() for p in (geom / '00000801.NIF', loose / '00000801_d.dds',
                                                     staged / '00000801_d.dds'))


def _dds_shape(data: bytes) -> tuple:
    """(width, mip count, fourcc) of a DDS."""
    height, width, _, _, mips = struct.unpack_from('<IIIII', data, 12)
    return width, mips, data[84:88]


@pytest.mark.skipif(not TX.TEXCONV.exists(), reason="needs the CK's texconv")
def test_face_textures_become_vanilla_sizes_with_mips(tmp_path):
    """_d and _msn become 1024 BC1 with 11 mips, _s 512 BC5 with 10; another suffix is left alone."""
    rgba = np.random.default_rng(0).integers(0, 256, (256, 256, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    folder = tmp_path / FG.FACEGEN_DIRS[1] / 'Faces.esp'
    folder.mkdir(parents=True)
    for suffix in ('d', 'msn', 's'):
        TX.write_dds(rgba, folder / f'00000800_{suffix}.dds')
    shutil.copyfile(folder / '00000800_d.dds', folder / '00000800_x.dds')
    assert FG.vanilla_textures('Faces.esp', tmp_path) == 3
    assert {p.stem: _dds_shape(p.read_bytes()) for p in folder.glob('*.dds')} == {
        '00000800_d': (1024, 11, b'DXT1'), '00000800_msn': (1024, 11, b'DXT1'), '00000800_s': (512, 10, b'BC5U'),
        '00000800_x': (256, 1, b'DXT5')}


def _fake_tools(monkeypatch, write):
    """Replace the converter with `write(dest)` (counted) and ffmpeg's lookup; the call list."""
    calls = []

    def convert(source, dest, ffmpeg, xwma, lipgen, text):
        """A counted conversion through `write`."""
        calls.append((source, text))
        return write(Path(dest), len(calls))
    monkeypatch.setattr(V, 'convert_file_to_xwm', convert)
    monkeypatch.setattr(V, 'find_ffmpeg', lambda need_decoder: 'ffmpeg')
    return calls


def _write(path: Path, data: bytes) -> bool:
    """Write `data` to `path`, its folder made; True."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def test_voice_converts_each_recording_and_transcript_once(monkeypatch, tmp_path):
    """Jobs sharing a recording and transcript convert once and share its file; a copy's stale .xwm goes."""
    calls = _fake_tools(monkeypatch, lambda dest, n: _write(dest, b'converted %d' % n))
    src = tmp_path / 'line.ogg'
    shared = [tmp_path / 'A' / '1_1.fuz', tmp_path / 'B' / '1_1.fuz', tmp_path / 'C' / '2_1.fuz']
    _write(tmp_path / 'B' / '1_1.xwm', b'stale')
    jobs = [(src, dest, 'Hi') for dest in shared] + [(src, tmp_path / 'A' / '3_1.fuz', 'Bye'),
                                                   (src, tmp_path / 'A' / '4_1.xwm', None)]
    assert V.convert(jobs, tmp_path) == 5
    assert len(calls) == 3
    assert len({p.read_bytes() for p in shared}) == 1 and not (tmp_path / 'B' / '1_1.xwm').exists()


def test_voice_copies_the_audio_left_when_lips_fail(monkeypatch, tmp_path):
    """When the lips fail, the .xwm left beside the first .fuz is copied beside the others; none counts."""
    _fake_tools(monkeypatch, lambda dest, n: _write(dest.with_suffix('.xwm'), b'audio'))
    src = tmp_path / 'line.ogg'
    jobs = [(src, tmp_path / 'A' / '1_1.fuz', 'Hi'), (src, tmp_path / 'B' / '1_1.fuz', 'Hi')]
    assert V.convert(jobs, tmp_path) == 0
    assert (tmp_path / 'B' / '1_1.xwm').read_bytes() == b'audio' and not (tmp_path / 'B' / '1_1.fuz').exists()


def test_template_chain_is_one_rule_for_npcs_creatures_and_vendors():
    """AI data (services) comes along TPLT while the flag takes it; a chain into a leveled list keeps the
    base's own for vendors and NPCs, and the last creature for creatures."""
    ai = str(N.USE_AI_DATA)
    records = {1: _rec(1, **{'ACBS.TemplateFlags': ai, 'TPLT.Template': '00000002', 'AIDT.Services': '0'}),
               2: _rec(2, **{'AIDT.Services': '16'}),
               3: _rec(3, **{'ACBS.TemplateFlags': ai, 'TPLT.Template': '00000009', 'AIDT.Services': '4'}),
               4: _rec(4, **{'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000002', 'AIDT.Services': '32'})}
    assert [VE.services(records, records[f]) for f in (1, 3, 4)] == [16, 4, 32]
    npcs = _npcs(records, creatures=records)
    assert npcs.source(1, N.USE_AI_DATA) is records[2] and npcs.source(3, N.USE_AI_DATA) is None
    assert npcs.creatures.source(records[3], N.USE_AI_DATA) is records[3]


def test_placed_creatures_without_a_base_are_counted():
    """A placed creature whose base converts to nothing counts under its skeleton folder, else its EditorID."""
    creatures = {0x20: {'FormID': '00000020', 'EditorID': 'NightStalker', 'Model.MODL': 'Creatures\\NightStalker\\x.nif'},
                 0x21: {'FormID': '00000021', 'EditorID': 'Floater'}}
    npcs = _npcs({}, creatures=creatures)
    refs = [{'FormID': f'000001{i:02X}', 'NAME': name, 'Signature': 'ACRE', 'RecordFlags': '0', 'ParentCELL': 'C'}
            for i, name in enumerate(('00000020', '00000020', '00000021'))]
    assert npcs.placed(refs, lambda ref: ref['ParentCELL'], {}, {}) == {}
    assert npcs.builder.counts == {'ACRE skipped (no FO4 base): creatures\\nightstalker': 2,
                                   'ACRE skipped (no FO4 base): Floater': 1}
