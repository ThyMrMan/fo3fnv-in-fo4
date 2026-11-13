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
from script_convert.constants import FALLOUT4_HELPER_PLUGIN, FALLOUT4_HELPER_QUESTS

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
    assert sent == registered == {'F3NV_LevelUpTake', 'F3NV_LevelUpRaise', 'F3NV_LevelUpClose', 'F3NV_LevelUpLog',
                                  'F3NV_LevelUpTags', 'F3NV_LevelUpTraits'}
    for call in re.findall(r'"root1\.(\w+)"', SCRIPT):
        assert re.search(rf'public function {call}\(', MOVIE), call
    assert 'Function OnMenuTags(Int aiMask)' in SCRIPT and 'Function OnMenuTraits(Int aiMask, Int aiShown)' in SCRIPT
    assert 'send("F3NV_LevelUpTraits", Character.mask(who.traits, "picked"), who.traits.length)' in MOVIE


def test_built_hands_over_what_the_movie_reads():
    """Built fills args[0] to args[34] and Send hands them over; Character reads 17 values, 8 requirement columns
    (17-24), then the mode, count, bonus, the trait tables (25-31), the show-all option (32) and each table's perk
    and row counts (33, 34), which move the rows' owners and perk targets."""
    built = _function(SCRIPT, 'Built')
    assert sorted(int(n) for n in re.findall(r'args\[(\d+)\] =', built)) == list(range(35)) and 'new Var[35]' in built
    assert 'UI.Invoke(MenuName, "root1.Open", args)' in _function(SCRIPT, 'Send')
    assert 'args[16]' in CHARACTER and 'readRows(args.slice(17, 25), split(args[33]), split(args[34]))' in CHARACTER
    assert re.findall(r'split\(columns\[(\d)\]\)', CHARACTER) == [str(i) for i in range(8)]
    assert 'for each (var at:String in split(columns[7]))' in CHARACTER
    assert sorted(int(n) for n in re.findall(r'args\[(2[5-9]|3\d)\]', CHARACTER)) == list(range(25, 35))
    assert 'args[32] = ShowAllPerks' in built and 'showAll = who.showAll;' in MOVIE


def test_the_rules_gather_the_menus_data_while_the_pipboy_closes():
    """ShowOurs prepares our menu (registering it) before listening and waiting, then opens it without the settling
    wait a message box needs; Open gathers again only for a different open."""
    shown = _function(RULES, 'ShowOurs')
    assert shown.index('Prepare(aiMode, aiCount, aiBonus)') < shown.index('RegisterForMenuOpenCloseEvent(') \
        < shown.index('WaitOutOfMenus(False)') < shown.index('.Open(aiMode, aiCount, aiBonus)')
    assert 'Register()' in _function(SCRIPT, 'Prepare') and 'If !ready || mode != aiMode' in _function(SCRIPT, 'Open')
    modes = {m: int(v) for m, v in re.findall(r'Int Property (\w+)Mode = (\d)', SCRIPT)}
    assert modes == {'LevelUp': 0, 'Tags': 1, 'Traits': 2}
    assert all(f'{name}:int = {modes[mode]};' in CHARACTER
               for name, mode in (('LEVEL_UP', 'LevelUp'), ('TAGS', 'Tags'), ('TRAITS', 'Traits')))


def test_the_rules_open_ours_in_place_of_level_up_menu():
    """LevelUpMenu opening closes it and the Pip-Boy, gives this level-up's points and opens ours; points go to
    F3NV_LevelUp, and LevelUpMenuEx's menus are never opened."""
    opened = _function(RULES, 'OpenLevelUp')
    assert opened.index('UI.CloseMenu("LevelUpMenu")') < opened.index('TopUp()') < opened.index('ShowOurs(')
    assert 'UI.CloseMenu("PipboyMenu")' in opened and 'WaitOutOfMenus(False)' in _function(RULES, 'ShowOurs')
    assert 'asMenuName == "LevelUpMenu" && abOpening' in RULES and 'PRKF:PRKF.Open' not in RULES
    top_up = _function(RULES, 'TopUp')
    assert 'LevelUp().AddSkillPoints(whole)' in top_up and 'PRKF' not in top_up


def test_the_tag_and_trait_menus_are_ours():
    """Our menu is the tag menu (count, bonus) and the trait menu (count, 0)."""
    assert 'ShowOurs(LevelUp().TagsMode, count, TagBonus)' in _function(RULES, 'OpenTags')
    assert 'ShowOurs(LevelUp().TraitsMode, count, 0)' in _function(RULES, 'OpenTraits') and 'OpenTraits(0)' in RULES


def test_level_up_menu_ex_is_reached_only_by_name_and_only_while_loaded():
    """No script compiles against LevelUpMenuEx: the rules call PRKF:PRKF by name (Prkf, CallGlobalFunction), only
    from MovePrkf, and only while PRKF.dll is loaded; nothing else names it."""
    assert 'PRKF:PRKF.' not in RULES and 'Utility.CallGlobalFunction("PRKF:PRKF"' in _function(RULES, 'Prkf')
    callers = {m.start() for m in re.finditer(r'\bPrkf\(', RULES)} - {RULES.index('Var Function Prkf(') + 13}
    moved = re.search(r'Function MovePrkf\(.*?EndFunction', RULES, re.S).span()
    assert callers and all(moved[0] < at < moved[1] for at in callers)
    assert 'If Migrated || F4SE.GetPluginVersion("PRKF") < 0' in _function(RULES, 'MovePrkf')
    for name in ('F3NV_LevelUp', 'F3NV_LevelUpTable', 'F3NV_CharacterEvents'):
        assert 'PRKF:' not in (STATIC / f'{name}.psc').read_text(encoding='utf-8'), name
    assert 'LevelUpMenuEx' not in header_dirs()


def test_each_tag_gets_its_bonus_once_and_keeps_it():
    """A skill tagged in the tag menu without its bonus gets TagBonus, one untagged loses it; SPECIAL set again
    keeps it; the suggestions are done with."""
    chosen = re.search(r'Event F3NV_LevelUp\.TagsChosen\(.*?EndEvent', RULES, re.S).group(0)
    assert 'tagged && !HasBonus(skills[i])' in chosen and '+ TagBonus' in chosen and '- TagBonus' in chosen
    assert 'TES4CharacterEvents.Suggested = new ActorValue[0]' in chosen
    assert 'If HasBonus(skill)' in _function(RULES, 'SetSkillBases')
    assert 'SendCustomEvent("TagsChosen"' in _function(SCRIPT, 'OnMenuTags')


def test_other_mods_reach_the_level_up_through_the_helper_plugin():
    """Get() reads the character events quest of FalloutHelpers.esl, which the level-up announces itself to as the
    rules start and as our menu registers."""
    get = _function(SCRIPT, 'Get')
    quest = FALLOUT4_HELPER_QUESTS['F3NV_CharacterEvents']
    assert f'Game.GetFormFromFile(0x{quest:X}, "{FALLOUT4_HELPER_PLUGIN}") as F3NV_CharacterEvents' in get
    assert 'Announce()' in _function(SCRIPT, 'Register') and 'LevelUp().Announce()' in RULES


def test_the_api_opens_each_menu_through_the_rules():
    """OpenLevelUpMenu, OpenTagMenu and OpenTraitMenu call the rules' openers, which exist."""
    for api, rules in (('OpenLevelUpMenu', 'OpenLevelUp()'), ('OpenTagMenu', 'OpenTags(aiTags)'),
                       ('OpenTraitMenu', 'OpenTraits(aiTraits)')):
        assert f'Rules().{rules}' in _function(SCRIPT, api)
        assert f'Function {rules.split("(")[0]}(' in RULES


def test_the_api_sends_its_events():
    """SkillRaised as points raise a skill, MenuClosed as our menu closes, each declared."""
    for event, function in (('SkillRaised', 'RaiseSkill'), ('MenuClosed', None)):
        assert f'CustomEvent {event}' in SCRIPT
        body = _function(SCRIPT, function) if function else re.search(
            r'Event OnMenuOpenCloseEvent\(.*?EndEvent', SCRIPT, re.S).group(0)
        assert f'SendCustomEvent("{event}", args)' in body


def test_an_added_perk_is_described_and_tested_by_the_game():
    """DescribeAdded fills every perk and row text (Text's 0-4, 8-14) for an added perk, its one row of kind 4,
    which the movie's GAME kind is, listed as passed after every table's rows when the game's test passes."""
    described = _function(SCRIPT, 'DescribeAdded')
    filled = sorted(int(n) for n in re.findall(r'AddPart\((\d+),', described))
    assert filled == [*range(5), *range(8, 15)] and 'AddPart(9, "4", j)' in described
    assert '"" + (tableRows + j)' in described
    assert 'public static const GAME:int = 4;' in CHARACTER and '"$F3NV_LU_OWN_TEST"' in CHARACTER


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_character_scripts_compile_together(tmp_path):
    """F3NV_CharacterRules.psc, F3NV_LevelUp.psc, F3NV_LevelUpTable.psc and F3NV_CharacterEvents.psc (which holds
    the tags) compile against FO4's and F4SE's headers alone."""
    src, stub, out = tmp_path / 'src', tmp_path / 'stub', tmp_path / 'out'
    for folder in (src, stub, out):
        folder.mkdir()
    (stub / 'TES4Polyfill.psc').write_text(POLYFILL_STUB, encoding='utf-8')
    names = ('F3NV_LevelUp', 'F3NV_LevelUpTable', 'F3NV_CharacterRules', 'F3NV_CharacterEvents')
    for name in names:
        shutil.copy(STATIC / f'{name}.psc', src)
    log = compile_folder(src, out, f'{src};{stub};{STATIC};{header_dirs()}')
    assert {p.name for p in out.iterdir()} == {f'{n}.pex' for n in names}, log


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
