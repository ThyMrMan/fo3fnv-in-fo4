"""The preflight audits that read a Fallout 4 build's files and history: shader names, the previous build,
quest-stage and actor targets, and DLC overrides.

See: docs/fork/fo4_preflight.md#materials
"""
import ast
import json
import os
import struct
import time
from collections import defaultdict
from types import SimpleNamespace

from fo4_import.base.ba2_write import write_general
from fo4_import.nif.blocks import pack_effect, pack_texture_set
from fo4_import.nif.file import NifFile, write
from tests.test_preflight_fo4 import OWN, fo4_index, rec, u32
from tests.test_preflight_audits import zs
from tools.validate.preflight import asset_nif, build_history, dlc_overrides, quest_targets
from tools.validate.preflight.asset_load import norm
from tools.validate.preflight.plugin_index import PluginIndex

#: The FO4 condition function indexes of GetStageDone and GetIsID.
GET_STAGE_DONE, GET_IS_ID = quest_targets.FUNCS['GetStageDone'], quest_targets.FUNCS['GetIsID']


def effect(name: int, texture: str) -> bytes:
    """A BSEffectShaderProperty named by string `name`, with source texture `texture`."""
    return pack_effect(dict(name=name, extra=[], controller=-1, flags1=0, flags2=0, uv_offset=(0.0, 0.0),
                            uv_scale=(1.0, 1.0), source_texture=texture, clamp=0, lighting_influence=0,
                            env_min_lod=0, unused=0, falloff=(0.0,) * 4, base_color=(1.0,) * 4, base_color_scale=1.0,
                            soft_depth=0.0, greyscale='', env_map='', normal='', env_mask='', env_map_scale=1.0))


def nif(effect_name: int, lighting_name: int) -> bytes:
    """A NIF whose strings are Root, BSX and a BGSM: an effect shader, a lighting shader and a texture set."""
    blocks = [('BSEffectShaderProperty', effect(effect_name, 'Effects/glow.dds')),
              ('BSLightingShaderProperty', struct.pack('<Ii', 0, lighting_name) + bytes(40)),
              ('BSShaderTextureSet', pack_texture_set({'textures': ['Data\\Textures\\a_d.dds', '']}))]
    return write(NifFile(strings=['Root', 'BSX', 'Materials\\fnv\\a.bgsm'], blocks=blocks))


def test_shader_names_unset_wrong_and_effect_bgsm():
    """Name -1 is no name (not the last string); BSX is wrong; an effect naming a BGSM is wrong; a BGSM lighting
    shader is a material, and textures lose a leading Data."""
    names, textures = asset_nif.shader_parts(nif(-1, 2))
    assert names == [('BSEffectShaderProperty', ''), ('BSLightingShaderProperty', 'Materials\\fnv\\a.bgsm')]
    assert sorted(norm(t, 'textures') for t in textures) == ['textures\\a_d.dds', 'textures\\effects\\glow.dds']
    data = {'meshes\\ok.nif': nif(-1, 2), 'meshes\\bsx.nif': nif(1, -1), 'meshes\\bgsm.nif': nif(2, -1)}
    materials, found = defaultdict(set), defaultdict(set)
    bad, unreadable = asset_nif.scan(SimpleNamespace(read=data.get), sorted(data), materials, found)
    assert dict(bad) == {('shader-name', 'BSX'): {'meshes\\bsx.nif'},
                         ('effect-bgsm', 'Materials\\fnv\\a.bgsm'): {'meshes\\bgsm.nif'}}
    assert set(materials) == {'materials\\fnv\\a.bgsm'} and not unreadable


def built(stamp: str, records: dict, contents: dict) -> dict:
    """A kept build: its stamp's end time, records and contents."""
    return {'stamp': {'ended': stamp}, 'records': records, 'contents': contents}


def test_previous_build_rotates_and_reports_gone_and_moved(tmp_path):
    """A new build is compared with the last one seen, the same build again with the one before it; records gone
    and EditorIDs moved are reviews."""
    first = built('A', {'00000001': 'INFO|', '00000002': 'SCEN|S', '00000003': 'QUST|Q'}, {'00000003': '1'})
    second = built('B', {'00000003': 'QUST|Q', '00000004': 'SCEN|S'}, {'00000003': '2'})
    assert build_history.remember(tmp_path, first) is None
    assert build_history.remember(tmp_path, second) == first
    assert build_history.remember(tmp_path, second) == first
    keys = {f.key: f.severity for f in build_history.compare('P.esm', first, second)}
    assert keys == {'build|P.esm|previous-removed|INFO': 'review', 'build|P.esm|previous-moved|SCEN': 'review'}


def test_cache_modules_resolve_and_invalidate():
    """A cache call's module argument resolves from a string, __name__ or an import; an edit to a file the code
    tag hashes may invalidate that cache; the mesh cache's written files are found under its own module."""
    tree = ast.parse('from fo4_import.nif import outfit\nfrom fo4_import.nif.outfit import worn\n')
    imports = build_history.imports_of(tree)
    args = [ast.parse(t, mode='eval').body for t in ("'a.b'", '__name__', 'outfit.__name__', 'worn.__module__', 'x')]
    assert [build_history.resolve(a, 'here', imports) for a in args] == [
        'a.b', 'here', 'fo4_import.nif.outfit', 'fo4_import.nif.outfit', None]
    sites = build_history.cache_sites()
    assert any(s.startswith('fo4_import/pipeline/mesh_cache.py') for s in sites['fo4_import.pipeline.mesh_cache'])
    hit = build_history.invalidated({'fo4_import/pipeline/code_tag.py'}, {'fo4_import.pipeline.code_tag': ['x:1']})
    assert hit == {'fo4_import.pipeline.code_tag': (['x:1'], ['fo4_import/pipeline/code_tag.py'])}


def ctda(func: int, p1: int, p2: int = 0, value: float = 1.0) -> bytes:
    """A 32-byte Fallout 4 CTDA: `func`(p1, p2) == value."""
    return struct.pack('<B3xfH2xIIII4x', 0, value, func, p1, p2, 0, 0)


def target_plugin():
    """A build: quest Q (stage 10), placed actor A, leveled list L giving C, unplaced B; an INFO testing each."""
    q, a, b, c, lvl, info = (OWN | n for n in (1, 2, 3, 4, 5, 6))
    return fo4_index([
        rec('QUST', q, [('EDID', zs('FNV_Q')), ('INDX', struct.pack('<HBB', 10, 0, 0))]),
        rec('NPC_', a, [('EDID', zs('FNV_A'))]), rec('NPC_', b, [('EDID', zs('FNV_B'))]),
        rec('NPC_', c, [('EDID', zs('FNV_C'))]),
        rec('LVLN', lvl, [('LVLO', struct.pack('<HHIhh', 1, 0, c, 1, 0))]),
        rec('ACHR', OWN | 7, [('NAME', u32(a))]), rec('ACHR', OWN | 8, [('NAME', u32(lvl))]),
        rec('INFO', info, [('CTDA', ctda(GET_STAGE_DONE, q, 20)), ('CTDA', ctda(GET_STAGE_DONE, q, 10)),
                           ('CTDA', ctda(GET_STAGE_DONE, OWN | 99, 5)), ('CTDA', ctda(GET_IS_ID, a)),
                           ('CTDA', ctda(GET_IS_ID, b)), ('CTDA', ctda(GET_IS_ID, c))])])


def test_stage_and_actor_targets():
    """A stage the quest lacks is an error, a review when the source quest lacks it too; a quest the build lacks is
    an error; GetIsID of an actor placed nowhere is an error when the source places it."""
    index = target_plugin()
    built_parts = quest_targets.Built(index, [], 'FNV_')
    stages, actors = quest_targets.condition_targets(index)
    fnv = SimpleNamespace(stages={'q': {10, 20}}, placed={'b'})
    found = {f.key: f.severity for f in quest_targets.stage_findings('P', index, built_parts, fnv, stages)
             + quest_targets.actor_findings('P', index, built_parts, fnv, actors)}
    assert found == {'targets|P|stage|Q|20': 'error', 'targets|P|quest|01000063': 'error',
                     'targets|P|actor|B': 'error'}
    fnv.stages, fnv.placed = {'q': {10}}, set()
    severities = {f.key: f.severity for f in quest_targets.stage_findings('P', index, built_parts, fnv, stages)
                  + quest_targets.actor_findings('P', index, built_parts, fnv, actors)}
    assert severities['targets|P|stage|Q|20'] == 'review' and severities['targets|P|actor|B'] == 'review'


def test_script_stage_calls(tmp_path):
    """Receiver and argument forms of a stage call name the quest through the script's property."""
    (tmp_path / 'S.psc').write_text('VMQ.SetStage(30)\nX.TES4SetStage(VMQ as Y, 40)\nlocal.SetStage(5)\n')
    quest = rec('QUST', OWN | 1)
    index = SimpleNamespace(attached={'s': [OWN | 1]}, script_props={'s': {'vmq': OWN | 1}}, by_fid={OWN | 1: quest})
    assert [(q, s) for q, s, _r in quest_targets.script_targets(index, tmp_path)] == [(OWN | 1, 30), (OWN | 1, 40)]


def test_dlc_voice_and_files(tmp_path):
    """Voice files of INFOs the DLC does not own, master rig and LOD paths, and unlisted files old and new."""
    index = fo4_index([rec('INFO', OWN | 0x10)])
    voice = {'sound\\voice\\d.esm\\v\\00000010_1.fuz', 'sound\\voice\\d.esm\\v\\00000011_1.fuz'}
    files = SimpleNamespace(loose=lambda: voice | {'meshes\\actors\\fnvrat\\a.hkx', 'meshes\\fnv\\x.nif'},
                            archived=dict)
    assert dlc_overrides.foreign_voice(index, files, tmp_path / 'D.esm') == ['sound\\voice\\d.esm\\v\\00000011_1.fuz']
    rig, shipped = ('meshes\\actors\\fnvrat\\',), {'meshes\\actors\\fnvrat\\a.hkx'}
    assert dlc_overrides.master_files(files, rig, (), shipped) == ['meshes\\actors\\fnvrat\\a.hkx']
    assert dlc_overrides.master_files(files, rig, (), set()) == []
    plugin = tmp_path / 'D.esm'
    (tmp_path / 'D.esm.files.txt').write_text('Meshes/fnv/listed.nif\n')
    (tmp_path / 'D.esm.build.json').write_text(json.dumps({'started': time.strftime('%Y-%m-%d %H:%M:%S')}))
    (tmp_path / 'Meshes' / 'fnv').mkdir(parents=True)
    for name in ('listed.nif', 'old.nif', 'new.nif'):
        (tmp_path / 'Meshes' / 'fnv' / name).write_bytes(b'')
    os.utime(tmp_path / 'Meshes' / 'fnv' / 'old.nif', (0, 0))
    assert dlc_overrides.unlisted_files(plugin) == (['Meshes/fnv/old.nif'], ['Meshes/fnv/new.nif'])


def test_master_rigs_are_found_loose_or_in_the_main_archive(tmp_path):
    """master_prefixes: a master's own-rig skeleton counts whether loose or packed in its Main BA2 (a deployed
    build); one Fallout 4 ships does not."""
    master = tmp_path / 'g' / 'G.esm'
    loose = tmp_path / 'g' / 'Meshes' / 'Actors' / 'FNVRat' / 'CharacterAssets' / 'skeleton.nif'
    loose.parent.mkdir(parents=True)
    loose.write_bytes(b'x')
    master.write_bytes(b'')
    write_general({'Meshes/Actors/FNVGecko/CharacterAssets/skeleton.nif': loose,
                   'Meshes/Actors/Dog/CharacterAssets/skeleton.nif': loose}, tmp_path / 'g' / 'G - Main.ba2')
    game = SimpleNamespace(where=lambda path: 'vanilla' if '\\dog\\' in path else None)
    rigs, lods = dlc_overrides.master_prefixes([master], game)
    assert rigs == ('meshes\\actors\\fnvgecko\\', 'meshes\\actors\\fnvrat\\') and lods == ()


def record(sig: bytes, fid: int, body: bytes = b'') -> bytes:
    """A plugin record: its 24-byte header, then `body`."""
    return sig + struct.pack('<IIIIHH', len(body), 0, fid, 0, 131, 0) + body


def plugin_file(path, records: dict, master: bool = True) -> None:
    """A plugin of QUSTs {FormID: data}, with master G.esm and a finished build stamp unless it is the master."""
    head = b'MAST' + struct.pack('<H', 6) + b'G.esm\0' if master else b''
    body = b''.join(record(b'QUST', fid, data) for fid, data in records.items())
    group = b'GRUP' + struct.pack('<I', 24 + len(body)) + b'QUST' + struct.pack('<iII', 0, 0, 0) + body
    path.parent.mkdir(parents=True)
    path.write_bytes(record(b'TES4', 0, head) + group)
    if master:
        path.with_name(path.name + '.build.json').write_text(json.dumps({'status': 'finished'}))


def test_dlc_overrides_shared_with_another_dlc(tmp_path):
    """A master record two DLC builds beside each other both override is an error naming the other DLC; a review
    when both copies are the master's own bytes."""
    plugin_file(tmp_path / 'g' / 'G.esm', {5: b'same', 6: b'game'}, master=False)
    plugin_file(tmp_path / 'a' / 'A.esm', {5: b'same', 6: b'mine', 7: b'x'})
    plugin_file(tmp_path / 'b' / 'B.esm', {5: b'same', 6: b'them', 8: b'y'})
    index = PluginIndex([], ('G.esm',), 'FNV_', True)
    found = dlc_overrides.shared_findings('A.esm', index, tmp_path / 'a' / 'A.esm', [tmp_path / 'g' / 'G.esm'],
                                          tmp_path / 'none')
    assert {(f.key, f.severity, f.detail) for f in found} == {
        ('dlc|A.esm|shared-identical|B.esm|QUST', 'review', ('G.esm 000005',)),
        ('dlc|A.esm|shared|B.esm|QUST', 'error', ('G.esm 000006',))}
