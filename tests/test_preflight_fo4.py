"""The preflight audits on a Fallout 4 build: VMAD fragments, the scene model, line copies, conditions, assets.

See: docs/fork/fo4_preflight.md#why
"""
import json
import struct
from types import SimpleNamespace

from fo4_import.base.vmad import info_fragments, object_scripts, quest_fragments
from tests.test_preflight_audits import export_file, zs
from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import asset_fo4, build_diff, package_ai, quest_progression, quest_start
from tools.validate.preflight import condition_diff as D
from tools.validate.preflight.fo4_dialogue import Fo4Dialogue, left_out, line_copies, line_parts
from tools.validate.preflight.plugin_index import FO4_FRAGMENT_AT, PluginIndex, vmad_scripts
from tools.validate.preflight.quest_converted import load_scripts
from tools.validate.preflight.quest_source import SourceGame

#: The own load-order index of the test plugins: one master.
OWN = 0x01000000


def rec(sig, fid, subs=(), parent_dial=0):
    """A built Fallout 4 record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs], parent_dial=parent_dial)


def fo4_index(records):
    """A Fallout 4 PluginIndex with one master."""
    return PluginIndex(records, ('Fallout4.esm',), 'FNV_', True)


def u32(value):
    """Four little-endian bytes."""
    return struct.pack('<I', value)


def test_fo4_fragment_scripts_and_object_arrays_attach():
    """An INFO's and a QUST's fragment script attach with their properties, and an object array names each form."""
    info = vmad_scripts(info_fragments('X_TIF__1', {'Q': OWN | 5}), FO4_FRAGMENT_AT['INFO'])
    quest = vmad_scripts(quest_fragments('X_QF_Q', [(10, 0, 'Fragment_Stage_0010_Item_0')], {'R': OWN | 6}),
                         FO4_FRAGMENT_AT['QUST'])
    assert info == [('x_tif__1', {'q': OWN | 5})] and quest == [('x_qf_q', {'r': OWN | 6})]
    name, prop = b'Steps', b'Playlist'
    array = (struct.pack('<hhH', 6, 2, 1) + struct.pack('<H', len(prop)) + prop + b'\0' + struct.pack('<H', 1)
             + struct.pack('<H', len(name)) + name + bytes([11, 1]) + u32(2)
             + struct.pack('<HhI', 0, -1, OWN | 7) + struct.pack('<HhI', 0, -1, OWN | 8))
    index = fo4_index([rec('QUST', OWN | 1, [('VMAD', array)])])
    assert {t for _s, _p, t in index.object_props} == {OWN | 7, OWN | 8}


def scene(fid, topic, quest=OWN | 1):
    """A SCEN whose one Dialogue action says `topic`."""
    return rec('SCEN', fid, [('FNAM', u32(0)), ('ANAM', struct.pack('<H', 0)), ('DATA', u32(topic)),
                             ('ANAM', b''), ('PNAM', u32(quest))])


def scene_plugin(named: bool):
    """Two scene topics: scene 1 (named by a script property when `named`) says A, whose line starts scene 2 (B)."""
    props = {'TES4Talk_A': OWN | 0x30} if named else {}
    return fo4_index([rec('QUST', OWN | 1, [('EDID', zs('FNV_Q')), ('VMAD', object_scripts([('X_Q', props, {})]))]),
                      rec('DIAL', OWN | 0x10, [('SNAM', b'SCEN')]), rec('DIAL', OWN | 0x11, [('SNAM', b'SCEN')]),
                      scene(OWN | 0x30, OWN | 0x10), scene(OWN | 0x31, OWN | 0x11),
                      rec('INFO', OWN | 0x20, [('TSCE', u32(OWN | 0x31))], OWN | 0x10),
                      rec('INFO', OWN | 0x21, [], OWN | 0x11)])


def test_a_scene_line_speaks_only_through_a_scene_that_starts():
    """A property starts scene 1, whose line starts scene 2; unnamed, neither plays."""
    assert Fo4Dialogue(scene_plugin(True)).reachable_info(OWN | 0x21) == ''
    assert 'in no scene that starts' in Fo4Dialogue(scene_plugin(False)).reachable_info(OWN | 0x21)


def test_talking_through_an_activator_reads_0_on_the_fnv_side():
    """FNV's IsActorTalkingThroughActivator is 0 in every sampled state, as no actor talks through one on FO4."""
    cond = {'func': D.FNV.index('IsActorTalkingThroughActivator'), 'p1': 0, 'p2': 0, 'run_on': 0, 'ref': 0}
    assert D.source_fact(cond, None, {}) == 0.0


def test_an_objective_its_quest_does_not_author_reads_0_on_the_fnv_side():
    """GetObjectiveDisplayed 50 of a quest authoring 10 and 30 is a left-out fact (reads 0), as in FNV; an authored
    one is the objective's fact."""
    shown = D.FNV.index('GetObjectiveDisplayed')
    names = SimpleNamespace(source_quest=lambda fid: ('form', 'q'), objectives={0x10431C: frozenset({10, 30})})
    cond = lambda index: {'func': shown, 'p1': 0x10431C, 'p2': index, 'run_on': 0, 'ref': 0}
    assert D.source_fact(cond(50), names, {}) is None
    assert D.source_fact(cond(30), names, {}) == (('objshown', ('form', 'q'), 30), None)


def test_a_talking_as_list_reads_0_on_the_built_side():
    """A built IsInList on a talking-as list reads 0, as FNV's IsActorTalkingThroughActivator does."""
    index = fo4_index([rec('FLST', OWN | 0x50, [('EDID', zs('TES4TalkingAs_00001234'))])])
    cond = {'func': D.FO4.index('IsInList'), 'p1': OWN | 0x50, 'p2': 0, 'run_on': 0, 'ref': 0, 'text': ''}
    assert D.built_fact(cond, SimpleNamespace(index=index)) == 0.0


def test_a_voice_holotape_starts_its_scene():
    """A voice NOTE (DNAM 1) naming scene 2 starts it, so scene 2's line can speak; a plain note does not."""
    for dnam, verdict in ((1, ''), (0, 'in no scene that starts')):
        plugin = scene_plugin(False)
        note = rec('NOTE', OWN | 0x40, [('DNAM', bytes([dnam])), ('SNAM', u32(OWN | 0x31))])
        index = fo4_index([*(r for recs in plugin.by_type.values() for r in recs), note])
        assert verdict in Fo4Dialogue(index).reachable_info(OWN | 0x21) if verdict else \
            Fo4Dialogue(index).reachable_info(OWN | 0x21) == ''


def test_a_line_whose_first_response_is_not_built_has_no_copies(tmp_path):
    """Later responses alone never play: the line maps to no copies until its first response is built."""
    index = fo4_index([rec('INFO', OWN | 0x100), rec('INFO', OWN | 0x101)])
    ledger = tmp_path / 'P.formids.tsv'
    rows = ['id\tFNV made\t"INFO 00001234 2 at 00000001 (\'part\', \'00001234\', 2)"\t000101']
    ledger.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    assert line_copies(line_parts(index, ledger, [0x1234])) == {0x1234: []}
    ledger.write_text('\n'.join(rows + ["id\tFNV made\t'INFO 00001234 1 at 00000001 topic 00000002'\t000100"]),
                      encoding='utf-8')
    assert sorted(line_copies(line_parts(index, ledger, [0x1234]))[0x1234]) == [OWN | 0x100, OWN | 0x101]


def test_the_builds_left_out_reason_is_kept(tmp_path):
    """A line the build left out reads as its readiness reason."""
    report = tmp_path / 'P.json'
    report.write_text(json.dumps([{'kind': 'line left out', 'owner': '00000001',
                                   'detail': '00001234 (condition: GetIsID: never true in this build)'}]))
    assert left_out(report) == {'00001234': 'the build left it out (condition: GetIsID: never true in this build)'}


def fact(name, form):
    """A yes/no fact on the subject about `form`."""
    return (name, D.SUBJECT, (('form', form), 0)), None


def test_the_differential_finds_a_dropped_condition_and_accepts_an_equivalent_one():
    """A faction test the copy drops is found; `== 1` against `!= 0` on a yes/no fact is the same test."""
    running = (D.running_fact(('form', 'q')), 0x00, 1.0, False)
    faction = fact('GetInFaction', 'f')
    fnv = [running, (faction, 0x00, 1.0, False)]
    state, said = D.disagreement(fnv, [running], 1, {})
    assert said is False and state[faction[0]] == 0.0
    assert D.disagreement(fnv, [running, (faction, 0x20, 0.0, False)], 1, {}) is None


def test_a_ledger_entry_for_a_reference_no_longer_built_reads_as_left_out(tmp_path):
    """The ledger keeps earlier builds' references: one whose built FormID is gone is absent, not renumbered."""
    export = tmp_path / 'export'
    export.mkdir()
    export_file(export, 'QUST', [])
    ledger = tmp_path / 'P.formids.tsv'
    ledger.write_text("id\tFNV made\t'ACHR 0000A001 STH'\t000300\nid\tFNV made\t'ACHR 0000A002 STH'\t000301\n",
                      encoding='utf-8')
    names = D.Names(fo4_index([rec('ACHR', OWN | 0x301)]), export, ledger)
    assert names.source(0xA001) is None and names.source(0xA002) == ('id', 0x301)


def test_or_chains_bind_tighter_than_and():
    """(A or B) and C: a copy that drops the OR flag requires both A and B."""
    a, b, c = fact('GetInFaction', 'a'), fact('GetInFaction', 'b'), fact('GetDead', 'c')
    fnv = [(a, 0x00, 1.0, True), (b, 0x00, 1.0, False), (c, 0x00, 0.0, False)]
    built = [(a, 0x00, 1.0, False), (b, 0x00, 1.0, False), (c, 0x00, 0.0, False)]
    assert D.disagreement(fnv, built, 1, {})[1] is True


def test_a_start_enabled_quest_the_build_lacks_is_reported_once(tmp_path):
    """An unbuilt quest is one finding, not one per stage."""
    export = tmp_path / 'export'
    export.mkdir()
    export_file(export, 'QUST', [{'FormID': '00001000', 'EditorID': 'TestQ', 'DATA.Flags': 1}])
    scripts = tmp_path / 'scripts'
    (scripts / 'source').mkdir(parents=True)
    ctx = quest_progression.QuestContext('P.esp', SourceGame(str(export)), load_scripts(scripts), fo4_index([]))
    [finding] = quest_start.start_findings(ctx)
    assert finding.key == 'start|P.esp|unbuilt|TestQ' and finding.severity == 'review'


def test_a_fo4_npc_runs_its_ai_packages_template():
    """Fallout 4 keeps template flags at ACBS byte 14 and the AI Packages template in TPTA."""
    acbs = bytes(14) + struct.pack('<H', 0x20) + bytes(4)
    tpta = bytes(20) + u32(OWN | 0x41) + bytes(28)
    index = fo4_index([rec('NPC_', OWN | 0x40, [('ACBS', acbs), ('TPTA', tpta)]),
                       rec('NPC_', OWN | 0x41, [('PKID', u32(OWN | 0x50))]), rec('PACK', OWN | 0x50)])
    held, _missing = package_ai.users(index)
    assert held[OWN | 0x50] == {OWN | 0x40, OWN | 0x41}


def test_changed_records_are_counted_by_type():
    """A record whose bytes change counts once under its signature."""
    before = fo4_index([rec('GLOB', OWN | 1, [('FLTV', b'\0' * 4)]), rec('GLOB', OWN | 2)])
    after = fo4_index([rec('GLOB', OWN | 1, [('FLTV', b'\1' * 4)]), rec('GLOB', OWN | 2)])
    snap = build_diff.snapshot(after)
    assert build_diff.changed(build_diff.contents(before), build_diff.contents(after), snap) == {'GLOB': 1}


def test_a_mesh_naming_a_missing_material_is_reported(tmp_path):
    """A placed mesh is found in the mod folder; the material it names is in no folder; the fake NIF is one the
    shader-name check cannot read."""
    mod = tmp_path / 'mods' / 'M'
    (mod / 'meshes').mkdir(parents=True)
    (mod / 'meshes' / 'a.nif').write_bytes(b'\0\0materials\\fnv\\x.bgsm\0')
    (tmp_path / 'Data').mkdir()
    index = fo4_index([rec('STAT', OWN | 1, [('MODL', zs('a.nif'))]), rec('REFR', OWN | 2, [('NAME', u32(OWN | 1))])])
    found = asset_fo4.audit('P.esp', index, mod / 'P.esp', tmp_path / 'Data', tmp_path / 'export')
    assert {f.key: f.severity for f in found} == {'assets|P.esp|material|materials\\fnv\\x.bgsm': 'error',
                                                   'assets|P.esp|unreadable|meshes\\a.nif': 'review'}
