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
    """A builder whose perks are `records`, each FNV perk 0x10<n> built as first rank 0x90<n>, two skills mapped."""
    first = {int(r['FormID'], 16): 0x90000 + int(r['FormID'], 16) for r in records}
    perks = SimpleNamespace(records=list(records), first=first, forms={('av', 45): SCIENCE, ('av', 40): GUNS})
    return SimpleNamespace(perks=perks, counts=Counter())


def _perk(fid: int, *conditions, playable: str = '1') -> dict:
    """An exported PERK with `conditions` (raw hex) as Condition[0..]."""
    return {'FormID': f'{fid:08X}', 'DATA.Playable': playable, 'DATA.Hidden': '0',
            **{f'Condition[{i}].Raw': c for i, c in enumerate(conditions)}}


def test_each_requirement_is_a_row_in_the_perks_order():
    """Skill, OR, level, sex and perk tests become rows on the perk's first rank; unplayable perks give none."""
    builder = _builder(
        _perk(0x1, _condition(AT_LEAST_OR, 45, 'GetPermanentActorValue', 40), _condition(AT_LEAST, 45, 'GetPermanentActorValue', 45)),
        _perk(0x2, _condition(BELOW, 30, 'GetLevel'), _condition(0, 1, 'GetIsSex'), _condition(0, 1, 'HasPerk', 0x1)),
        _perk(0x3, _condition(AT_LEAST, 50, 'GetPermanentActorValue', 45), playable='0'))
    assert L.rows(builder) == [(0x90001, 0, GUNS, 3, 45.0, 1), (0x90001, 0, SCIENCE, 3, 45.0, 0),
                               (0x90002, 3, 0, 4, 30.0, 0), (0x90002, 1, 0, 0, 1.0, 0), (0x90002, 2, 0x90001, 0, 1.0, 0)]
    assert not builder.counts


def test_a_requirement_the_menu_cannot_show_is_counted_and_left_out():
    """An unmapped actor value and a function outside the kinds are counted, not written."""
    builder = _builder(_perk(0x1, _condition(AT_LEAST, 5, 'GetPermanentActorValue', 99),
                             _condition(0, 1, 'GetQuestCompleted', 0x5)))
    assert L.rows(builder) == []
    assert builder.counts['level-up requirement not shown'] == 2


def test_requirement_properties_are_parallel_arrays():
    """Each Requirement* array lines up by row; none is written for an empty table."""
    props = L.properties([(0x90001, 0, GUNS, 3, 45, 1), (0x90002, 3, 0, 4, 30.0, 0)])
    assert props == {'RequirementPerks': ('objects', [0x90001, 0x90002]), 'RequirementKinds': ('ints', [0, 3]),
                     'RequirementForms': ('objects', [GUNS, 0]), 'RequirementCompares': ('ints', [3, 4]),
                     'RequirementValues': ('floats', [45.0, 30.0]), 'RequirementOr': ('ints', [1, 0])}
    assert all(not value for _, value in L.properties([]).values())


def test_the_script_declares_exactly_the_properties_the_build_writes():
    """F3NV_LevelUp.psc's properties without a default are each Requirement* property and Perks, the ones
    character.build fills; SkillCap keeps its default."""
    source = (STATIC / f'{L.SCRIPT}.psc').read_text(encoding='utf-8')
    declared = set(re.findall(r'^\S+ Property (\w+) Auto Const$', source, re.M))
    assert declared == {*L.properties([]), 'Perks'}
    assert "level_up = ({'Perks': perks}," in (Path(L.__file__).parent / 'character.py').read_text(encoding='utf-8')


@pytest.mark.skipif(not FO4_COMPILER.is_file(), reason='the FO4 Papyrus compiler is not installed')
def test_the_script_compiles(tmp_path):
    """F3NV_LevelUp.psc compiles against Fallout 4's and F4SE's headers."""
    src, out = tmp_path / 'src', tmp_path / 'out'
    src.mkdir()
    out.mkdir()
    shutil.copy(STATIC / f'{L.SCRIPT}.psc', src)
    log = compile_folder(src, out, f'{src};{header_dirs()}')
    assert (out / f'{L.SCRIPT}.pex').is_file(), log
