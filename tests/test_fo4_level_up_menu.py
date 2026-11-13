"""Our character rules on Cleanroom UI's level-up: the rules and F3NV_CharacterEvents against its CRUI_LevelUp.psc
and CRUI_LevelUpHolder.psc, and the build installing its movie and words. The movie's contract with its script is
tested in Cleanroom UI.

See: docs/fork/fo4_level_up_plan.md#menu
"""

import re
import shutil
from pathlib import Path

import pytest

from fo4_import import cleanroom
from fo4_import import level_up as M
from fo4_import.base.papyrus import FO4_COMPILER, compile_folder, header_dirs
from fo4_import.spike import character
from fo4_import.spike.level_up import LEGACY_SCRIPT

if cleanroom.checkout() is None:
    pytest.skip('no Cleanroom UI checkout', allow_module_level=True)

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
CLEANROOM = cleanroom.scripts()
SCRIPT = CLEANROOM['CRUI_LevelUp.psc'].read_text(encoding='utf-8')
RULES = (STATIC / 'F3NV_CharacterRules.psc').read_text(encoding='utf-8')
EVENTS = (STATIC / 'F3NV_CharacterEvents.psc').read_text(encoding='utf-8')
#: The polyfill functions the rules call, for compiling them without the assembled TES4Polyfill.
POLYFILL_STUB = ('ScriptName TES4Polyfill Hidden\nBool Function Tracing() Global\n  Return False\nEndFunction\n'
                 'Function TraceWrite(String asKind, String asText) Global\nEndFunction\n')


def _function(source: str, name: str) -> str:
    """The body of Papyrus function `name` in `source`."""
    return re.search(rf'Function {name}\(.*?EndFunction', source, re.S).group(0)


def _variables(source: str) -> set:
    """The names of the script-level variables and Auto properties in Papyrus `source`."""
    code = re.sub(r'\{.*?\}', '', source, flags=re.S)
    return set(re.findall(r'^(?:Int|Bool|Float|String|Perk|Var)(?:\[\])?[ \t]+(?:Property[ \t]+)?(\w+)(?![ \t]*\()',
                          code, re.M))


def test_the_build_installs_the_movie_the_script_opens(tmp_path, monkeypatch):
    """install() copies the movie CRUI_LevelUp.psc opens and CleanroomUI's words from Cleanroom UI's build, and
    deletes an older build's F3NV_LevelUp.swf."""
    name = re.search(r'String Property MenuName = "(\w+)"', SCRIPT).group(1)
    built = tmp_path / 'crui'
    for rel in (f'Interface/{name}.swf', 'Interface/Translations/CleanroomUI_en.txt', 'Interface/DialogueMenu.swf'):
        (built / rel).parent.mkdir(parents=True, exist_ok=True)
        (built / rel).write_text(rel)
    monkeypatch.setattr(cleanroom, 'build', lambda: built)
    data = tmp_path / 'data'
    (data / M.OLD_MOVIE).parent.mkdir(parents=True)
    (data / M.OLD_MOVIE).write_bytes(b'old')
    assert M.install(data) == 2 and (data / f'Interface/{name}.swf').is_file()
    assert (data / 'Interface/Translations/CleanroomUI_en.txt').is_file() and not (data / M.OLD_MOVIE).exists()


def test_the_rules_gather_the_menus_data_while_the_pipboy_closes():
    """ShowOurs prepares our menu (registering it) before listening and waiting, then opens it without the settling
    wait a message box needs."""
    shown = _function(RULES, 'ShowOurs')
    assert shown.index('Prepare(aiMode, aiCount, aiBonus)') < shown.index('RegisterForMenuOpenCloseEvent(') \
        < shown.index('WaitOutOfMenus(False)') < shown.index('.Open(aiMode, aiCount, aiBonus)')
    assert 'Register()' in _function(SCRIPT, 'Prepare')
    modes = {m: int(v) for m, v in re.findall(r'Int Property (\w+)Mode = (\d)', SCRIPT)}
    assert modes == {'LevelUp': 0, 'Tags': 1, 'Traits': 2}


def test_the_rules_open_ours_in_place_of_level_up_menu():
    """LevelUpMenu opening closes it and the Pip-Boy, gives this level-up's points and opens ours; points go to
    CRUI_LevelUp, and LevelUpMenuEx's menus are never opened."""
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
    for path in (*CLEANROOM.values(), STATIC / 'F3NV_CharacterEvents.psc'):
        assert 'PRKF:' not in path.read_text(encoding='utf-8'), path.name
    assert 'LevelUpMenuEx' not in header_dirs()


def test_each_tag_gets_its_bonus_once_and_keeps_it():
    """A skill tagged in the tag menu without its bonus gets TagBonus, one untagged loses it; SPECIAL set again
    keeps it; the suggestions are done with."""
    chosen = re.search(r'Event CRUI_LevelUp\.TagsChosen\(.*?EndEvent', RULES, re.S).group(0)
    assert 'tagged && !HasBonus(skills[i])' in chosen and '+ TagBonus' in chosen and '- TagBonus' in chosen
    assert 'TES4CharacterEvents.Suggested = new ActorValue[0]' in chosen
    assert 'If HasBonus(skill)' in _function(RULES, 'SetSkillBases')
    assert 'SendCustomEvent("TagsChosen"' in _function(SCRIPT, 'OnMenuTags')


def test_other_mods_reach_the_level_up_through_cleanroom_ui():
    """Get() reads only Cleanroom UI's shared holder, which the level-up announces itself to as the rules start and
    as our menu registers; the character events quest stays its own holder, whose Running() is its LevelUp."""
    get = _function(SCRIPT, 'Get')
    assert 'CRUI_LevelUpHolder.Shared()' in get and 'GetFormFromFile' not in get
    assert 'Announce()' in _function(SCRIPT, 'Register') and 'LevelUp().Announce()' in RULES
    assert 'ScriptName F3NV_CharacterEvents extends CRUI_LevelUpHolder' in EVENTS
    assert 'Return LevelUp as CRUI_LevelUp' in _function(EVENTS, 'Running') and 'LevelUp = ' in _function(EVENTS, 'Hold')


def test_an_older_save_moves_its_level_up_state_once():
    """F3NV_LevelUp keeps the saved variables CRUI_LevelUp took over (same names, so the save fills them) and MoveTo
    hands each over; the rules' LevelUp() calls it once, only on a save whose rules started before (OnInit marks a
    new game moved before anything reaches LevelUp()).
    See: docs/fork/fo4_level_up_plan.md#crui
    """
    old = (STATIC / f'{LEGACY_SCRIPT}.psc').read_text(encoding='utf-8')
    kept = {'PerkPoints', 'SkillPoints', 'Added', 'SkillCap', 'ShowAllPerks'}
    assert _variables(old) == kept and kept <= _variables(SCRIPT)
    moved = _function(old, 'MoveTo')
    for call in ('AddPerkPoints(PerkPoints)', 'AddSkillPoints(SkillPoints)', 'SkillCap = SkillCap',
                 'ShowAllPerks = ShowAllPerks', 'AddPerk(Added[i])'):
        assert f'akHost.{call}' in moved, call
    level_up = _function(RULES, 'LevelUp')
    assert level_up.index('If !HostMoved') < level_up.index('HostMoved = True') < level_up.index('old.MoveTo(host)')
    init = re.search(r'Event OnInit\(\).*?EndEvent', RULES, re.S).group(0)
    assert init.index('HostMoved = True') < init.index('LevelUp()')


def test_the_rules_quest_keeps_the_old_script_beside_ours():
    """The build attaches F3NV_LevelUp, with nothing set, beside CRUI_LevelUp on the rules quest."""
    assert "(LEGACY_SCRIPT, {}, {})" in Path(character.__file__).read_text(encoding='utf-8')
    assert LEGACY_SCRIPT == 'F3NV_LevelUp' and character.LEVEL_UP_SCRIPT == 'CRUI_LevelUp'


def test_the_api_opens_each_menu_through_the_holder_and_the_rules():
    """OpenLevelUpMenu, OpenTagMenu and OpenTraitMenu call the holder's openers; F3NV_CharacterEvents overrides each
    with the rules' opener of the same name, which exists."""
    for api, opener in (('OpenLevelUpMenu', 'OpenLevelUp()'), ('OpenTagMenu', 'OpenTags(aiTags)'),
                        ('OpenTraitMenu', 'OpenTraits(aiTraits)')):
        name = opener.split('(')[0]
        assert f'Holder().{opener}' in _function(SCRIPT, api)
        assert f'Rules().{name}(' in _function(EVENTS, name) and f'Function {name}(' in RULES


def test_character_events_overrides_the_holder_with_matching_signatures():
    """Every function F3NV_CharacterEvents shares with CRUI_LevelUpHolder has the holder's exact signature, so it
    replaces the holder's own (its tags stay in its saved Tagged and Suggested)."""
    holder = CLEANROOM['CRUI_LevelUpHolder.psc'].read_text(encoding='utf-8')
    signature = re.compile(r'^((?:\w+[ \t]+)?Function (\w+)\([^)\n]*\))', re.M)
    theirs = {name: line for line, name in signature.findall(holder)}
    ours = {name: line for line, name in signature.findall(EVENTS)}
    shared = set(theirs) & set(ours)
    assert shared == {'Running', 'Hold', 'IsTagged', 'IsSuggested', 'Tag', 'Untag', 'SuggestTag', 'OpenLevelUp',
                      'OpenTags', 'OpenTraits'}
    assert all(ours[name] == theirs[name] for name in shared), {n for n in shared if ours[n] != theirs[n]}


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_character_scripts_compile_together(tmp_path):
    """F3NV_CharacterRules.psc, F3NV_CharacterEvents.psc (the holder holding the tags) and F3NV_LevelUp.psc (an older
    save's state) compile with Cleanroom UI's CRUI_LevelUp, CRUI_LevelUpTable and CRUI_LevelUpHolder against FO4's
    and F4SE's headers alone."""
    src, stub, out = tmp_path / 'src', tmp_path / 'stub', tmp_path / 'out'
    for folder in (src, stub, out):
        folder.mkdir()
    (stub / 'TES4Polyfill.psc').write_text(POLYFILL_STUB, encoding='utf-8')
    ours = ('F3NV_CharacterRules', 'F3NV_CharacterEvents', LEGACY_SCRIPT)
    theirs = ('CRUI_LevelUp', 'CRUI_LevelUpTable', 'CRUI_LevelUpHolder')
    for path in [STATIC / f'{name}.psc' for name in ours] + [CLEANROOM[f'{name}.psc'] for name in theirs]:
        shutil.copy(path, src)
    log = compile_folder(src, out, f'{src};{stub};{STATIC};{header_dirs()}')
    assert {p.name for p in out.iterdir()} == {f'{n}.pex' for n in ours + theirs}, log
