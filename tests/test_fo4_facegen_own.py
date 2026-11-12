"""The faces stage's own FaceGen: which NPCs get it, per-NPC failures, and the CK fallback for only those NPCs.

See: docs/fork/fo4_facegen_plan.md#own-stage
"""

import struct
from concurrent.futures.process import BrokenProcessPool

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import facegeom, own_facegen
from fo4_import.face.facegeom import Rec
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


def test_fitted_faces_are_only_those_the_export_wrote(tmp_path):
    """A fitted NPC with no FaceGeom (the export skips one taking traits) is not refitted or skinned (001810D4)."""
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='t')
    for fid in (0x01000800, 0x01000801):
        subs = pack_subrecord('EDID', f'{own_facegen.FNV_PREFIX}Npc{fid & 0xFFF:X}\0'.encode())
        subs += pack_subrecord('ACBS', bytes(20)) + pack_subrecord('FMRI', b'\0' * 4)
        w.add_record('NPC_', pack_fo4_record('NPC_', fid, 0, subs))
    w.write(str(tmp_path / 'p.esp'))
    geom = tmp_path / own_facegen.GEOM_DIR / 'p.esp'
    geom.mkdir(parents=True)
    (geom / '00000800.nif').write_bytes(b'')
    assert [f.form_id for f in facegen_skin.fitted_faces(tmp_path, 'p.esp')] == [0x800]


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
    assert facegen_own.own_face(0x800) == (0x800, 'ValueError: bad head part')
    monkeypatch.setattr(facegen_skin, 'pool', lambda job, work, forms: [(0x800, 'written'), (0x801, 'skipped'),
                                                                        (0x802, 'KeyError: x')])
    assert facegen_own.export_own(None, [0x800, 0x801, 0x802]) == (1, 1, {0x802: 'KeyError: x'})

    def broken(*_):
        """A pool whose worker died."""
        raise BrokenProcessPool('killed')
    monkeypatch.setattr(facegen_skin, 'pool', broken)
    written, skipped, failed = facegen_own.export_own(None, [0x800, 0x801])
    assert (written, skipped, sorted(failed)) == (0, 0, [0x800, 0x801])


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
