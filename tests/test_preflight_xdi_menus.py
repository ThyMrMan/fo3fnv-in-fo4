"""The XDI menu audit: menus that can open showing only "dialogueentry"."""

import struct

from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import xdi_menus
from tools.validate.preflight.plugin_index import PluginIndex

#: Two NPCs; a scene; its four player topics and NPC topic; a topic holding the line that starts the scene.
GUARD, BARTENDER, SCENE, OPENERS = 0x0A000001, 0x0A000002, 0x0B000001, 0x0C000009
P0, P1, P2, P3, NPC_TOPIC = 0x0C000001, 0x0C000002, 0x0C000003, 0x0C000004, 0x0C000005


def rec(sig, fid, subs=(), parent_dial=0):
    """A built record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs], parent_dial=parent_dial)


def is_id(npc: int, run_on: int) -> tuple:
    """A CTDA: GetIsID(npc) == 1 run on `run_on` (0 the subject, 1 the target)."""
    return 'CTDA', struct.pack('<B3xfH2xIIIIi', 0, 1.0, 72, npc, 0, run_on, 0, -1)


def option(fid: int, text: str, npc: int, flags: int = 0) -> TES5Record:
    """A player line `text` (a pad when empty) answered while the target is `npc`."""
    said = [('TRDA', bytes(20)), ('NAM1', text.encode() + b'\0'), ('RNAM', text.encode() + b'\0')] if text else []
    return rec('INFO', fid, [('ENAM', struct.pack('<HH', flags, 0))] + said + [is_id(npc, 1)], parent_dial=P0)


def plugin(options: list, opener_npc: 'int | None' = GUARD) -> PluginIndex:
    """A plugin: a menu scene whose P0 holds `options`, started by a line said by `opener_npc` (None: nothing)."""
    menu = [('SNAM', struct.pack('<I', 0))] + [(sig, struct.pack('<I', t)) for sig, t in
                                               zip(xdi_menus.PLAYER_TOPICS, (P0, P1, P2, P3))]
    scene = rec('SCEN', SCENE, [('EDID', b'Menu\0')] + menu + [('NPOT', struct.pack('<I', NPC_TOPIC))])
    opener = [rec('INFO', 0x0D000001, [is_id(opener_npc, 0), ('TSCE', struct.pack('<I', SCENE))],
                  parent_dial=OPENERS)] if opener_npc else []
    return PluginIndex([scene] + options + opener, fo4=True)


def kinds(index) -> dict:
    """{finding kind: severity} of the audit over `index`."""
    return {f.key.split('|')[3]: f.severity for f in xdi_menus.audit('Test.esm', index)}


def test_a_menu_with_no_option_for_the_npc_who_opens_it_is_found():
    """Gomorrah's bartender opens a menu only the entrance guard answers."""
    assert kinds(plugin([option(1, 'Who are you?', GUARD)], opener_npc=BARTENDER)) == {
        'no option for its speaker': 'error'}
    assert kinds(plugin([option(1, 'Who are you?', GUARD)])) == {}


def test_pads_are_never_options_and_an_empty_menu_shows_only_dialogueentry():
    """XDI skips a line with no response (a pad); a menu of pads alone has no option, an error when a line
    starts it and review when nothing does."""
    pads = [option(1, '', GUARD), option(2, '', GUARD)]
    assert kinds(plugin(pads)) == {'no option': 'error'}
    assert kinds(plugin(pads, opener_npc=None)) == {'no option, nothing starts it': 'review'}
    assert kinds(plugin([option(1, 'Hi.', GUARD), option(2, '', BARTENDER)])) == {}


def test_a_greeting_line_starting_its_scene_by_tsce_is_found():
    """A Greeting line's TSCE cannot start a scene left playing, so every later talk would show only
    "dialogueentry"; a starter opening it by script passes."""
    greet = rec('DIAL', 0x0C000010, [('SNAM', b'GREE')])
    starter = rec('INFO', 0x0D000010, [('TSCE', struct.pack('<I', SCENE))], parent_dial=0x0C000010)
    found = xdi_menus.tsce_greetings('Test.esm', PluginIndex([greet, starter], fo4=True))
    assert [f.key.split('|')[3] for f in found] == ['greeting by TSCE']
    assert xdi_menus.tsce_greetings('Test.esm', PluginIndex([greet], fo4=True)) == []


def test_a_say_once_option_is_found():
    """FO4's Say Once on a player line drops it once said, which can empty the menu."""
    assert kinds(plugin([option(1, 'What are Powder Gangers?', GUARD, flags=0x4)])) == {'say once option': 'error'}
