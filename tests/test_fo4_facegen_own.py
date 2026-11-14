"""The faces stage's own FaceGen: which NPCs get it, per-NPC failures, and the CK fallback for only those NPCs.

See: docs/fork/fo4_facegen_plan.md#own-stage
"""

import struct
from concurrent.futures.process import BrokenProcessPool

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import facegeom, own_facegen
from fo4_import.face.facegeom import Rec
from fo4_import.pipeline import work_cache
from fo4_import.spike import facegen, facegen_own, facegen_skin
from tes5_import.base.writer import pack_subrecord


def _npc(template: bool, traits: bool) -> Rec:
    """An NPC record with or without a template, taking traits from it or not."""
    acbs = bytearray(20)
    struct.pack_into('<H', acbs, 14, 1 if traits else 0)
    return Rec('p.esp', b'NPC_', [(b'ACBS', bytes(acbs))] + ([(b'TPLT', b'\0' * 4)] if template else []))


def _race(flags: int) -> Rec:
    """A race whose DATA flags are `flags`."""
    data = bytearray(40)
    struct.pack_into('<I', data, 32, flags)
    return Rec('p.esp', b'RACE', [(b'DATA', bytes(data))])


def test_the_ck_exports_faces_of_facegen_races_not_taking_traits():
    """FaceGen Head race and no inherited traits: exported; a template alone does not stop it."""
    head, creature = _race(facegeom.FACEGEN_HEAD | 1), _race(1)
    assert facegeom.exported(_npc(False, False), head) and facegeom.exported(_npc(True, False), head)
    assert not facegeom.exported(_npc(True, True), head) and not facegeom.exported(_npc(False, False), creature)
    assert facegeom.exported(_npc(False, True), head)


def test_own_npcs_are_the_plugins_own_records(tmp_path):
    """NPC_ records the plugin adds count; its overrides of a master's do not."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='t')
    for fid in (0x01000802, 0x01000800, 0x00000123):
        w.add_record('NPC_', pack_fo4_record('NPC_', fid, 0, pack_subrecord('EDID', b'x\0')))
    w.next_object_id = 0x803
    w.write(str(tmp_path / 'p.esp'))
    assert facegen_own.own_npcs(tmp_path / 'p.esp') == [0x800, 0x802]


def test_fitted_faces_are_only_those_the_export_wrote(tmp_path, monkeypatch):
    """A fitted NPC with no FaceGeom (the export skips one taking traits) is not refitted or skinned (001810D4);
    nor is a converted creature (Dead Money's Ghost People), which FNV has no NPC_ record or FaceGen for."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='t')
    for fid in (0x01000800, 0x01000801, 0x01000802):
        subs = pack_subrecord('EDID', f'{own_facegen.FNV_PREFIX}Npc{fid & 0xFFF:X}\0'.encode())
        subs += pack_subrecord('ACBS', bytes(20)) + pack_subrecord('FMRI', b'\0' * 4)
        w.add_record('NPC_', pack_fo4_record('NPC_', fid, 0, subs))
    w.write(str(tmp_path / 'p.esp'))
    geom = tmp_path / own_facegen.GEOM_DIR / 'p.esp'
    geom.mkdir(parents=True)
    for stem in ('00000800', '00000802'):
        (geom / f'{stem}.nif').write_bytes(b'')
    npcs = ({'EditorID': 'Npc800'}, {'EditorID': 'Npc801'}, {})
    monkeypatch.setattr(facegen_skin, 'export_records', lambda export_dir, sig: npcs if sig == 'NPC_' else ())
    assert [f.form_id for f in facegen_skin.fitted_faces(tmp_path, 'p.esp', tmp_path)] == [0x800]


def test_a_face_a_later_plugin_overrides_is_not_refitted(monkeypatch):
    """refit_face leaves an NPC whose winning record is another plugin's: its sliders are not ours to patch."""
    monkeypatch.setitem(facegen_skin.shared(), 'plugin', 'p.esp')
    monkeypatch.setitem(facegen_skin.shared(), 'src', None)
    monkeypatch.setattr(facegen_skin.slider_fit, 'problem', lambda female: None)
    monkeypatch.setattr(facegen_skin.facegeom, 'npc_face', lambda *_: (Rec('mod.esp', b'NPC_', []),))
    assert facegen_skin.refit_face(facegen_skin.Face(0x800, 'x', False, False)) is None


def test_collect_keeps_only_the_named_npcs(tmp_path, monkeypatch):
    """With `only`, the named NPCs' files move into the mod; the CK's others are deleted from overwrite."""
    overwrite, data = tmp_path / 'overwrite', tmp_path / 'mod'
    monkeypatch.setattr(facegen.creation_kit, 'output_dir', lambda: overwrite)
    geom, tex = overwrite / facegen.FACEGEN_DIRS[0] / 'p.esp', overwrite / facegen.FACEGEN_DIRS[1] / 'p.esp'
    for folder, names in ((geom, ('00000800.nif', '00000801.nif')), (tex, ('00000800_d.dds', '00000801_s.dds'))):
        folder.mkdir(parents=True)
        for name in names:
            (folder / name).write_bytes(b'x')
    nifs = facegen.collect('p.esp', data, {'00000801'})
    assert [p.name for p in nifs] == ['00000801.nif']
    assert sorted(p.name for p in data.rglob('*') if p.is_file()) == ['00000801.nif', '00000801_s.dds']
    assert not [p for p in overwrite.rglob('*') if p.is_file()]


def test_a_failing_npc_is_reported_not_raised(monkeypatch):
    """own_face returns the error of a face that fails; a broken pool fails every face."""
    monkeypatch.setattr(facegen_skin, 'shared', lambda: {'src': None, 'plugin': 'p.esp', 'data': None})

    def boom(*_):
        """A write that fails."""
        raise ValueError('bad head part')
    monkeypatch.setattr(facegen_own, 'write_face', boom)
    assert facegen_own.own_face(0x800) == (0x800, 'ValueError: bad head part', '')
    monkeypatch.setattr(facegen_skin, 'pool', lambda job, work, forms: [
        (0x800, 'written', 'code changed'), (0x801, 'skipped', ''), (0x802, 'KeyError: x', ''), (0x803, 'kept', '')])
    assert facegen_own.export_own(None, [0x800, 0x801, 0x802, 0x803]) == (
        1, 1, 1, {0x802: 'KeyError: x'}, {'code changed': 1})

    def broken(*_):
        """A pool whose worker died."""
        raise BrokenProcessPool('killed')
    monkeypatch.setattr(facegen_skin, 'pool', broken)
    written, kept, skipped, failed, _ = facegen_own.export_own(None, [0x800, 0x801])
    assert (written, kept, skipped, sorted(failed)) == (0, 0, 0, [0x800, 0x801])


class _Src(facegeom.Sources):
    """Sources over in-memory records and files."""

    def __init__(self, files: dict, records: dict):
        """Hold `files` {path: bytes} and `records` {(owner, local id): Rec}."""
        self.files, self.records, self.masters, self.seen = files, records, {'p.esp': []}, set()

    def stored(self, rel: str) -> bytes:
        """The held file."""
        return self.files[rel]


def _kept_face(tmp_path, monkeypatch) -> tuple:
    """(run, made): run(npc ACBS, race DATA, texture) writes face 800 through the work cache in tmp_path, giving
    (status, written bytes); made lists each face made, not kept."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(facegen_own, 'texconv', lambda: 'texconv')
    made = []

    def make(src, plugin, form_id, textures=True):
        """Face files from the NPC's race and one texture; none for a texture b''."""
        made.append(form_id)
        src.get(src.record('p.esp', form_id), struct.pack('<I', 0x900))
        texture = src.read('textures/x.dds')
        return {'meshes/x.nif': texture} if texture else None
    monkeypatch.setattr(facegen_own, 'face_files', make)

    def run(acbs: bytes, race: bytes, texture: bytes, other: bytes = b'o', misses: list = None,
            loaded: dict = None) -> tuple:
        """One build's write of face 801 (ACBS `other`), then face 800 (its cache miss, if any, added to
        `misses`), with the other plugins `loaded` {name: masters} in the load order; face 800's."""
        records = {('p.esp', 0x800): Rec('p.esp', b'NPC_', [(b'ACBS', acbs)]),
                   ('p.esp', 0x801): Rec('p.esp', b'NPC_', [(b'ACBS', other)]),
                   ('p.esp', 0x900): Rec('p.esp', b'RACE', [(b'DATA', race)])}
        src, out = _Src({'textures\\x.dds': texture}, records), tmp_path / f'mod{len(made)}'
        src.masters.update(loaded or {})
        facegen_own.write_face(src, 'p.esp', 0x801, out)
        status = facegen_own.write_face(src, 'p.esp', 0x800, out, misses=misses)
        return status, (out / 'meshes/x.nif').read_bytes() if (out / 'meshes/x.nif').exists() else None
    return run, made


def test_a_face_is_kept_until_what_it_read_changes(tmp_path, monkeypatch):
    """A second build writes the kept face unmade; a changed texture, race or NPC record makes it again."""
    run, made = _kept_face(tmp_path, monkeypatch)
    assert run(b'a', b'r', b'tex') == ('written', b'tex') and run(b'a', b'r', b'tex') == ('kept', b'tex')
    assert run(b'a', b'r', b'new') == ('written', b'new') and run(b'a', b'r2', b'new') == ('written', b'new')
    assert run(b'b', b'r2', b'new') == ('written', b'new') and run(b'a', b'r2', b'new') == ('kept', b'new')
    assert made.count(0x800) == 4


def test_a_cache_miss_says_why(tmp_path, monkeypatch):
    """A face made again names the cause: no entry for a new NPC record, else the record or file that changed."""
    run, _ = _kept_face(tmp_path, monkeypatch)
    misses = []
    for build in ((b'a', b'r', b'tex'), (b'a', b'r', b'tex'), (b'a', b'r2', b'tex'), (b'a', b'r2', b'new'),
                  (b'b', b'r2', b'new')):
        run(*build, misses=misses)
    assert misses == ['no entry (NPC record, masters or texconv)', 'read RACE record changed', 'read file changed',
                      'no entry (NPC record, masters or texconv)']


def test_another_plugin_in_the_load_order_keeps_the_face(tmp_path, monkeypatch):
    """A plugin added to the load order (a test ESL, another mod) leaves the face kept: only its own plugin's
    masters key it."""
    run, made = _kept_face(tmp_path, monkeypatch)
    assert run(b'a', b'r', b'tex') == ('written', b'tex')
    assert run(b'a', b'r', b'tex', loaded={'test.esl': [], 'mod.esp': ['p.esp']}) == ('kept', b'tex')
    assert made.count(0x800) == 1


def test_a_face_not_exported_is_kept_too(tmp_path, monkeypatch):
    """An NPC the CK exports nothing for is skipped again without being made."""
    run, made = _kept_face(tmp_path, monkeypatch)
    assert run(b'a', b'r', b'') == ('skipped', None) and run(b'a', b'r', b'') == ('skipped', None)
    assert made.count(0x800) == 1


def test_another_npcs_record_does_not_remake_a_face(tmp_path, monkeypatch):
    """Face 800, made after 801 in one worker, is kept when only 801's record changes."""
    run, made = _kept_face(tmp_path, monkeypatch)
    assert run(b'a', b'r', b'tex') == ('written', b'tex') and run(b'a', b'r', b'tex', b'o2') == ('kept', b'tex')
    assert made == [0x801, 0x800, 0x801]


def test_the_second_pass_writes_head_meshes_only(tmp_path, monkeypatch):
    """heads() over every NPC asks for face textures; over the refitted forms, FaceGeom NIFs only.

    See: docs/fork/fo4_facegen_plan.md#second-pass
    """
    asked = []
    monkeypatch.setattr(facegen_skin, 'pool', lambda job, work, forms: [work(f) for f in forms])
    monkeypatch.setattr(facegen_skin, 'shared', lambda: {'src': None, 'plugin': 'p.esp', 'data': tmp_path})
    monkeypatch.setattr(facegen_own, 'write_face', lambda *a: asked.append(a[4]) or facegen_own.WRITTEN)
    monkeypatch.setattr(facegen_own, 'own_npcs', lambda path: [0x801])
    monkeypatch.setattr(facegen, 'clear', lambda plugin, data_dir: None)
    job = (None, tmp_path, 'p.esp', None)
    facegen.heads(job, True)
    facegen.heads(job, True, [0x800])
    assert asked == [True, False]


def test_a_mesh_only_face_keeps_its_own_entry(tmp_path, monkeypatch):
    """With and without textures, one NPC's faces are kept apart: neither pass takes the other's files."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(facegen_own, 'texconv', lambda: 'texconv')
    monkeypatch.setattr(facegen_own, 'face_files', lambda src, plugin, form_id, textures: {'f': bytes([textures])})
    src = _Src({}, {('p.esp', 0x800): Rec('p.esp', b'NPC_', [(b'ACBS', b'a')])})
    for _ in range(2):
        assert facegen_own.cached_files(src, 'p.esp', 0x800, True)[0] == {'f': bytes([1])}
        assert facegen_own.cached_files(src, 'p.esp', 0x800, False)[0] == {'f': bytes([0])}


def test_a_failed_ck_fallback_is_reported_and_our_heads_kept(tmp_path, monkeypatch):
    """Our FaceGen leaves MO2's view while the CK runs and comes back; a CK failure is a report line."""
    data = tmp_path / 'mod'
    ours = data / facegen.FACEGEN_DIRS[0] / 'p.esp' / '00000800.nif'
    ours.parent.mkdir(parents=True)
    ours.write_bytes(b'ours')
    seen = []

    def ck(plugin, data_dir):
        """A CK that checks ours is out of view, then fails."""
        seen.append(ours.exists())
        raise SystemExit('the Creation Kit crashed')
    monkeypatch.setattr(facegen, 'run_ck', ck)
    lines = facegen.fallback('p.esp', data, {0x801: 'ValueError: x'})
    assert seen == [False] and ours.read_bytes() == b'ours'
    assert lines == ['CK fallback failed, 1 NPCs have no FaceGen: the Creation Kit crashed']
