"""Faces, FaceGen, voice, vendors and unbuilt creatures after the converter audit's speed and drop findings.

See: docs/fork/fo4_tool_audit.md#first-build
See: docs/fork/fo4_tool_audit.md#rebuild
"""

import collections
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

from fo4_import.base import ba2_pack
from fo4_import.base import ba2
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_ESM, FALLOUTNV_ESM, use_source
from fo4_import.base.writer import pack_fo4_header, pack_fo4_record
from fo4_import.face import memo, tint
from fo4_import.face import texture as TX
from fo4_import.face.bake import align, surface
from fo4_import.face.fnv_head import FnvHead, head
from fo4_import.nif import file as nif_file
from fo4_import.pipeline.export_index import asset_root
from fo4_import.spike import facegen as FG
from fo4_import.spike import npcs as N
from fo4_import.spike import vendors as VE
from fo4_import.spike import voice as V
from fo4_import.spike.creatures import USE_SPELLS, Creatures
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_group, pack_subrecord

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
VANILLA_MESHES = FALLOUT4_ESM.parent / 'Fallout4 - Meshes.ba2'
#: Vanilla Scarlett's FaceGen: HairFemale04, a hair with cloth physics.
SCARLETT_FACEGEN = 'meshes/Actors/Character/FaceGenData/FaceGeom/Fallout4.esm/0004B240.nif'


def _plugin(*records: tuple) -> bytes:
    """Plugin bytes holding `records` [(signature, FormID, subrecords)], a top group per signature."""
    groups = collections.defaultdict(bytes)
    for sig, fid, subs in records:
        groups[sig] += pack_fo4_record(sig, fid, 0, subs)
    return pack_fo4_header([], len(records), 0x800, 0, 'test') + b''.join(
        pack_group(0, sig.encode(), body) for sig, body in groups.items())


def uv_grid(n: int, scale: float, lift: float) -> tuple:
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
    npcs.creatures._entry = lambda rec: (None, '')
    npcs.races, npcs.child_races = {0x19: 'Caucasian', 0x3B3E: 'Ghoul'}, set()
    npcs.builder = SimpleNamespace(counts=collections.Counter(), actor_ids={})
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
    assert tint.skin_tone_layers(_plugin(('RACE', tint.HUMAN_RACE, b''.join(teti)), ('RACE', 0x1234, other))) == {5, 9}


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
    fo4 = uv_grid(9, 1.0, 0.0)
    fnv_points, fnv_uvs, fnv_tris = uv_grid(7, 1.1, 0.1)
    fnv = FnvHead(fnv_points, fnv_tris, fnv_points, fnv_uvs)
    rgba = rng.integers(1, 256, (64, 64, 4), dtype=np.uint8)
    pieces = (rng.uniform(0, 200, (32, 32, 3)), rng.uniform(-20, 20, (32, 32, 3)), None)
    for variant in ('T1', 'T2', 'T1'):
        new, old = TX.face_texture(rgba, fo4, fnv, pieces, variant), _old_face_texture(rgba, fo4, fnv, pieces, variant)
        assert new[0].tobytes() == old[0].tobytes() and new[1].tobytes() == old[1].tobytes()
    assert not TX.texel_map(fo4, (fnv.mean, fnv.triangles, fnv.uvs), (64, 64))[2].flags.writeable


@pytest.mark.skipif(not (EXPORT / 'meshes' / 'characters' / 'head' / 'headhuman.nif').exists(),
                    reason='needs the FNV export')
def test_fnv_head_mesh_is_read_once():
    """Two NPCs on one head mesh share its read-only mean, under a plain folder or a new layered one each time
    (asset_root); each gets its own face."""
    one, two = (head(EXPORT / 'meshes', 'Characters\\Head\\HeadHuman.NIF', '', '') for _ in range(2))
    assert one.mean is two.mean and not one.mean.flags.writeable and one.npc is not two.npc
    assert np.array_equal(one.npc, one.mean)
    layered = [head(asset_root(EXPORT, 'meshes'), 'Characters\\Head\\HeadHuman.NIF', '', '') for _ in range(2)]
    assert layered[0].mean is layered[1].mean is one.mean


def test_faces_follow_templates_and_lists(monkeypatch):
    """The faces warm_faces fits: an NPC's own, its traits template's, a leveled list entry's; no ghoul's."""
    monkeypatch.setattr(N, 'basis_hash', lambda female: 'basis')
    records = {1: _rec(1), 2: _rec(2, **{'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000003'}),
               3: _rec(3, **{'ACBS.Flags': '1'}), 4: _rec(4, **{'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000010'}),
               5: _rec(5), 6: _rec(6, **{'RNAM.Race': '00003B3E'})}
    lists = {0x10: {'FormID': '00000010', 'EntryCount': '1', 'Entry[0].Level': '1', 'Entry[0].FormID': '00000005',
                    'Entry[0].Count': '1'}}
    faces = _npcs(records, lists)._faces([1, 2, 4, 6])
    assert {fid: female for fid, (_, female) in faces.items()} == {1: False, 3: True, 5: False}


def test_face_workers_follow_the_faces_the_cores_and_free_memory(monkeypatch):
    """One worker per FACES_PER_WORKER faces, at most half the logical cores, as many as the profile's memory holds."""
    monkeypatch.setattr(N.os, 'cpu_count', lambda: 16)
    monkeypatch.setattr(N, 'pool_workers', lambda each, jobs, asked: min(jobs, asked))
    assert [N.face_workers(n) for n in (1, 2 * N.FACES_PER_WORKER, 10 ** 6)] == [1, 2, 8]
    monkeypatch.setattr(N, 'pool_workers', lambda each, jobs, asked: min(jobs, asked, 4))
    assert N.face_workers(10 ** 6) == 4


def test_ck_timeout_scales_with_the_plugins_npcs(tmp_path):
    """The CK gets CK_FACE_SECONDS per NPC_ record in the plugin, never under the CK_TIMEOUT floor."""
    plugin = tmp_path / 'Faces.esp'
    plugin.write_bytes(_plugin(*[('NPC_', 0x800 + i, b'') for i in range(3)], ('RACE', 0x900, b'')))
    assert FG.npc_count(plugin) == 3
    assert FG.ck_timeout(3) == FG.CK_TIMEOUT
    assert FG.ck_timeout(2247) == 2247 * FG.CK_FACE_SECONDS > FG.CK_TIMEOUT


def test_ck_exports_facegen_for_64_bit_pc(monkeypatch):
    """The CK is asked for the X64 target: W32 writes hair cloth physics with 4-byte pointers."""
    calls = []
    monkeypatch.setattr(FG.creation_kit.subprocess, 'Popen', lambda args, **_: calls.append(args))
    monkeypatch.setattr(FG.creation_kit, 'running', lambda: False)
    monkeypatch.setattr(FG.creation_kit.time, 'sleep', lambda _: None)
    monkeypatch.setattr(FG.creation_kit, 'output_dir', lambda: FG.creation_kit.MO2 / 'overwrite')
    FG.run_ck('Spike.esp')
    assert calls[0][-1] == '-ExportFaceGenData:Spike.esp X64'


def test_ck_closed_once_quiet_after_writing(monkeypatch, tmp_path):
    """A CK that wrote files and then nothing for CK_QUIET seconds is closed and counts as done; one that never
    wrote runs to its timeout, is closed, and raises."""
    CK, clock, closed = FG.creation_kit, [1000.0], []
    monkeypatch.setattr(CK.subprocess, 'Popen', lambda *_, **__: None)
    monkeypatch.setattr(CK, 'running', lambda: True)
    monkeypatch.setattr(CK, 'close', lambda: closed.append(clock[0]))
    monkeypatch.setattr(CK, 'output_dir', lambda: tmp_path)
    monkeypatch.setattr(CK.time, 'time', lambda: clock[0])
    monkeypatch.setattr(CK.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(CK, 'newest_file', lambda _: 1010.0)
    CK.run('-x', 10 * CK.CK_QUIET, 'testing')
    assert closed == [pytest.approx(1010.0 + CK.CK_QUIET, abs=CK.CK_POLL)]
    monkeypatch.setattr(CK, 'newest_file', lambda _: 0.0)
    with pytest.raises(SystemExit, match='did not finish'):
        CK.run('-x', 100, 'testing')
    assert len(closed) == 2


def test_ck_closed_when_it_writes_nothing_in_ck_first(monkeypatch, tmp_path):
    """A CK that writes no file within CK_FIRST seconds is closed then, not at its (hours long) timeout, and raises."""
    CK, clock, closed = FG.creation_kit, [1000.0], []
    monkeypatch.setattr(CK.subprocess, 'Popen', lambda *_, **__: None)
    monkeypatch.setattr(CK, 'running', lambda: True)
    monkeypatch.setattr(CK, 'close', lambda: closed.append(clock[0]))
    monkeypatch.setattr(CK, 'output_dir', lambda: tmp_path)
    monkeypatch.setattr(CK, 'newest_file', lambda _: 0.0)
    monkeypatch.setattr(CK.time, 'time', lambda: clock[0])
    monkeypatch.setattr(CK.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    with pytest.raises(SystemExit, match='no file written'):
        CK.run('-x', 20 * CK.CK_FIRST, 'testing')
    assert closed == [pytest.approx(1000.0 + CK.CK_FIRST, abs=CK.CK_POLL)]


@pytest.mark.skipif(not VANILLA_MESHES.exists(), reason='needs Fallout 4')
def test_export_refuses_facegen_with_32_bit_cloth_physics(monkeypatch, tmp_path):
    """Vanilla FaceGen with cloth hair (Scarlett's) passes; the same with its packfile's pointer size set to 4, as
    the CK's W32 target writes it, stops the export."""
    vanilla = Archives(VANILLA_MESHES.parent, VANILLA_MESHES.name).read(SCARLETT_FACEGEN)
    assert FG.cloth_pointer_sizes(vanilla) == [8]
    nif = nif_file.read(vanilla)
    at = next(i for i, (kind, _) in enumerate(nif.blocks) if kind == 'BSClothExtraData')
    raw = bytearray(nif.blocks[at][1])
    raw[FG.CLOTH_POINTER_SIZE_AT] = 4
    nif.blocks[at] = ('BSClothExtraData', bytes(raw))
    face = tmp_path / '00000801.NIF'
    monkeypatch.setattr(FG, 'run_ck', lambda *_: None)
    monkeypatch.setattr(FG, 'collect', lambda *_: [face])
    face.write_bytes(vanilla)
    assert FG.export('Spike.esp', tmp_path) == 1
    face.write_bytes(nif_file.write(nif))
    with pytest.raises(SystemExit, match='00000801.NIF'):
        FG.export('Spike.esp', tmp_path)


def test_prune_keeps_only_faces_of_the_plugins_npcs_from_the_last_export(tmp_path, monkeypatch):
    """A FaceGeom NIF of an NPC_ the plugin dropped goes with its textures; a texture an older export left (no NIF)
    goes, loose or staged; a current NPC_'s face stays."""
    geom, loose = (tmp_path / folder / 'Spike.esp' for folder in FG.FACEGEN_DIRS)
    monkeypatch.setattr(ba2_pack, 'STAGING_CACHE', tmp_path / 'cache')
    staged = ba2_pack.staging_root(tmp_path) / FG.FACEGEN_DIRS[1] / 'Spike.esp'
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


@pytest.mark.skipif(not TX.TEXCONV.exists(), reason="needs the CK's texconv")
def test_a_texture_taking_a_vanilla_ones_place_keeps_its_format_size_and_mips():
    """An opaque face drawn over vanilla's BC3 1024 face diffuse stays BC3 1024 with 11 mips (the CK refuses a
    face texture in another format than its race's); over a BC1 one it is BC1."""
    rgba = np.full((256, 256, 4), 200, np.uint8)
    for fmt, size, mips in ((77, 1024, 11), (71, 512, 10)):
        like = ba2.dds(fmt, size, size, b'')
        out = TX.dds_like(rgba, like)
        assert TX.dds_layout(out) == (TX.DXGI_NAMES[fmt], size, size)
        assert struct.unpack_from('<I', out, 28)[0] == mips


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


def test_an_unused_voice_file_waits_in_the_cache_and_comes_back_when_a_line_needs_it(tmp_path):
    """A build without line 2's voice type keeps its .fuz aside, not deleted; the next build needing it restores it
    instead of converting it again."""
    voice, cache, src = tmp_path / 'Voice' / 'MaleAdult01', tmp_path / 'VoiceCache', tmp_path / 'line.ogg'
    _write(voice / '1_1.fuz', b'one')
    _write(voice / '2_1.fuz', b'two')
    assert V.remove_stale([(src, voice / '1_1.fuz', 'a')], [voice], cache) == 1
    assert not (voice / '2_1.fuz').exists() and (cache / 'MaleAdult01' / '2_1.fuz').read_bytes() == b'two'
    assert V.restore([(src, voice / '1_1.fuz', 'a'), (src, voice / '2_1.fuz', 'b')], cache) == 1
    assert (voice / '2_1.fuz').read_bytes() == b'two' and not (cache / 'MaleAdult01' / '2_1.fuz').exists()


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


def test_a_creature_merchant_takes_its_chest_from_the_source_plugin(tmp_path):
    """A placed creature's XMRC, which the export drops, is read from the source plugin, as an NPC's is."""
    plugin = tmp_path / 'Source.esm'
    plugin.write_bytes(_plugin(('ACRE', 0x30, pack_subrecord('NAME', struct.pack('<I', 0x20))
                                + pack_subrecord('XMRC', struct.pack('<I', 0x40))),
                               ('ACHR', 0x31, pack_subrecord('NAME', struct.pack('<I', 0x21)))))
    blocks = {'REFR': 'Signature=REFR\nFormID=00000040\n', 'ACRE': 'Signature=ACRE\nFormID=00000030\nNAME=00000020\n',
              'ACHR': 'Signature=ACHR\nFormID=00000031\nNAME=00000021\n'}
    for sig, block in blocks.items():
        (tmp_path / f'{sig}.txt').write_text(f'---RECORD_BEGIN---\n{block}---RECORD_END---\n', encoding='utf-8')
    VE.merchant_chests.cache_clear()
    use_source(plugin)
    try:
        sold = VE.merchants(tmp_path, lambda actor: True)
    finally:
        use_source(FALLOUTNV_ESM)
        VE.merchant_chests.cache_clear()
    assert [(a['FormID'], c['FormID']) for a, c in sold] == [('00000030', '00000040')]


def test_a_creature_vendor_wears_its_vendor_faction():
    """A creature base with a vendor faction gets its SNAM, rank 0, after its own factions."""
    creatures = Creatures.__new__(Creatures)
    creatures.builder = SimpleNamespace(vendors={0x20: 0xABC}, factions={0x5: 0x123})
    creatures.records, creatures.sounds = {}, SimpleNamespace(source=lambda rec: None)
    creatures._death_item = creatures._spells = lambda rec: None
    flags = N.USE_STATS | N.USE_TRAITS | N.USE_MODEL | USE_SPELLS
    rec = _rec(0x20, **{'ACBS.TemplateFlags': str(flags), 'TPLT.Template': '00000099', 'FactionCount': '1',
                        'Faction[0].FormID': '00000005', 'Faction[0].Rank': '1'})
    edit = creatures.own_parts(rec, templated=True)[3]
    snams = [data for tag, data in subrecords(edit(pack_subrecord('ACBS', b''))) if tag == b'SNAM']
    assert snams == [struct.pack('<Ib', 0x123, 1), struct.pack('<Ib', 0xABC, 0)]
    assert N.vendor_snam(creatures.builder, 0x21) == b''


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


def test_a_race_head_without_an_egt_gets_no_colour_offset(tmp_path):
    """A head texture whose model ships no .egt keeps its own colours."""
    Image.fromarray(np.full((4, 8, 3), 90, np.uint8)).save(tmp_path / 'head.png')
    base, offset = TX.fnv_texture(tmp_path / 'head.png', tmp_path / 'head.egt', np.ones(50))
    assert base.shape == offset.shape == (4, 8, 3) and not offset.any()
