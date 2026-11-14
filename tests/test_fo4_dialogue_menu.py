"""The dialogue menu on Cleanroom UI's release: the demo plugin and its links, the test mod, and the build's links
file. The movie and CleanroomDialogue.dll are tested in Cleanroom UI.

See: docs/fork/fo4_dialogue_menu_plan.md#test-build
"""

import struct
import subprocess
from pathlib import Path

import pytest

from fo4_import import cleanroom
from fo4_import import dialogue_menu as D
from fo4_import.dialogue_menu import test_mod as T
from fo4_import.spike import records as R
from tools.validate.preflight.plugin_index import every, first, load_plugin, u32


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


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A stand-in for Cleanroom UI's built files: the dialogue movie, two words files and another movie."""
    folder = tmp_path / 'crui'
    words = 'Interface/Translations/'
    for rel in ('Interface/DialogueMenu.swf', 'Interface/CRUI_Hud.swf', f'{words}CleanroomDialogue_en.txt',
                f'{words}CleanroomDialogue_de.txt', f'{words}CleanroomUI_en.txt'):
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(rel)
    monkeypatch.setattr(cleanroom, 'build', lambda: folder)
    return folder


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


def test_test_mod_ships_cleanroom_uis_dialogue_release(tmp_path, built):
    """The test mod holds the demo plugin, its links in CleanroomDialogue's folder, the DLL given, and only the
    dialogue movie and words of Cleanroom UI's build."""
    dll = tmp_path / T.DLL.name
    dll.write_bytes(b'dll')
    out = tmp_path / 'mod'
    T.build(out, dll)
    shipped = sorted(p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file())
    assert shipped == ['F3NV_MenuTest.esp', 'F4SE/Plugins/CleanroomDialogue.dll',
                       'F4SE/Plugins/CleanroomDialogue/F3NV_MenuTest.txt', 'Interface/DialogueMenu.swf',
                       'Interface/Translations/CleanroomDialogue_de.txt',
                       'Interface/Translations/CleanroomDialogue_en.txt']
    assert T.DLL == cleanroom.DIST / 'CleanroomDialogue.dll'


def test_links_move_to_cleanroom_uis_folder(tmp_path):
    """remove_legacy deletes the hub files and the plugin's own file in the old F3NV_Menus folder (and the folder
    once empty), never another plugin's."""
    old = tmp_path / D.OLD_LINKS
    old.mkdir(parents=True)
    for name in ('Mod.txt', 'F3NV_MenuHub.txt'):
        (old / name).write_text('x')
    (tmp_path / 'F3NV_MenuHub.esp').write_text('x')
    gone = D.remove_legacy(tmp_path, 'Mod.esp')
    assert sorted(p.name for p in gone) == ['F3NV_MenuHub.esp', 'F3NV_MenuHub.txt', 'Mod.txt'] and not old.exists()
    (old / 'Other.txt').parent.mkdir(parents=True)
    (old / 'Other.txt').write_text('x')
    assert D.remove_legacy(tmp_path, 'Mod.esp') == [] and (old / 'Other.txt').is_file()
    assert D.LINKS == Path('F4SE', 'Plugins', 'CleanroomDialogue')


def test_cleanroom_finds_the_main_checkout_from_the_main_checkout_and_a_worktree(monkeypatch):
    """main_checkout(): the repo, or the one above .claude/worktrees."""
    for repo, main in ((Path('D:/C/x'), Path('D:/C/x')), (Path('D:/C/x/.claude/worktrees/w'), Path('D:/C/x'))):
        monkeypatch.setattr(cleanroom, 'REPO', repo)
        assert cleanroom.main_checkout() == main


@pytest.mark.skipif(cleanroom.checkout() is None, reason='no Cleanroom UI checkout')
def test_cleanroom_scripts_come_from_the_pinned_commit_not_the_checkout():
    """scripts() reads the pinned commit's tree, so a checkout that moved past PIN never changes what a build ships
    (a newer CRUI_LevelUp once failed to compile and broke every character script)."""
    pin = cleanroom.pinned()
    assert cleanroom.source().name == pin
    for name, path in cleanroom.scripts().items():
        shown = subprocess.run(['git', '-C', str(cleanroom.checkout()), 'show', f'{pin}:papyrus/{name}'],
                               capture_output=True, check=True).stdout
        assert path.read_bytes().replace(b'\r\n', b'\n') == shown.replace(b'\r\n', b'\n'), name
