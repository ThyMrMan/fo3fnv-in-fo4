"""Our dialogue menu: the demo plugin and its links, the build's links file, and the movie.

See: docs/fork/fo4_dialogue_menu_plan.md#test-build
"""

import re
import struct
import zlib
from pathlib import Path

import pytest

from asset_convert.ui.swf import Swf
from fo4_import.base import swf_skeleton as S
from fo4_import.dialogue_menu import movie as M
from fo4_import.dialogue_menu import test_mod as T
from fo4_import.spike import records as R
from tools.validate.preflight.plugin_index import every, first, load_plugin, u32


#: The menu's ActionScript source and F3NV.dll's dialogue hooks.
MENU_AS = Path(M.__file__).parent / 'as3' / 'DialogueMenu.as'
DIALOGUE_CPP = Path(__file__).parents[1] / 'tes_runtime' / 'fo4_condition' / 'dialogue.cpp'


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


def test_npc_slot_gets_the_same_answer_on_every_ask():
    """The engine asks the NPC slot each frame until the NPC can speak; each ask of that action gets the picked line.

    See: docs/fork/fo4_dialogue_menu_plan.md#answer-retries
    """
    source = DIALOGUE_CPP.read_text(encoding='utf-8')
    assert 'if (picked.line) return Again(picked, action, scene);' in source
    assert 'if (picked.answeredBy != action) return nullptr;' in source and 'return picked.line;' in source
    assert 'REFR_MODEL_STATE = 0x10A' in source and 'answered = true' not in source


def test_prompts_write_out_the_players_macros_and_gray_on_the_answer_line():
    """&PCName; / &PCRace; (any case, or &amp;-escaped) become the player's; said follows the answer line, not the option.

    See: docs/fork/fo4_dialogue_menu_plan.md#prompt-macros
    """
    source = DIALOGUE_CPP.read_text(encoding='utf-8')
    assert 'if (name == "pcname")' in source and 'if (name == "pcrace")' in source
    assert 'if (name == "amp") name = MacroName(text, end + 1, &end);' in source
    assert 'Expanded(own && *own ? own : Prompt(info)), At<UInt8>(line, INFO_SAID) != 0' in source


def test_unused_rows_leave_the_holder_so_the_backdrop_fits():
    """A hidden row still counts in the holder's bounds that size the backdrop.

    See: docs/fork/fo4_dialogue_menu_plan.md#backdrop-rows
    """
    menu = MENU_AS.read_text(encoding='utf-8')
    assert 'if(i >= count && row.parent != null)' in menu and 'row.parent.removeChild(row);' in menu


def test_wheel_scrolls_the_list_and_skips_the_camera():
    """The movie moves on ZoomIn/ZoomOut; F3NV.dll refuses them at the first- and third-person cameras' tests."""
    source = DIALOGUE_CPP.read_text(encoding='utf-8')
    assert '"ZoomIn"' in MENU_AS.read_text(encoding='utf-8')
    for rva in ('0x25AAB08', '0x10213E0', '0x2522A88', '0x102DFC0'):
        assert rva in source
    assert 'CAMERA_ZOOM' not in source


def test_movie_sources_use_no_bethesda_classes():
    """Every import is Flash's own: nothing from the game's movies.

    See: docs/fork/fo4_dialogue_menu_plan.md#own-movie
    """
    for path in M.SOURCES.rglob('*.as'):
        imports = re.findall(r'^\s*import ([\w.]+);', path.read_text(encoding='utf-8'), re.M)
        assert all(name.startswith('flash.') for name in imports), (path.name, imports)


def test_the_skeleton_is_an_as3_movie_whose_document_class_is_the_first_shell():
    """FileAttributes says AS3, DoABC2 holds an ABC 46.16 naming every class, SymbolClass makes the first the root."""
    tags = {tag.code: tag.data for tag in Swf.parse(S.skeleton(['DialogueMenuRoot', 'f3ui.dialogue.X'])).tags}
    assert struct.unpack('<I', tags[S.FILE_ATTRIBUTES])[0] & S.AS3_FLAG
    abc = tags[S.DO_ABC2][5:]
    assert struct.unpack_from('<HH', abc) == (16, 46)
    assert b'DialogueMenuRoot' in abc and b'f3ui.dialogue' in abc and b'X' in abc
    assert tags[S.SYMBOL_CLASS] == struct.pack('<HH', 1, 0) + b'DialogueMenuRoot\x00'


def test_u30_writes_seven_bits_a_byte_low_first():
    """ABC's variable-length integers."""
    assert (S.u30(0), S.u30(0x7F), S.u30(0x80), S.u30(300)) == (b'\x00', b'\x7f', b'\x80\x01', b'\xac\x02')


def test_the_document_class_comes_first_and_packages_are_dotted(tmp_path):
    """class_names: the document class first, x/Y.as as x.Y."""
    (tmp_path / 'f3ui' / 'x').mkdir(parents=True)
    for rel in ('A.as', 'DialogueMenuRoot.as', 'f3ui/x/Y.as'):
        (tmp_path / rel).write_text('', encoding='utf-8')
    assert S.class_names(tmp_path, M.DOCUMENT) == ['DialogueMenuRoot', 'A', 'f3ui.x.Y']


@pytest.mark.skipif(not M.FFDEC.is_file(), reason='needs FFDec')
def test_movie_builds_the_same_twice_with_the_menu_at_root_menu_mc(tmp_path):
    """Two builds are identical; the root holds Menu_mc, whose code registers the holders and calls the DLL."""
    raw = M.compile_movie(tmp_path / 'a.swf').read_bytes()
    assert raw == M.compile_movie(tmp_path / 'b.swf').read_bytes()
    body = zlib.decompress(raw[8:]) if raw[:3] == b'CWS' else raw
    for name in (b'DialogueMenuRoot', b'Menu_mc', b'registerObjects', b'GetDialogueOptions', b'SelectDialogueOption',
                 b'onF4SEObjCreated', b'QuickkeyUp'):
        assert name in body
