"""Our own level-up state in place of PRKF.dll: the perks' requirement rows and CRUI_LevelUp.psc.

See: docs/fork/fo4_level_up_plan.md#prkf
"""

import re
import shutil
import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.papyrus import FO4_COMPILER, compile_folder, header_dirs
from fo4_import.spike import character
from fo4_import.spike import conditions as C
from fo4_import.spike import level_up as L

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
TABLE = (STATIC / f'{L.TABLE_SCRIPT}.psc').read_text(encoding='utf-8')
SEND = re.search(r'Function Built\(.*?EndFunction', (STATIC / f'{L.SCRIPT}.psc').read_text(encoding='utf-8'), re.S).group(0)
#: FNV comparison flags: >=, >= OR'd with the next, <.
AT_LEAST, AT_LEAST_OR, BELOW = 0x60, 0x61, 0x80
SCIENCE, GUNS, LEVEL_PERK = 0x200, 0x201, 0x300


def _condition(op: int, value: float, func: str, p1: int = 0) -> str:
    """One FNV condition's raw hex, as the export writes it."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, 0, 0).hex()


def _builder(*records) -> SimpleNamespace:
    """A builder whose perks are `records`, each FNV perk 0x<m>00000<n> built as first rank 0x90<n> (a second rank
    0x91<n> when it has two), two skills mapped; offered() is every non-trait, trait_records() every trait; its own
    records are master byte 1's, as a DLC's on one master."""
    ids = {int(r['FormID'], 16): [0x90000 + (int(r['FormID'], 16) & 0xFFF)] + [0x91000 + (int(
        r['FormID'], 16) & 0xFFF)] * (r.get('DATA.Ranks') == '2') for r in records}
    perks = SimpleNamespace(records=list(records), ids=ids, first={k: v[0] for k, v in ids.items()},
                            forms={('av', 45): SCIENCE, ('av', 40): GUNS},
                            offered=lambda: [r for r in records if r.get('DATA.Trait') != '1'],
                            trait_records=lambda: [r for r in records if r.get('DATA.Trait') == '1'])
    return SimpleNamespace(perks=perks, counts=Counter(), ids=SimpleNamespace(is_own=lambda fid: fid >> 24 >= 1))


def _perk(fid: int, *conditions, playable: str = '1', **fields) -> dict:
    """An exported PERK: `conditions` (raw hex) as Condition[0..], and `fields`."""
    return {'FormID': f'{fid:08X}', 'DATA.Playable': playable, 'DATA.Hidden': '0', **fields,
            **{f'Condition[{i}].Raw': c for i, c in enumerate(conditions)}}


def test_each_requirement_is_a_row_in_the_perks_order():
    """Skill, OR, level, sex and perk tests become rows on the perk's first rank, labeled with the actor value's or
    perk's name; unplayable perks give none."""
    builder = _builder(
        _perk(0x1, _condition(AT_LEAST_OR, 45, 'GetPermanentActorValue', 40), _condition(AT_LEAST, 45, 'GetPermanentActorValue', 45)),
        _perk(0x2, _condition(BELOW, 30, 'GetLevel'), _condition(0, 1, 'GetIsSex', 1), _condition(0, 1, 'HasPerk', 0x1)),
        _perk(0x3, _condition(AT_LEAST, 50, 'GetPermanentActorValue', 45), playable='0'))
    names = {(0, 40): 'Guns', (0, 45): 'Science', (2, 0x1): 'Gunslinger'}
    assert L.rows(builder, names) == [(0x90001, 0, GUNS, 3, 45.0, 1, 'Guns'), (0x90001, 0, SCIENCE, 3, 45.0, 0, 'Science'),
                                      (0x90002, 3, 0, 4, 30.0, 0, ''), (0x90002, 1, 0, 0, 1.0, 0, ''),
                                      (0x90002, 2, 0x90001, 0, 1.0, 0, 'Gunslinger')]
    assert not builder.counts


def test_a_sex_requirement_tests_the_players_sex_against_the_one_named():
    """GetIsSex(Male) == 1 (Lady Killer) needs sex 0; == 0 or != 1 is the other test; any other comparison is not
    shown."""
    builder = _builder(_perk(0x1, _condition(0, 1, 'GetIsSex', 0), _condition(0, 0, 'GetIsSex', 1),
                             _condition(0x20, 1, 'GetIsSex', 1), _condition(AT_LEAST, 1, 'GetIsSex', 0)))
    assert [row[3:5] for row in L.rows(builder)] == [(0, 0.0), (1, 1.0), (1, 1.0)]
    assert builder.counts['level-up requirement not shown'] == 1


def test_a_requirement_the_menu_cannot_show_is_counted_and_left_out():
    """An unmapped actor value and a function outside the kinds are counted, not written."""
    builder = _builder(_perk(0x1, _condition(AT_LEAST, 5, 'GetPermanentActorValue', 99),
                             _condition(0, 1, 'GetQuestCompleted', 0x5)))
    assert L.rows(builder) == []
    assert builder.counts['level-up requirement not shown'] == 2


def test_requirement_properties_are_the_texts_the_menu_reads():
    """Each Requirement* text lines up by row: its perk's place in the list (owner), where the menu finds the
    tested value (target: the values for an actor value, the list for a perk, -1 for neither), the labels; the
    rows testing a perk not listed are named with their perks; none is written for an empty table."""
    table = [(0x90001, 0, GUNS, 3, 45, 1, 'Guns'), (0x90002, 3, 0, 4, 30.0, 0, ''),
             (0x90002, 2, 0x90001, 0, 1.0, 0, 'Gunslinger'), (0x90003, 2, 0x90009, 0, 1.0, 0, 'Trait')]
    props = L.properties(table, values=[0x2C2, SCIENCE, GUNS], listed=[0x90001, 0x90002])
    assert props == {'RequirementKinds': ('string', '0\t3\t2\t2'), 'RequirementCompares': ('string', '3\t4\t0\t0'),
                     'RequirementValues': ('string', '45.0\t30.0\t1.0\t1.0'), 'RequirementOr': ('string', '1\t0\t0\t0'),
                     'RequirementOwners': ('string', '0\t1\t1\t-1'), 'RequirementTargets': ('string', '2\t-1\t0\t-1'),
                     'RequirementLabels': ('string', 'Guns\t\tGunslinger\tTrait'), 'RowTotal': ('int', 4),
                     'UnlistedRows': ('ints', [3]), 'UnlistedPerks': ('objects', [0x90009])}
    assert all(not value for _, value in L.properties([]).values())


def test_the_menu_tables_follow_the_list_and_the_skills():
    """Perks in the list's order with their names, descriptions, images (under our textures), levels and every
    rank; skills from the game's AVIF records; a tab inside a text becomes a space."""
    builder = _builder(_perk(0x1, FULL='Action Boy', DESC='More\tAP', ICON='Interface\\Icons\\Perk_AB.dds',
                             **{'DATA.MinLevel': '6', 'DATA.Ranks': '2'}),
                       _perk(0x2, FULL='Comprehension', **{'DATA.MinLevel': '4'}))
    table = L.perk_table(builder.perks, builder.perks.offered())
    assert table['PerkNames'] == ('string', 'Action Boy\tComprehension')
    assert table['PerkDescriptions'] == ('string', 'More AP\t') and table['PerkImages'][1].endswith('perk_ab.dds\t')
    assert table['PerkLevels'] == ('string', '6\t4') and table['PerkRanks'] == ('ints', [2, 1])
    assert table['PerkRanksText'] == ('string', '2\t1')
    assert table['RankForms'] == ('objects', [0x90001, 0x91001, 0x90002])
    avs = {C.FNV_AV_NAMES.index('Barter'): {'FULL': 'Barter', 'DESC': 'Trade.', 'ICON': 'Interface\\Icons\\Skills_Barter.dds'}}
    skills = L.skill_table(avs, ['Barter', 'EnergyWeapons'])
    assert skills['SkillNames'] == ('string', 'Barter\tEnergyWeapons') and skills['SkillDescriptions'] == ('string', 'Trade.\t')


def _declared(source: str) -> set:
    """The properties without a default a script declares."""
    return set(re.findall(r'^\S+ Property (\w+) Auto Const$', source, re.M))


def test_the_scripts_declare_exactly_the_properties_the_build_writes():
    """CRUI_LevelUp's properties without a default are the lists and the skill table; CRUI_LevelUpTable's the
    registry and table_properties' tables; character.build fills both."""
    builder = _builder(_perk(0x01000001))
    source = (STATIC / f'{L.SCRIPT}.psc').read_text(encoding='utf-8')
    assert _declared(source) == {*L.skill_table({}, []), 'Perks', 'Skills', 'Specials', 'Events', 'Tables'}
    assert _declared(TABLE) == {*L.table_properties(builder, {}, []), 'Tables'}
    built = (Path(L.__file__).parent / 'character.py').read_text(encoding='utf-8')
    assert "table = (TABLE_SCRIPT, {'Tables': tables}, table_properties(builder, avifs, special_forms + skill_forms))" in built
    assert "'Events': objects['TES4CharacterEvents'],\n                                  'Tables': tables}" in built


def test_a_dlc_table_holds_only_its_own_perks_and_traits():
    """Master perks and traits stay the game table's; a DLC perk's rows index its own table, and a requirement on a
    master perk targets -1 (the menu asks whether the player has it)."""
    builder = _builder(_perk(0x00000001, FULL='Master'), _perk(0x00000002, playable='1', **{'DATA.Trait': '1'}),
                       _perk(0x01000003, _condition(0, 1, 'HasPerk', 0x00000001), _condition(0, 1, 'HasPerk', 0x01000004),
                             FULL='Own'),
                       _perk(0x01000004, FULL='Second'), _perk(0x01000005, FULL='Trait', **{'DATA.Trait': '1'}))
    table = L.table_properties(builder, {}, [])
    assert table['PerkNames'] == ('string', 'Own\tSecond') and table['RankForms'] == ('objects', [0x90003, 0x90004])
    assert table['TraitNames'] == ('string', 'Trait') and table['TraitForms'] == ('objects', [0x90005])
    assert table['RequirementOwners'] == ('string', '0\t0') and table['RequirementTargets'] == ('string', '-1\t1')
    assert table['UnlistedPerks'] == ('objects', [0x90001])


def test_the_game_table_rides_the_rules_quest_and_a_dlc_writes_its_own(monkeypatch):
    """The game build gets the table back for its rules quest; a DLC (rules quest a master's) writes a start-game
    quest of its own when its table lists anything, else nothing."""
    written = []
    writer = SimpleNamespace(own_index=1, add_record=lambda sig, body: written.append(sig))
    builder = SimpleNamespace(writer=writer, export_dir=Path('x'), new_id=lambda owner, key=None: 0x01000800)
    monkeypatch.setattr(character, 'plugin_stem', lambda export_dir: 'OldWorldBlues')
    table = (L.TABLE_SCRIPT, {'Tables': 0x00000900}, {'RankForms': ('objects', []), 'TraitForms': ('objects', [0x90005])})
    assert character._table(builder, 0x01000700, table) == [table] and not written
    assert character._table(builder, 0x00000700, table) == [] and written == ['QUST']
    empty = (L.TABLE_SCRIPT, {}, {'RankForms': ('objects', []), 'TraitForms': ('objects', [])})
    assert character._table(builder, 0x00000700, empty) == [] and written == ['QUST']


def test_an_older_builds_level_up_menu_ex_ini_is_deleted(tmp_path):
    """The game build deletes Data/PRKF/<stem>.ini an older build wrote, the folder once empty; another file stays."""
    folder = tmp_path / character.PRKF_INI_DIR
    folder.mkdir()
    (folder / 'FalloutNV.ini').write_text('[Main]\n', encoding='ascii')
    assert character.drop_prkf_ini(tmp_path, 'FalloutNV.esm') == 1 and not folder.exists()
    assert character.drop_prkf_ini(tmp_path, 'FalloutNV.esm') == 0
    folder.mkdir()
    (folder / 'FalloutNV.ini').write_text('[Main]\n', encoding='ascii')
    (folder / 'OtherMod.ini').write_text('[Main]\n', encoding='ascii')
    assert character.drop_prkf_ini(tmp_path, 'FalloutNV.esm') == 1 and [p.name for p in folder.iterdir()] == ['OtherMod.ini']


def test_built_merges_each_text_the_movie_reads_where_the_table_keeps_it():
    """Each Merged(n, ...) in Built is the table's Text n, a property the build wrote whole (an open joins none), and
    fills the argument the movie reads that table from; the rows' held tests are gathered beside the ranks."""
    text = re.search(r'String Function Text\(.*?EndFunction', TABLE, re.S).group(0)
    branches = {**dict(re.findall(r'aiWhich == (\d+)\n\s+Return (\w+)\n', text)), '14': 'RequirementLabels'}
    assert text.endswith('Return RequirementLabels\nEndFunction') and 'Joined(' not in text
    wanted = {5: 'PerkNames', 6: 'PerkDescriptions', 7: 'PerkImages', 8: 'PerkLevels', 9: 'PerkRanksText',
              17: 'RequirementOwners', 18: 'RequirementKinds', 19: 'RequirementTargets', 20: 'RequirementCompares',
              21: 'RequirementValues', 22: 'RequirementOr', 23: 'RequirementLabels',
              28: 'TraitNames', 29: 'TraitDescriptions', 30: 'TraitImages'}
    merged = {int(arg): branches[n] for arg, n in re.findall(r'args\[(\d+)\] = Merged\((\d+),', SEND)}
    assert merged == wanted and 'args[24] = unlisted' in SEND
    assert 'args[33] = GroupCounts(perkCounts)' in SEND and 'args[34] = GroupCounts(rowCounts)' in SEND


def test_the_trait_table_follows_the_traits_list():
    """The trait menu's names, descriptions and images line up with FNV_Traits (trait_records' order)."""
    traits = [{'FULL': 'Kamikaze', 'DESC': 'Faster, weaker.', 'ICON': 'Interface\\Icons\\Trait_K.dds'}, {'FULL': 'Four Eyes'}]
    table = L.texts('Trait', traits)
    assert table['TraitNames'] == ('string', 'Kamikaze\tFour Eyes')
    assert table['TraitDescriptions'] == ('string', 'Faster, weaker.\t') and table['TraitImages'][1].endswith('trait_k.dds\t')


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_script_compiles(tmp_path):
    """CRUI_LevelUp.psc compiles against Fallout 4's and F4SE's headers and F3NV_CharacterEvents.psc, which holds
    the tags."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    shutil.copy(STATIC / f'{L.SCRIPT}.psc', src)
    log = compile_folder(src, out, f'{src};{STATIC};{header_dirs()}')
    assert (out / f'{L.SCRIPT}.pex').is_file(), log
