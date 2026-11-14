"""FNV weapon skill, weapon animation and creature type tests as FO4 keyword tests.

See: docs/fork/fo4_perks.md#type-tests
"""

import struct

from fo4_import.spike import conditions as C
from fo4_import.spike import type_tests as T


class _Keywords:
    """Stand-in TypeKeywords: one FormID per EditorID, nothing written."""

    def __init__(self):
        """No keyword handed out yet."""
        self.ids = {}

    def keyword(self, edid: str) -> int:
        """A stable FormID for `edid`."""
        return self.ids.setdefault(edid, 0x0B200000 + len(self.ids))


def _cond(func: str, op: int, value: float, p1: int = 0, or_next: bool = False) -> dict:
    """A parsed FNV condition: `func` `op` (0x00 ==, 0x20 !=) `value`."""
    return {'func': func, 'op_flags': op | (C.OR_NEXT if or_next else 0), 'value': value, 'p1': p1, 'p2': 0,
            'run_on': 0, 'ref': 0, 'global': 0}


def test_weapon_skill_on_a_weapon_tab_is_has_keyword():
    """IsWeaponSkillType Guns == 1 on a weapon subject: HasKeyword(FNV_WeaponSkillGuns) == 1, OR flag kept."""
    kw = _Keywords()
    guns = C.FNV_AV_NAMES.index('Guns')
    (out,) = T.translated([_cond(T.SKILL, 0x00, 1.0, guns, or_next=True)], kw, item=True)
    assert (out['func'], out['p1'], out['value'], out['op_flags']) == (
        T.HAS, kw.ids['FNV_WeaponSkillGuns'], 1.0, C.OR_NEXT)


def test_animation_range_on_an_actor_is_or_of_worn_keywords():
    """GetWeaponAnimType <= 3 on an actor: WornHasKeyword of the four types it covers, OR'd, the last closing."""
    kw = _Keywords()
    out = T.translated([_cond(T.ANIM, 0xA0, 3.0)], kw, item=False)
    assert [c['func'] for c in out] == [T.WORN] * 4
    assert [c['p1'] for c in out] == [kw.ids[T.anim_keyword(t)] for t in range(4)]
    assert [c['op_flags'] & C.OR_NEXT for c in out] == [C.OR_NEXT] * 3 + [0]


def test_animation_not_equal_is_one_keyword_absent():
    """GetWeaponAnimType != 8: the Handle keyword absent (== 0)."""
    kw = _Keywords()
    (out,) = T.translated([_cond(T.ANIM, 0x20, 8.0)], kw, item=False)
    assert (out['p1'], out['value']) == (kw.ids['FNV_WeaponAnimHandle'], 0.0)


def test_several_absent_keywords_in_an_or_group_cannot_convert():
    """Absent keywords AND together, which an OR group cannot hold: None."""
    conds = [_cond(T.ANIM, 0x40, 1.0, or_next=True), _cond(T.SKILL, 0x00, 1.0, 41)]
    assert T.translated(conds, _Keywords(), item=False) is None


def test_creature_type_is_has_keyword_on_the_actor():
    """GetIsCreatureType 6 == 1: HasKeyword(FNV_CreatureTypeRobot)."""
    kw = _Keywords()
    (out,) = T.translated([_cond(T.CREATURE, 0x00, 1.0, 6)], kw, item=False)
    assert (out['func'], out['p1']) == (T.HAS, kw.ids['FNV_CreatureTypeRobot'])


def test_without_keywords_a_type_test_cannot_convert():
    """A build with no TypeKeywords cannot write a type test."""
    assert T.translated([_cond(T.CREATURE, 0x00, 1.0, 6)], None, item=False) is None


def test_with_keywords_adds_to_ksiz_and_kwda():
    """Keywords 7, 8, 9 on a record holding 7: KSIZ 3, no 7 twice."""
    subs = [(b'EDID', b'x\0'), (b'KSIZ', struct.pack('<I', 1)), (b'KWDA', struct.pack('<I', 7))]
    out = dict(T.with_keywords(subs, [7, 8, 9]))
    assert out[b'KSIZ'] == struct.pack('<I', 3) and out[b'KWDA'] == struct.pack('<3I', 7, 8, 9)


def test_with_keywords_adds_kwda_after_the_given_tag():
    """An armor without keywords gains KSIZ/KWDA right after RNAM."""
    subs = [(b'EDID', b'x'), (b'RNAM', b'r'), (b'DATA', b'd')]
    out = T.with_keywords(subs, [7], T.ARMO_KEYWORDS_AFTER)
    assert [t for t, _ in out] == [b'EDID', b'RNAM', b'KSIZ', b'KWDA', b'DATA'] and out[3][1] == struct.pack('<I', 7)


def test_biped_slots_mark_each_set_flag():
    """Biped flags 0x401 (Head, Hat) give FNV_BipedSlot0 and FNV_BipedSlot10."""
    kw = _Keywords()
    T.TypeKeywords.slots(kw, 0x401)
    assert sorted(kw.ids) == ['FNV_BipedSlot0', 'FNV_BipedSlot10']
    assert (T.equipped_slot(' 10'), T.equipped_slot('iSlot'), T.equipped_slot('20')) == (10, None, None)


def test_weapon_fields_name_animation_and_skill():
    """An FNV DNAM with animation type 5 and skill Guns names RifleBallistic and Guns."""
    dnam = bytearray(140)
    struct.pack_into('<I', dnam, T.DNAM_ANIM, 5)
    struct.pack_into('<i', dnam, T.DNAM_SKILL, C.FNV_AV_NAMES.index('Guns'))
    assert T.weapon_names({b'DNAM': bytes(dnam)}) == ('FNV_WeaponAnimRifleBallistic', 'FNV_WeaponSkillGuns')
