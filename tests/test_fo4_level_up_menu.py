"""Our level-up menu: the movie mxmlc builds, the contract between it and F3NV_LevelUp.psc, and the character rules
opening it in place of LevelUpMenu.

See: docs/fork/fo4_level_up_plan.md#menu
"""

import re
import shutil
from pathlib import Path

import pytest

from asset_convert.ui.swf import Swf
from fo4_import import level_up as M
from fo4_import.base import mxmlc
from fo4_import.base.papyrus import FO4_COMPILER, compile_folder, header_dirs

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
SCRIPT = (STATIC / 'F3NV_LevelUp.psc').read_text(encoding='utf-8')
RULES = (STATIC / 'F3NV_CharacterRules.psc').read_text(encoding='utf-8')
MOVIE = (M.SOURCES / 'F3NV_LevelUp.as').read_text(encoding='utf-8')
CHARACTER = (M.SOURCES / 'f3nv' / 'levelup' / 'Character.as').read_text(encoding='utf-8')
#: The polyfill functions the rules call, for compiling them without the assembled TES4Polyfill.
POLYFILL_STUB = ('ScriptName TES4Polyfill Hidden\nBool Function Tracing() Global\n  Return False\nEndFunction\n'
                 'Function TraceWrite(String asKind, String asText) Global\nEndFunction\n')


def _function(source: str, name: str) -> str:
    """The body of Papyrus function `name` in `source`."""
    return re.search(rf'Function {name}\(.*?EndFunction', source, re.S).group(0)


def test_the_script_opens_the_movie_the_build_installs():
    """The menu name F3NV_LevelUp.psc registers is the movie's file and document class."""
    name = re.search(r'String Property MenuName = "(\w+)"', SCRIPT).group(1)
    assert M.MOVIE == f'Interface/{name}.swf' and M.DOCUMENT == name and f'MENU:String = "{name}"' in MOVIE


def test_the_script_and_movie_agree_on_events_and_calls():
    """Every event the movie sends is one the script registers, and each root1 call the script makes is a public
    function of the movie."""
    sent = set(re.findall(r'send\("(F3NV_LevelUp\w+)"', MOVIE))
    registered = set(re.findall(r'RegisterForExternalEvent\("(\w+)"', SCRIPT))
    assert sent == registered == {'F3NV_LevelUpTake', 'F3NV_LevelUpRaise', 'F3NV_LevelUpClose', 'F3NV_LevelUpLog'}
    for call in re.findall(r'"root1\.(\w+)"', SCRIPT):
        assert re.search(rf'public function {call}\(', MOVIE), call


def test_send_hands_over_what_the_movie_reads():
    """Send fills args[0] to args[24], and Character reads 17 values then 8 requirement columns."""
    send = _function(SCRIPT, 'Send')
    assert sorted(int(n) for n in re.findall(r'args\[(\d+)\] =', send)) == list(range(25)) and 'new Var[25]' in send
    assert 'args[16]' in CHARACTER and 'readRows(args.slice(17))' in CHARACTER
    assert re.findall(r'split\(columns\[(\d)\]\)', CHARACTER) == [str(i) for i in range(8)]


def test_the_rules_open_ours_in_place_of_level_up_menu():
    """LevelUpMenu opening (not as LevelUpMenuEx's trait or tag menu, which the rules flag) closes it and the
    Pip-Boy, gives this level-up's points and opens ours; points go to F3NV_LevelUp, not PRKF."""
    opened = _function(RULES, 'OpenLevelUp')
    assert opened.index('UI.CloseMenu("LevelUpMenu")') < opened.index('TopUp()') < opened.index('LevelUp().Open()')
    assert 'UI.CloseMenu("PipboyMenu")' in opened and 'WaitOutOfMenus()' in opened
    assert 'asMenuName == "LevelUpMenu" && abOpening && !PrkfMenu' in RULES
    for opener in ('PRKF:PRKF.OpenTraitsMenuFL', 'PRKF:PRKF.OpenTagSkillsMenu'):
        before = RULES[:RULES.index(opener)]
        assert before.rstrip().endswith('PrkfMenu = True'), opener
    top_up = _function(RULES, 'TopUp')
    assert 'LevelUp().AddSkillPoints(whole)' in top_up and 'PRKF' not in top_up


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_rules_and_level_up_compile_together(tmp_path):
    """F3NV_CharacterRules.psc (calling F3NV_LevelUp) and F3NV_LevelUp.psc compile against FO4's, F4SE's and
    LevelUpMenuEx's headers."""
    src, stub, out = tmp_path / 'src', tmp_path / 'stub', tmp_path / 'out'
    for folder in (src, stub, out):
        folder.mkdir()
    (stub / 'TES4Polyfill.psc').write_text(POLYFILL_STUB, encoding='utf-8')
    for name in ('F3NV_LevelUp', 'F3NV_CharacterRules'):
        shutil.copy(STATIC / f'{name}.psc', src)
    log = compile_folder(src, out, f'{src};{stub};{STATIC};{header_dirs()}')
    assert {p.name for p in out.iterdir()} == {'F3NV_LevelUp.pex', 'F3NV_CharacterRules.pex'}, log


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_the_movie_builds_the_same_twice(tmp_path):
    """Two uncompressed, undated builds are identical and hold the menu's calls and the library."""
    raw = M.compile_movie(tmp_path / 'a.swf').read_bytes()
    assert raw == M.compile_movie(tmp_path / 'b.swf').read_bytes() and raw[:3] == b'FWS'
    assert not {t.code for t in Swf.parse(raw).tags} & set(mxmlc.DATED)
    for name in (b'F3NV_LevelUp', b'Open', b'Taken', b'Raised', b'ProcessUserEvent', b'Character', b'ScrollList'):
        assert name in raw


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_install_writes_the_movie_under_interface(tmp_path):
    """install() copies the built movie to <data>/Interface/F3NV_LevelUp.swf."""
    assert M.install(tmp_path) == 1 and (tmp_path / M.MOVIE).read_bytes()[:3] == b'FWS'
