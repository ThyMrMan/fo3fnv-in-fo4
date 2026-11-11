"""The dialogue menu check over a tiny built plugin and its links file, and the Greeting TSCE check.

See: docs/fork/fo4_dialogue_menu_plan.md#converter
"""

import struct
from types import SimpleNamespace

from fo4_import.dialogue_menu import LINKS, rows, write_links
from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import menus as M
from tools.validate.preflight.dialogue_rules import tsce_greetings
from tools.validate.preflight.plugin_index import PluginIndex

#: Own forms: a scene, its player topic, two options, an answer topic, its line, an empty topic, an actor value.
SCENE, PLAYER, OPTION, OTHER, ANSWER, LINE, EMPTY, SPEECH = (0x01000800 + i for i in range(8))
PLUGIN = 'Test.esm'


def rec(sig, fid, subs=(), parent_dial=0):
    """A built record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs], parent_dial=parent_dial)


def plugin() -> PluginIndex:
    """A plugin whose one menu offers OPTION and OTHER; ANSWER holds LINE, EMPTY holds nothing."""
    menu = [('PTOP', struct.pack('<I', PLAYER))] + [(s, bytes(4)) for s in M.PLAYER_TOPICS[1:]]
    records = [rec('SCEN', SCENE, menu), rec('DIAL', PLAYER), rec('DIAL', ANSWER), rec('DIAL', EMPTY),
               rec('INFO', OPTION, parent_dial=PLAYER), rec('INFO', OTHER, parent_dial=PLAYER),
               rec('INFO', LINE, parent_dial=ANSWER), rec('AVIF', SPEECH)]
    return PluginIndex(records, ['Fallout4.esm'], fo4=True)


def kinds(tmp_path, links: list, checks: list = ()) -> set:
    """The check's finding kinds with a links file of `links` and `checks`."""
    built = tmp_path / PLUGIN
    write_links(tmp_path / LINKS / 'Test.txt', rows(['Fallout4.esm', PLUGIN], links, list(checks)))
    return {f.key.split('|')[3] for f in M.audit(PLUGIN, plugin(), built, [])}


def test_every_option_linked_to_an_answer_with_a_line_passes(tmp_path):
    """Both options linked to a topic with a line, a check on it: no finding."""
    assert kinds(tmp_path, [(OPTION, ANSWER), (OTHER, ANSWER)], [(LINE, SPEECH, 25)]) == set()


def test_faults_of_the_links_file_are_found(tmp_path):
    """An option left out, a link from no option, to an empty topic, to a line, and a check on a topic."""
    found = kinds(tmp_path, [(OPTION, EMPTY), (LINE, ANSWER), (OTHER, LINE)], [(ANSWER, SPEECH, 25)])
    assert found == {'link from no menu option', 'answer topic with no line', 'link to no answer topic',
                     'skill check on a missing form'}
    assert kinds(tmp_path, [(OPTION, ANSWER)]) == {'option without a link'}


def test_menus_without_a_links_file_are_found(tmp_path):
    """No links file beside a plugin with menus: F3NV.dll lists none of its options."""
    found = M.audit(PLUGIN, plugin(), tmp_path / PLUGIN, [])
    assert [f.key.split('|')[3] for f in found] == ['no links file']


def test_a_masters_answer_topic_counts_its_lines(tmp_path, monkeypatch):
    """A link to a master's answer topic (a DLC reusing it in place) is checked in that master's own numbering."""
    master = PluginIndex([rec('DIAL', 0x01000900), rec('INFO', 0x01000901, parent_dial=0x01000900)], ['Fallout4.esm'])
    monkeypatch.setattr(M, 'load_plugin', lambda path: master)
    records = M.Records(SimpleNamespace(by_fid={}, by_type={'INFO': []}, masters=('Fallout4.esm', 'Game.esm')),
                        [tmp_path / 'Game.esm'])
    assert records.get(0x01000900).type == 'DIAL' and records.lines(0x01000900) == 1
    assert records.lines(0x01000902) == 0


def test_a_greeting_line_starting_its_scene_by_tsce_is_found():
    """A Greeting line's TSCE cannot start a scene left playing; a plugin without one passes."""
    greet = rec('DIAL', 0x0C000010, [('SNAM', b'GREE')])
    starter = rec('INFO', 0x0D000010, [('TSCE', struct.pack('<I', SCENE))], parent_dial=0x0C000010)
    found = tsce_greetings(PLUGIN, PluginIndex([greet, starter], fo4=True))
    assert [f.key.split('|')[2] for f in found] == ['greeting by TSCE']
    assert tsce_greetings(PLUGIN, PluginIndex([greet], fo4=True)) == []
