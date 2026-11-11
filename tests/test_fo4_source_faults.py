"""A bad source file is counted, not fatal: SourceFault from the mesh, collision and Elric steps, caught by the
caller that asked for the model and listed by file; a bug still ends the build; models are found in every one of
the game's own plugins.

See: docs/fork/fo4_build_speed.md#faults
"""

import collections
import pickle
import struct
from types import SimpleNamespace

import pytest

from fo4_import.base import source_fault as SF
from fo4_import.nif import collision as CO
from fo4_import.nif import elric as E
from fo4_import.nif import file as F
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import IDENTITY
from fo4_import.nif.file import NifFile
from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import export_index as X
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import work_cache as WC
from fo4_import.spike import activators as AC
from fo4_import.spike import creatures as CR
from fo4_import.spike import object_lod as OL
from fo4_import.spike import statics as ST
from fo4_import.spike import swaps as SW
from fo4_import.spike import talking_machines as TM
from fo4_import.spike import terminals as TE
from fo4_import.spike.cell import CellBuilder


@pytest.fixture(autouse=True)
def _no_faults():
    """Each test starts and ends with no fault counted."""
    SF.FAULTS.clear()
    yield
    SF.FAULTS.clear()


def _export(folder, masters: list) -> None:
    """An export folder whose _HEADER.txt lists `masters`."""
    folder.mkdir()
    (folder / '_HEADER.txt').write_text(''.join(f'Master[{i}]={m}\n' for i, m in enumerate(masters)), encoding='utf-8')


def _mesh(export, rel: str, data: bytes = b'nif') -> None:
    """Write `data` as meshes/`rel` in `export`."""
    path = export / 'meshes' / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _builder(tmp_path, monkeypatch, convert):
    """A stand-in CellBuilder on a masterless export holding meshes/bad.nif, its meshes converted by `convert`
    (the mesh cache kept under `tmp_path`)."""
    export = tmp_path / 'Game.esm'
    _export(export, [])
    _mesh(export, 'bad.nif')
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(MC, 'addon_map', lambda _: {})
    monkeypatch.setattr(MC, 'convert', convert)
    X.export_masters.cache_clear()
    builder = CellBuilder.__new__(CellBuilder)
    builder.export_dir, builder.data_dir, builder.meshes, builder.faulted = export, tmp_path / 'Data', {}, set()
    builder.counts, builder.weapons = collections.Counter(), set()
    return builder


def test_a_build_meets_a_missing_model_and_an_undefined_motion_system_finishes_and_lists_both(tmp_path, monkeypatch):
    """An item's missing model and a static whose rigid body has motion system 205 are both left out of their
    records, counted, and listed by file; the static is left out as a base with no mesh is."""
    builder = _builder(tmp_path, monkeypatch, lambda *_: CO._motion(205))
    assert builder.mesh('clutter\\gone.nif') == ('', None)
    assert builder.record(0x1000, 'STAT', {'FormID': '00001000', 'Model.MODL': 'bad.nif'}) is None
    assert builder.weapon_mesh('bad.nif', {}) == ('', None) and builder.weapons == set()
    lines = SF.report()
    assert any('gone.nif: missing model' in line for line in lines)
    assert any(str(builder.export_dir / 'meshes' / 'bad.nif') in line and 'motion system 205' in line
               for line in lines)
    assert lines[-1] == 'source faults: 2'
    assert builder.counts['STAT left out for its mesh (a source fault)'] == 1
    assert not builder.meshes and not list((tmp_path / 'cache').rglob('*.pkl'))


def test_a_bug_in_our_code_still_ends_the_build(tmp_path, monkeypatch):
    """A TypeError from the converter is not a SourceFault: it reaches the build and nothing is counted."""
    builder = _builder(tmp_path, monkeypatch, lambda *_: None + 1)
    with pytest.raises(TypeError):
        builder.mesh('bad.nif')
    assert not SF.FAULTS


def test_a_fault_crosses_a_process_pool_and_takes_its_file_once():
    """A fault pickles; at() names a file only when it has none."""
    fault = pickle.loads(pickle.dumps(SF.SourceFault(None, 'why')))
    assert (fault.file, fault.reason) == (None, 'why')
    assert str(fault.at('a.nif')) == 'a.nif: why' and fault.at('a.nif').at('b.nif').file == 'a.nif'


def _node(nif: NifFile, name: str, collision: int = NONE) -> dict:
    """A NiNode dict named `name` with collision object `collision`."""
    return {'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': IDENTITY, 'scale': 1.0, 'collision': collision, 'children': []}


def test_a_collision_node_matching_no_node_names_the_mesh_and_leaves_it_without_collision(tmp_path):
    """Elric's body on a node our mesh lacks: the mesh is written without its Havok, failed, and the fault is
    counted under the name the caller gave it."""
    ours = NifFile()
    ours.blocks = [('NiNode', _node(ours, 'Root', 1)), ('bhkCollisionObject', b'raw')]
    processed = NifFile()
    processed.blocks = [('NiNode', _node(processed, 'Elsewhere')), ('bhkPhysicsSystem', b'sys'),
                        ('bhkNPCollisionObject', struct.pack('<iHiI', 0, 0, 1, 0))]
    path = tmp_path / '00000.nif'
    path.write_bytes(F.write(ours))
    out = F.write(processed)
    assert E.finish([path], lambda sources: {name: out for name in sources}, ['meshes/tld/rock.nif']) == [path]
    assert [k for k, _ in F.read(path.read_bytes()).blocks] == ['NiNode']
    assert list(SF.FAULTS) == [('meshes/tld/rock.nif', "collision node 'elsewhere' matches no node of the mesh")]
    assert SF.faulted('meshes/tld/rock.nif')


def test_a_faulted_finish_is_not_cached_so_the_next_build_lists_it_again(tmp_path, monkeypatch):
    """elric_cache.finish(): a mesh whose graft faulted is written without collision but not kept in the work
    cache; Elric's step meets it again next build, under the mesh's own path."""
    runs = []

    def fake(paths, run, names):
        """Stand in for elric.finish: every mesh's graft faults, under its name in `names`."""
        runs.append(names)
        for name in names:
            SF.count(SF.SourceFault(name, 'no node'))
        return list(paths)
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'finish', fake)
    path = tmp_path / 'rock.nif'
    for _ in range(2):
        path.write_bytes(b'rock')
        assert EC.finish([path]) == [path]
    assert runs == [[path], [path]] and list(SF.FAULTS) == [(str(path), 'no node')]


def _faulty(*_, **__):
    """A converter meeting a bad source file."""
    raise SF.SourceFault('bad.nif', 'motion system 205')


def _stand_in_builder(**more) -> SimpleNamespace:
    """A builder carrying counts, and `more`."""
    return SimpleNamespace(counts=collections.Counter(), **more)


def test_an_activator_whose_mesh_faults_is_not_ambient(tmp_path, monkeypatch):
    """ambient(): a faulted mesh reads as no loop (the activator is made as an ACTI), counted."""
    _mesh(tmp_path, 'act.nif')
    monkeypatch.setattr(AC, 'cached_convert', _faulty)
    acts = AC.Activators.__new__(AC.Activators)
    acts.export_dir, acts.water = tmp_path, set()
    acts.builder = _stand_in_builder(radio=SimpleNamespace(stations_of={}))
    assert acts.ambient({'FormID': '00001000'}, 'act.nif') is False
    assert acts.builder.counts['activator loop not read (a source fault)'] == 1 and SF.FAULTS


def test_a_creature_whose_body_faults_keeps_its_targets_skin(monkeypatch):
    """_skin(): no skin of FNV's body is written; None, so _worn keeps the target's WNAM as a stand-in does."""
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.records = {1: {'Model.MODL': 'creatures\\dog\\skeleton.nif', 'EditorID': 'Dog'}}
    creatures.worn, creatures.skins = {'dog': (None, None, None)}, {}
    creatures.builder = _stand_in_builder(writer=None)
    monkeypatch.setattr(creatures, '_mesh', _faulty)
    assert creatures._skin(1, SimpleNamespace(edid='Dog')) is None and creatures.skins == {1: None}
    assert creatures.builder.counts["creatures on their target's skin (a source fault)"] == 1


def test_a_talking_machine_part_that_faults_is_left_out(tmp_path, monkeypatch):
    """statics(): the faulted part gets no activator; the others are placed; counted."""
    for name in ('a.nif', 'b.nif'):
        _mesh(tmp_path, f'creatures\\eyebot\\{name}')
    monkeypatch.setattr(TM, 'bone_worlds', lambda path: {})
    monkeypatch.setattr(TM, 'part_pose', lambda path, worlds: {})
    monkeypatch.setattr(TM, 'write_assets', lambda d, model, *a, **k: _faulty() if 'a.nif' in model else ('m', None))
    builder = _stand_in_builder(writer=SimpleNamespace(derive_formid=lambda site, key: 7,
                                                       add_record=lambda sig, rec: None))
    machines = TM.TalkingMachines(builder, tmp_path, tmp_path)
    rec = {'Model.MODL': 'creatures\\eyebot\\skeleton.nif', 'NIFZCount': 2, 'NIFZ[0]': 'a.nif', 'NIFZ[1]': 'b.nif'}
    assert machines.statics(rec) == [7]
    assert builder.counts['talking machine part left out (a source fault)'] == 1


def test_a_terminal_whose_mesh_faults_falls_to_the_plain_mesh(monkeypatch):
    """_look(): a faulted screen conversion takes builder.mesh()'s answer, ('', None) for the same fault."""
    monkeypatch.setattr(TE, 'terminal_assets', _faulty)
    terms = TE.Terminals.__new__(TE.Terminals)
    terms.export_dir, terms.looks = None, {}
    terms.builder = _stand_in_builder(data_dir=None, meshes={}, mesh=lambda model: ('', None))
    assert terms._look('t.nif') == (('', None), None)


def test_a_swap_whose_mesh_faults_is_no_swap(monkeypatch):
    """_pair(): None, as for a shape the model lacks; swap() writes no MSWP and counts it."""
    monkeypatch.setattr(SW, 'swap_material', _faulty)
    swaps = SW.Swaps.__new__(SW.Swaps)
    swaps.export_dir, swaps.pairs, swaps.made = None, {}, {}
    swaps.targets, swaps.models = {'P': ('Ref', 'Node', 'tex')}, {'ref': 'm.nif'}
    swaps.builder = _stand_in_builder(data_dir=None)
    assert swaps.swap('P') == 0 and swaps.builder.counts['swap without a converted shape: P'] == 1


def test_an_lod_mesh_that_faults_leaves_the_static_without_lod(tmp_path, monkeypatch):
    """_converted() gives None; a TREE's card then gives no LOD, as without a billboard; a shipped _lod.nif that
    faults reads as none shipped."""
    monkeypatch.setattr(OL, 'cached_files', _faulty)
    monkeypatch.setattr(OL, 'card_nif', lambda *a: b'card')
    monkeypatch.setattr(OL, 'keep', lambda rel, made: tmp_path / 'card.nif')
    (tmp_path / 'textures' / 'trees' / 'billboards').mkdir(parents=True)
    (tmp_path / 'textures' / 'trees' / 'billboards' / 'joshua.dds').write_bytes(b'dds')
    _mesh(tmp_path, 'rock_lod.nif')
    builder = _stand_in_builder(export_dir=tmp_path, meshes={}, mesh=lambda model: ('', None))
    lod = OL.ObjectLod(builder)
    rec = {'Model.MODL': 'trees\\joshua.spt', 'BNAM.BillboardWidth': 1, 'BNAM.BillboardHeight': 1}
    assert lod.tree(1, rec, 'FNV_Joshua', 'm') == (0, ()) and lod._shipped('rock.nif') is None
    assert builder.counts['LOD meshes left out (a source fault)'] == 1


def test_a_mod_finds_a_pre_order_pack_model_its_masters_lack_but_not_its_records(tmp_path):
    """A mod on FalloutNV.esm alone resolves a ClassicPack.esm mesh path; its records stay its masters'; the game's
    own export does not reach the pack."""
    _export(tmp_path / 'FalloutNV.esm', [])
    _export(tmp_path / 'ClassicPack.esm', ['FalloutNV.esm'])
    _export(tmp_path / 'YUP.esm', ['FalloutNV.esm'])
    _mesh(tmp_path / 'ClassicPack.esm', 'nvdlcpre1/weapons/10mmpistolpreorder.nif', b'pack')
    (tmp_path / 'ClassicPack.esm' / 'WEAP.txt').write_text(
        '---RECORD_BEGIN---\nSignature=WEAP\nFormID=01000800\nEditorID=Pack\n---RECORD_END---\n', encoding='utf-8')
    X.export_masters.cache_clear()
    rel = ('meshes', 'nvdlcpre1', 'weapons', '10mmpistolpreorder.nif')
    assert X.export_file(tmp_path / 'YUP.esm', *rel).read_bytes() == b'pack'
    assert (X.asset_root(tmp_path / 'YUP.esm', 'meshes') / 'nvdlcpre1' / 'weapons' / rel[-1]).read_bytes() == b'pack'
    assert X.export_records(tmp_path / 'YUP.esm', 'WEAP') == ()
    assert not X.export_file(tmp_path / 'FalloutNV.esm', *rel).is_file()


def test_a_fallout_3_mod_finds_its_games_dlc_models_not_new_vegas(tmp_path):
    """The game is the mod's root master's: a mod on Fallout3.esm reaches Zeta.esm's mesh, never a New Vegas
    pack's."""
    _export(tmp_path / 'Fallout3.esm', [])
    for name in ('Zeta.esm', 'ClassicPack.esm'):
        _export(tmp_path / name, [])
        _mesh(tmp_path / name, f'{name}.nif')
    _export(tmp_path / 'Mod.esp', ['Fallout3.esm'])
    X.export_masters.cache_clear()
    assert X.export_file(tmp_path / 'Mod.esp', 'meshes', 'Zeta.esm.nif').read_bytes() == b'nif'
    assert not X.export_file(tmp_path / 'Mod.esp', 'meshes', 'ClassicPack.esm.nif').is_file()


def test_a_texture_no_export_layer_holds_is_counted_not_fatal(tmp_path):
    """copy_texture() of a texture missing from every layer counts a fault and copies nothing."""
    assert ST.copy_texture(tmp_path / 'export', tmp_path / 'data', 'textures/nvb/missing.dds') is False
    assert [reason for _, reason in SF.FAULTS] == ['missing texture (in no export layer)']
    assert not (tmp_path / 'data').exists()
