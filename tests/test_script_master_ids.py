"""The script stage's cross-reference graph states every master's FormIDs in the dependent's numbering.

See: docs/commentary/script_convert.md#master-ids-rekeyed
"""

import pytest

from core.plugin_masters import chain_index_maps
from script_convert.constants import papyrus_script_name
from script_convert.cross_ref import CrossRefGraph

#: (plugin folder, its masters, {record type: [record fields]}): two DLCs that both number their own records 01.
PLUGINS = (
    ('Game.esm', (), {'STAT': [{'FormID': '00000900', 'EditorID': 'GameRock'},
                               {'FormID': '00000014', 'EditorID': 'EngineForm'}]}),
    ('DlcA.esm', ('Game.esm',), {
        'QUST': [{'FormID': '01000010', 'EditorID': 'DlcQuest', 'SCRI': '01000011'}],
        'SCPT': [{'FormID': '01000011', 'EditorID': 'DlcQuestScript', 'SCHR.Type': '1'},
                 {'FormID': '01000015', 'EditorID': 'DlcActorScript', 'SCHR.Type': '0'}],
        'ALCH': [{'FormID': '01000012', 'EditorID': 'DlcPotion'}],
        'GLOB': [{'FormID': '01000013', 'EditorID': 'DlcGlobal', 'FNAM.Type': 's', 'FLTV.Value': '3.0'}],
        'NPC_': [{'FormID': '01000014', 'EditorID': 'DlcActor', 'SCRI': '01000015', 'AIPackage[0]': '01000016'}],
        'PACK': [{'FormID': '01000016', 'EditorID': 'DlcWander', 'PKDT.Type': '5'}],
        'REFR': [{'FormID': '01000017', 'EditorID': 'DlcRockRef', 'NAME': '00000900'}],
    }),
    ('DlcB.esm', ('Game.esm',), {
        'REFR': [{'FormID': '01000012', 'EditorID': 'OtherRef', 'NAME': '00000900'},
                 {'FormID': '01000010', 'EditorID': 'OtherRef2', 'NAME': '00000900'}],
        'ACTI': [{'FormID': '01000014', 'EditorID': 'OtherSwitch', 'SCRI': '01000015'},
                 {'FormID': '01000013', 'EditorID': 'OtherSwitch2'}],
        'SCPT': [{'FormID': '01000015', 'EditorID': 'OtherSwitchScript', 'SCHR.Type': '0'},
                 {'FormID': '01000011', 'EditorID': 'OtherScript', 'SCHR.Type': '0'}],
        'PACK': [{'FormID': '01000016', 'EditorID': 'OtherTravel', 'PKDT.Type': '6'}],
    }),
    ('Mod.esp', ('Game.esm', 'DlcA.esm', 'DlcB.esm'), {
        'QUST': [{'FormID': '01000010', 'EditorID': 'DlcQuest', 'SCRI': '01000011'}],
    }),
    ('ModSwapped.esp', ('Game.esm', 'DlcB.esm', 'DlcA.esm'), {
        'QUST': [{'FormID': '02000010', 'EditorID': 'DlcQuest', 'SCRI': '02000011'}],
    }),
    ('Thin.esp', ('DlcA.esm',), {}),
)


def _write_plugin(root, name: str, masters: tuple, records: dict) -> None:
    """One export folder: `_HEADER.txt` naming `masters`, and a text file per record type."""
    folder = root / name
    folder.mkdir()
    (folder / '_HEADER.txt').write_text(''.join(f'Master[{i}]={m}\n' for i, m in enumerate(masters)))
    for sig, recs in records.items():
        blocks = ['---RECORD_BEGIN---\nSignature=%s\n%s---RECORD_END---\n'
                  % (sig, ''.join(f'{k}={v}\n' for k, v in rec.items())) for rec in recs]
        (folder / f'{sig}.txt').write_text(''.join(blocks))


@pytest.fixture(scope='module')
def exports(tmp_path_factory):
    """The export root holding every plugin of `PLUGINS`."""
    root = tmp_path_factory.mktemp('export')
    for name, masters, records in PLUGINS:
        _write_plugin(root, name, masters, records)
    return root


def _graph(exports, name: str) -> CrossRefGraph:
    """The graph the script stage builds for plugin `name`."""
    graph = CrossRefGraph()
    graph.load_from_export(str(exports / name), workers=1)
    return graph


@pytest.fixture(scope='module', params=[('Mod.esp', '01', '02'), ('ModSwapped.esp', '02', '01')])
def mod(request, exports):
    """(a two-DLC mod's graph, DlcA's index byte, DlcB's), per master order."""
    name, a, b = request.param
    return _graph(exports, name), a, b


def test_overridden_quest_keeps_its_masters_script(mod):
    """A quest the mod overrides is still typed by its master's script."""
    graph, _a, _b = mod
    assert graph.get_quest_script_type('DlcQuest') == papyrus_script_name('DlcQuestScript')
    assert graph.get_record_script_type('DlcQuest') == papyrus_script_name('DlcQuestScript')


def test_sibling_masters_do_not_overwrite_each_other(mod):
    """A potion and a global of one DLC keep their record type though the other DLC reuses their ids."""
    graph, a, b = mod
    assert graph.edid_to_formid['dlcpotion'] == a + '000012'
    assert graph.edid_to_formid['otherref'] == b + '000012'
    assert graph.get_base_signature('DlcPotion') == 'ALCH'
    assert graph.get_base_signature('DlcGlobal') == 'GLOB'
    assert graph.global_types['dlcglobal'] == 's'
    assert graph.get_base_signature('OtherRef') == 'STAT'
    assert graph.get_base_signature('OtherSwitch2') == 'ACTI'


def test_actor_script_extends_actor(mod):
    """A script only an NPC carries extends Actor though the other DLC hangs its same-numbered script on an activator."""
    graph, a, b = mod
    assert graph.record_script_edid('DlcActor') == 'DlcActorScript'
    assert graph.get_extends_class(a + '000015') == 'Actor'
    assert graph.get_extends_class(b + '000015') == 'ObjectReference'
    assert graph.npc_formids == {a + '000014'}


def test_id_fields_follow_their_record(mod):
    """A master record's own id fields (base, package list) land in the same numbering as its key."""
    graph, a, _b = mod
    assert graph.record_base[a + '000017'] == '00000900'
    assert graph.get_actor_packages_of_type('DlcActor', 5) == ['DlcWander']
    assert graph.get_actor_packages_of_type('DlcActor', 6) == []


def test_single_master_plugin_is_left_alone(exports):
    """A DLC whose one master is the game already shares its numbering: nothing moves."""
    graph = _graph(exports, 'DlcA.esm')
    assert graph.edid_to_formid['dlcquest'] == '01000010'
    assert graph.edid_to_formid['gamerock'] == '00000900'
    assert all(theirs == ours for _folder, remap in chain_index_maps(str(exports / 'DlcA.esm'))
               for theirs, ours in remap.items())


def test_inherited_master_gets_a_slot_past_the_plugin(exports):
    """A master's master the plugin does not list sits past the plugin's own slot, never on a listed one."""
    maps = {folder.replace('\\', '/').rsplit('/', 1)[-1]: remap
            for folder, remap in chain_index_maps(str(exports / 'Thin.esp'))}
    assert maps == {'Game.esm': {0: 2}, 'DlcA.esm': {0: 2, 1: 0}}
    graph = _graph(exports, 'Thin.esp')
    assert graph.edid_to_formid['dlcpotion'] == '00000012'
    assert graph.get_base_signature('DlcRockRef') == 'STAT'
    assert graph.edid_to_formid['gamerock'] == '02000900'
    assert graph.edid_to_formid['engineform'] == '00000014'
