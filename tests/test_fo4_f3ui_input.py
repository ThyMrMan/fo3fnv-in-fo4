"""f3ui's Input and HintBar: the game's controls and glyphs they rely on, and the menus taking input only through them.

See: docs/fork/swf_framework.md#input
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'fo4_import' / 'base' / 'as3' / 'f3ui'
MENUS = (ROOT / 'fo4_import' / 'casino' / 'as3' / 'F3NV_Casino.as',
         ROOT / 'fo4_import' / 'dialogue_menu' / 'as3' / 'DialogueMenu.as')
#: FO4's menu-mode controls (the control map in Fallout4.exe) and the action each should be.
MENU_CONTROLS = {'Accept': 'ACCEPT', 'Cancel': 'BACK', 'Up': 'UP', 'Down': 'DOWN', 'Left': 'LEFT', 'Right': 'RIGHT',
                 'LShoulder': 'PREV', 'RShoulder': 'NEXT', 'LTrigger': 'PREV', 'RTrigger': 'NEXT', 'XButton': 'X',
                 'YButton': 'Y', 'ZoomIn': 'UP', 'ZoomOut': 'DOWN'}
#: The controller font's letter per button (the game's button hint map), Xbox then PlayStation.
XBOX = {'accept': 'A', 'back': 'B', 'x': 'C', 'y': 'D', 'prev': 'G', 'next': 'L', 'up': 'W', 'down': 'V', 'left': 'T',
        'right': 'U'}
PLAYSTATION = {'accept': 'a', 'back': 'd', 'x': 'c', 'y': 'b', 'prev': 'g', 'next': 'm', 'up': 'w', 'down': 'v',
               'left': 't', 'right': 'u'}


def _object(source: str, name: str) -> dict:
    """The AS3 object literal `name` in `source` as {key: value}, its values strings or bare names."""
    body = re.search(rf'{name}:Object = \{{(.*?)\}};', source, re.S).group(1)
    return {k: v.strip('"') for k, v in re.findall(r'(\w+):\s*("?[\w.]+"?)', body)}


def test_the_hint_glyphs_are_the_controller_fonts_letters():
    """Each action's glyph on Xbox and PlayStation is the letter the game's controller font draws that button with."""
    source = (LIBRARY / 'HintBar.as').read_text(encoding='utf-8')
    assert _object(source, 'XBOX') == XBOX and _object(source, 'PLAYSTATION') == PLAYSTATION
    assert 'GLYPHS:String = "$Controller_Buttons"' in source


def test_input_maps_every_menu_mode_control():
    """The game's menu-mode controls each map to their action; moves fire on the press, accept and back on release."""
    source = (LIBRARY / 'Input.as').read_text(encoding='utf-8')
    assert _object(source, 'names') == MENU_CONTROLS
    moves = _object(source, 'MOVES')
    assert set(moves) == {'up', 'down', 'left', 'right', 'prev', 'next'}


def test_no_movie_calls_flash_11s_remove_children():
    """removeChildren() is Flash Player 11's; Scaleform may lack it, so our AS3 empties a container a child at a time.

    See: docs/fork/swf_framework.md#scroll-list
    """
    for path in (ROOT / 'fo4_import').rglob('*.as'):
        assert 'removeChildren(' not in path.read_text(encoding='utf-8'), path.name


def test_images_asks_the_dll_for_a_texture_by_the_name_it_registers():
    """F3NV.dll registers TextureExists on every movie of ours (opening Textures\\<path> as F4SE opens a translation
    file); Images calls it with the path MountImage takes, and treats a DLL without it as found.

    See: docs/fork/swf_framework.md#images
    """
    runtime = ROOT / 'tes_runtime' / 'fo4_condition'
    gfx = (runtime / 'gfx.cpp').read_text(encoding='utf-8')
    assert 'RegisterFunction<TextureExistsNative>(plugin, movie, "TextureExists")' in gfx
    assert 'std::string("Textures\\\\")' in gfx and 'BSResourceNiBinaryStream stream(path.c_str());' in gfx
    assert 'RegisterImageNatives(movie, plugin);' in (runtime / 'dialogue.cpp').read_text(encoding='utf-8')
    images = (LIBRARY / 'Images.as').read_text(encoding='utf-8')
    assert 'dll.TextureExists == null || dll.TextureExists(texturePath(path)) == true' in images


def test_both_lists_are_the_librarys():
    """The Pip-Boy's list panel is a Modal round a ScrollList, and the dialogue's rows are a ScrollList."""
    panel = (ROOT / 'fo4_import' / 'pipboy_overlay' / 'as3' / 'ListPanel.as').read_text(encoding='utf-8')
    assert 'new Modal()' in panel and 'new ScrollList()' in panel and 'modal.open(body' in panel
    assert 'new ScrollList()' in MENUS[1].read_text(encoding='utf-8')


def test_the_menus_take_keys_and_controls_only_through_input():
    """Neither menu listens for keys itself, and each hands the game's controls and platform to Input."""
    for menu in MENUS:
        source = menu.read_text(encoding='utf-8')
        assert 'KeyboardEvent' not in source, menu.name
        assert 'input.control(' in source and 'input.setPlatform(platform)' in source, menu.name
        assert 'new HintBar(' in source, menu.name
