"""Our own level-up state in place of PRKF.dll: the perks' requirement rows and F3NV_LevelUp.psc.

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
from fo4_import.spike import conditions as C
from fo4_import.spike import level_up as L

STATIC = Path(__file__).resolve().parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
#: FNV comparison flags: >=, >= OR'd with the next, <.
AT_LEAST, AT_LEAST_OR, BELOW = 0x60, 0x61, 0x80
SCIENCE, GUNS, LEVEL_PERK = 0x200, 0x201, 0x300


def _condition(op: int, value: float, func: str, p1: int = 0) -> str:
    """One FNV condition's raw hex, as the export writes it."""
    return struct.pack('<B3xfIIIII', op, value, C.FNV.index(func), p1, 0, 0, 0).hex()


def _builder(*records) -> SimpleNamespace:
    """A builder whose perks are `records`, each FNV perk 0x10<n> built as first rank 0x90<n> (a second rank
    0x91<n> when it has two), two skills mapped; offered() is every record."""
    ids = {int(r['FormID'], 16): [0x90000 + int(r['FormID'], 16)] + [0x91000 + int(r['FormID'], 16)] * (
        r.get('DATA.Ranks') == '2') for r in records}
    perks = SimpleNamespace(records=list(records), ids=ids, first={k: v[0] for k, v in ids.items()},
                            forms={('av', 45): SCIENCE, ('av', 40): GUNS}, offered=lambda: list(records))
    return SimpleNamespace(perks=perks, counts=Counter())


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


def test_requirement_properties_are_parallel_arrays():
    """Each Requirement* array lines up by row: its perk's place in the list (owner), where the menu finds the
    tested value (target: the values for an actor value, the list for a perk, -1 for neither), the labels as one
    table; none is written for an empty table."""
    table = [(0x90001, 0, GUNS, 3, 45, 1, 'Guns'), (0x90002, 3, 0, 4, 30.0, 0, ''),
             (0x90002, 2, 0x90001, 0, 1.0, 0, 'Gunslinger'), (0x90003, 2, 0x90009, 0, 1.0, 0, 'Trait')]
    props = L.properties(table, values=[0x2C2, SCIENCE, GUNS], listed=[0x90001, 0x90002])
    assert props == {'RequirementPerks': ('objects', [0x90001, 0x90002, 0x90002, 0x90003]),
                     'RequirementKinds': ('ints', [0, 3, 2, 2]), 'RequirementForms': ('objects', [GUNS, 0, 0x90001, 0x90009]),
                     'RequirementCompares': ('ints', [3, 4, 0, 0]), 'RequirementValues': ('floats', [45.0, 30.0, 1.0, 1.0]),
                     'RequirementOr': ('ints', [1, 0, 0, 0]), 'RequirementOwners': ('ints', [0, 1, 1, -1]),
                     'RequirementTargets': ('ints', [2, -1, 0, -1]),
                     'RequirementLabels': ('string', 'Guns\t\tGunslinger\tTrait')}
    assert all(not value for _, value in L.properties([]).values())


def test_the_menu_tables_follow_the_list_and_the_skills():
    """Perks in the list's order with their names, descriptions, images (under our textures), levels and every
    rank; skills from the game's AVIF records; a tab inside a text becomes a space."""
    builder = _builder(_perk(0x1, FULL='Action Boy', DESC='More\tAP', ICON='Interface\\Icons\\Perk_AB.dds',
                             **{'DATA.MinLevel': '6', 'DATA.Ranks': '2'}),
                       _perk(0x2, FULL='Comprehension', **{'DATA.MinLevel': '4'}))
    table = L.perk_table(builder.perks)
    assert table['PerkNames'] == ('string', 'Action Boy\tComprehension')
    assert table['PerkDescriptions'] == ('string', 'More AP\t') and table['PerkImages'][1].endswith('perk_ab.dds\t')
    assert table['PerkLevels'] == ('ints', [6, 4]) and table['PerkRanks'] == ('ints', [2, 1])
    assert table['RankForms'] == ('objects', [0x90001, 0x91001, 0x90002])
    avs = {C.FNV_AV_NAMES.index('Barter'): {'FULL': 'Barter', 'DESC': 'Trade.', 'ICON': 'Interface\\Icons\\Skills_Barter.dds'}}
    skills = L.skill_table(avs, ['Barter', 'EnergyWeapons'])
    assert skills['SkillNames'] == ('string', 'Barter\tEnergyWeapons') and skills['SkillDescriptions'] == ('string', 'Trade.\t')


def test_the_script_declares_exactly_the_properties_the_build_writes():
    """F3NV_LevelUp.psc's properties without a default are the ones character.build fills: the lists, the
    requirement rows and the menu's tables; SkillCap keeps its default."""
    source = (STATIC / f'{L.SCRIPT}.psc').read_text(encoding='utf-8')
    declared = set(re.findall(r'^\S+ Property (\w+) Auto Const$', source, re.M))
    builder = _builder(_perk(0x1))
    written = {*L.properties([]), *L.perk_table(builder.perks), *L.skill_table({}, [])}
    assert declared == {*written, 'Perks', 'Skills', 'Specials'}
    character = (Path(L.__file__).parent / 'character.py').read_text(encoding='utf-8')
    assert "level_up = ({'Perks': perks, 'Skills': skill_list, 'Specials': objects['SpecialStats']}," in character


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_script_compiles(tmp_path):
    """F3NV_LevelUp.psc compiles against Fallout 4's and F4SE's headers."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    shutil.copy(STATIC / f'{L.SCRIPT}.psc', src)
    log = compile_folder(src, out, f'{src};{header_dirs()}')
    assert (out / f'{L.SCRIPT}.pex').is_file(), log
