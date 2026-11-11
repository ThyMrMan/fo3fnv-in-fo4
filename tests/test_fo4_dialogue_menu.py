"""Our dialogue menu: the demo plugin and its links, XDI's pairing rule, the menu rebuild, and the movie.

See: docs/fork/fo4_dialogue_menu_plan.md#test-build
"""

import re
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.dialogue_menu import movie as M
from fo4_import.dialogue_menu import test_mod as T
from fo4_import.spike import records as R
from tools.dialog import menu_rebuild as MR
from tools.validate.preflight.plugin_index import every, first, load_plugin, u32
from tools.validate.preflight.xdi_menus import pair_lines


#: The menu's ActionScript source and F3NV.dll's dialogue hooks.
MENU_AS = Path(M.__file__).parent / 'as3' / 'DialogueMenu.as'
DIALOGUE_CPP = Path(__file__).parents[1] / 'tes_runtime' / 'fo4_condition' / 'dialogue.cpp'


def _sub(sig: str, data: bytes) -> SimpleNamespace:
    """A subrecord."""
    return SimpleNamespace(type=sig, data=data)


def _line(fid: int, text: str = '') -> SimpleNamespace:
    """An INFO with one response `text`, or none."""
    return SimpleNamespace(form_id=fid, subrecords=[_sub('NAM1', text.encode() + b'\0')] if text else [])


@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    """(PluginIndex of the demo plugin, {option FormID: answer topic FormID}) as test_mod writes them."""
    out = tmp_path_factory.mktemp('demo')
    rows = T.demo_plugin(out / T.DEMO)
    path = T.write_links(out / T.LINKS / 'demo.txt', rows)
    links = {}
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        _, option, _, answer = line.split('\t')
        links[1 << 24 | int(option, 16)] = 1 << 24 | int(answer, 16)
    return load_plugin(str(out / T.DEMO)), links


def test_demo_links_name_listed_options_and_answer_topics(demo):
    """Each link: an option INFO in the menu's first player topic, with a prompt; an answer DIAL with lines."""
    index, links = demo
    p0 = next(d.form_id for d in index.by_type['DIAL'] if index.edid(d.form_id) == 'F3NVMenuTest_P0')
    assert len(links) == len(T.DEMO_OPTIONS)
    for option, answer in links.items():
        assert index.by_fid[option].parent_dial == p0
        assert first(index.by_fid[option], 'RNAM')
        assert index.by_fid[answer].type == 'DIAL'
        assert any(i.parent_dial == answer for i in index.by_type['INFO'])


def test_demo_options_gated_by_the_global(demo):
    """Only the 'global is 2' option carries a condition; its answer lines restart the menu unless they end it."""
    index, links = demo
    gated = [o for o in links if every(index.by_fid[o], 'CTDA')]
    assert len(gated) == sum(1 for o in T.DEMO_OPTIONS if o[2])
    menu = next(s.form_id for s in index.by_type['SCEN'])
    for info in (i for i in index.by_type['INFO'] if i.parent_dial in links.values()):
        flags = struct.unpack_from('<H', first(info, 'ENAM'))[0]
        assert bool(flags & R.INFO_END_SCENE) != (u32(first(info, 'TSCE')) == menu)


def test_pair_lines_follows_xdi_range_rule():
    """A listed player line owns the NPC lines up to the next listed one; an empty one is its pad."""
    player = [_line(1, 'a'), _line(2), _line(3, 'b')]
    npc = [_line(10, 'x'), _line(11, 'y'), _line(12, 'z')]
    pairs = [(o.form_id, [p.form_id for p in pads], [a.form_id for a in ans]) for o, pads, ans in pair_lines(player, npc)]
    assert pairs == [(1, [2], [10, 11]), (3, [], [12])]


def test_numbered_needs_each_plugins_masters_as_a_prefix():
    """The load order's names come from the last plugin; a plugin out of order is refused."""
    game = ('Game.esm', SimpleNamespace(masters=['Fallout4.esm']))
    mod = ('Mod.esm', SimpleNamespace(masters=['Fallout4.esm', 'Game.esm']))
    assert MR.numbered([game, mod]) == ['Fallout4.esm', 'Game.esm', 'Mod.esm']
    with pytest.raises(ValueError):
        MR.numbered([('Other.esm', SimpleNamespace(masters=['Fallout4.esm'])), mod])


def test_shared_copy_drops_responses_and_shares_the_line():
    """The copy keeps conditions and flags, drops the response text, and names the original by DNAM after ENAM."""
    answer = SimpleNamespace(form_id=0x03000123, flags=0, subrecords=[
        _sub('ENAM', b'\x44\0\0\0'), _sub('TRDA', b'\0' * 20), _sub('NAM1', b'Vale\0'), _sub('CTDA', b'\0' * 32)])
    raw = MR.shared_copy(answer, 0x0A000800)
    assert b'Vale' not in raw and b'TRDA' not in raw and b'CTDA' in raw
    assert raw.index(b'DNAM') > raw.index(b'ENAM')
    assert struct.unpack_from('<I', raw, raw.index(b'DNAM') + 6)[0] == answer.form_id


def test_rebuild_takes_every_scene_once_as_its_winner():
    """Every scene of the load order, a master's overridden by the mod's record, none twice (no hub reach)."""
    game_scene, mod_override, mod_own = (SimpleNamespace(form_id=f) for f in (0x03000001, 0x03000001, 0x04000002))
    game = SimpleNamespace(by_type={'SCEN': [game_scene]}, by_fid={0x03000001: game_scene})
    mod = SimpleNamespace(by_type={'SCEN': [mod_override, mod_own]},
                          by_fid={0x03000001: mod_override, 0x04000002: mod_own})
    assert MR.scenes([game, mod]) == [mod_override, mod_own]


def _value_test(op: int, value: float, av: int, run_on: int = MR.TARGET) -> bytes:
    """A GetValue condition's data on actor value `av`."""
    return R.pack_ctda(op, value, MR.GET_VALUE, av, run_on=run_on)[6:]


def _answer(*conditions: bytes) -> SimpleNamespace:
    """An INFO with `conditions`."""
    return SimpleNamespace(form_id=2, subrecords=[_sub('CTDA', c) for c in conditions])


def test_skill_check_is_the_answer_condition_matching_the_prompt_tag():
    """An option's check is the answer's GetValue test on the player that the prompt's tag number names."""
    speech, sneak = 0x0100081C, 0x01000810
    option = SimpleNamespace(form_id=1, subrecords=[_sub('RNAM', b'[Speech 25] Trust me.\0')])
    assert MR.skill_check(option, [_answer(_value_test(0x60, 25.0, speech))]) == (speech, 25)
    both = _answer(_value_test(0x40, 24.0, sneak), _value_test(0x60, 25.0, speech))
    assert MR.skill_check(option, [both]) == (sneak, 25)
    assert MR.skill_check(option, [_answer(_value_test(0x40, 20.0, speech))]) == ()
    assert MR.skill_check(option, [_answer(_value_test(0x60, 25.0, speech, run_on=0))]) == ()
    untagged = SimpleNamespace(form_id=1, subrecords=[_sub('RNAM', b'Trust me.\0')])
    assert MR.skill_check(untagged, [_answer(_value_test(0x60, 25.0, speech))]) == ()


def test_movie_draws_only_white_so_the_hud_color_shows():
    """Every fill is white, never a black backdrop (it would draw opaque).

    See: docs/fork/fo4_dialogue_menu_plan.md#as-built
    """
    fills = re.findall(r'beginFill\(([^,]+),', MENU_AS.read_text(encoding='utf-8'))
    assert fills and set(fills) == {'0xFFFFFF'}


def test_backdrop_is_the_games_shaded_background():
    """The backdrop is the engine's shaded background, never a fill.

    See: docs/fork/fo4_dialogue_menu_plan.md#as-built
    """
    source = DIALOGUE_CPP.read_text(encoding='utf-8')
    assert 'dll.ShadeList(on)' in MENU_AS.read_text(encoding='utf-8')
    assert 'EnableShadedBackground(0x1B04350)' in source and 'MENU_QUESTION_TARGET = 0xF8' in source


def test_failed_skill_checks_show_fnv_tags_in_the_hard_tint():
    """FNV's tags ([Speech 25] / [Sneak 17/25], two spaces after), failed rows in the Negative holder's Hard tint.

    See: docs/fork/fo4_dialogue_menu_plan.md#skill-checks
    """
    source, menu = DIALOGUE_CPP.read_text(encoding='utf-8'), MENU_AS.read_text(encoding='utf-8')
    assert '"[%s %d/%u]  "' in source and '"[%s %u]  "' in source
    assert 'TintChallenge(0x1043EF0)' in source and 'CHALLENGE_HARD = 3' in source
    assert 'MENU_NEGATIVE_TARGET = 0xE8' in source
    assert 'FadeHolder_mc.Negative.addChild(this.failedRows)' in menu and 'dll.TintFailed()' in menu


def test_movie_shows_escaped_prompts_as_written():
    """The build's &lt; &gt; &amp; show as < > & in the menu.

    See: docs/fork/fo4_pipeline.md#xdi-html
    """
    menu = MENU_AS.read_text(encoding='utf-8')
    assert 'split("&lt;").join("<").split("&gt;").join(">").split("&amp;").join("&")' in menu
    assert 'this.unescaped(String(options[i].text))' in menu and 'text = this.unescaped(text);' in menu


def test_wheel_scrolls_the_list_and_skips_the_camera():
    """The movie moves on ZoomIn/ZoomOut; F3NV.dll refuses them at the first- and third-person cameras' tests."""
    source = DIALOGUE_CPP.read_text(encoding='utf-8')
    assert '"ZoomIn"' in MENU_AS.read_text(encoding='utf-8')
    for rva in ('0x25AAB08', '0x10213E0', '0x2522A88', '0x102DFC0'):
        assert rva in source
    assert 'CAMERA_ZOOM' not in source


@pytest.mark.skipif(not M.FFDEC.is_file() or not (FALLOUT4_DIR / 'Data' / M.ARCHIVE).is_file(),
                    reason='needs FFDec and the Fallout 4 Interface archive')
def test_movie_carries_our_menu():
    """The built movie's code calls the DLL's natives and handles the game's list keys."""
    raw = M.built_movie().read_bytes()
    body = zlib.decompress(raw[8:]) if raw[:3] == b'CWS' else raw
    for name in (b'GetDialogueOptions', b'SelectDialogueOption', b'onF4SEObjCreated', b'QuickkeyUp'):
        assert name in body
