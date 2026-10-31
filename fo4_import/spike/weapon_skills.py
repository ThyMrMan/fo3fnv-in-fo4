"""FNV's weapon skills in combat: damage and gun spread scaled by the attacker's skill with the weapon.

FalloutNV.exe (GOG 1.4.0.525) multiplies a weapon's damage (0x644CE0; every weapon but hand-to-hand, animation
type 0) by fDamageSkillBase + fDamageSkillMult x skill / 100 (x the condition penalty on the skill part), 0.5 +
0.5 x skill / 100 in FalloutNV.esm, before the attacker's Calculate Weapon Damage perks. Its gun spread (0x646910)
ends x (1 - fWobbleToSkillConversion x skill / 100), halved at skill 100; Fallout 3's fGunSpreadSkill* settings
are not read. FO4 perk entry points do the same: Mod Weapon Attack Damage (35) by Multiply Value base and Multiply 1
+ Actor Value Mult (the skill x mult / (100 x base)); Mod Cone-of-fire Mult (134) by Multiply 1 + Actor Value Mult
(the skill x -fWobbleToSkillConversion / 100). Each skill's entries test the weapon's FNV_WeaponSkill keyword
(type_tests) and an attacker holding that skill, so creatures, which FNV gives one combat skill, keep full damage.
FNV's skill never widens the player's cone, so the cone entries test a non-player owner; it moves the player's
sway and V.A.T.S. chance, here Mod Actor Scope Stability (102) and Mod VATS Hit Chance (123), owner tab only.

See: docs/fork/fo4_pipeline.md#weapon-skills
"""

import struct

from fo4_import.base.install import plugin_walk
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.type_tests import ANIM_TYPES, DNAM_SKILL, anim_keyword, skill_keyword
from tes5_import.base.tes5_reader import first_sub

#: FO4 entry points Mod Weapon Attack Damage and Mod Cone-of-fire Mult, and their condition tab counts (vanilla's).
DAMAGE, SPREAD, DAMAGE_TABS, SPREAD_TABS, WEAPON_TAB = 35, 134, 3, 2, 1
#: Entry point functions Multiply Value, Multiply Actor Value Mult, Multiply 1 + Actor Value Mult; EPFT kinds.
MULTIPLY, MULTIPLY_AV, MULTIPLY_ONE_PLUS_AV, FLOAT_PARAM, AV_PARAM = 3, 13, 14, 1, 8
#: FO4 entry points Mod VATS Hit Chance and Mod Actor Scope Stability, each with one (owner) tab.
VATS_HIT, VATS_TABS, SWAY = 123, 1, 102
#: FO4's scoped sway at skill 0 (vanilla's player: 0.5); FNV halves it at 100 (fWobbleToSkillConversion).
SWAY_AT_ZERO = 0.75
#: The player's reference, for GetIsReference.
PLAYER_REF = 0x14
#: CTDA operators: equal, greater than.
EQUAL, GREATER = 0x00, 0x40


def weapon_skills(plugin: bytes) -> list:
    """Names of the FNV skills `plugin`'s weapons use (their DNAM skill actor value), sorted."""
    found = set()
    for rec, _ in plugin_walk(plugin, b'WEAP'):
        dnam = first_sub(rec.body, b'DNAM') or b''
        skill = struct.unpack_from('<i', dnam, DNAM_SKILL)[0] if len(dnam) >= DNAM_SKILL + 4 else -1
        if 0 <= skill < len(C.FNV_AV_NAMES):
            found.add(skill)
    return sorted(C.FNV_AV_NAMES[s].replace(' ', '') for s in found)


def _param(av: int, value: float) -> list:
    """An actor value and float parameter (EPFT 8)."""
    return [(b'EPFT', bytes([AV_PARAM])), (b'EPFD', struct.pack('<If', av, value))]


class WeaponSkills:
    """The damage and spread entries of the source game's weapon skills."""

    def __init__(self, builder, settings: dict, helper_index: int):
        """FNV's `settings` (fnv_settings); its weapons' skills, read once."""
        self.builder, self.settings, self.helper_index = builder, settings, helper_index
        self.skills = [s for s in weapon_skills(None) if actor_value_form(s, helper_index) is not None]

    def entries(self) -> list:
        """[(DATA, tabs, parameters)]: per skill, its damage and spread scaling."""
        keyword, has, get = self.builder.type_keywords.keyword, C.FO4.index('HasKeyword'), C.FO4.index('GetValue')
        unarmed = R.pack_ctda(EQUAL, 0.0, has, keyword(anim_keyword(ANIM_TYPES.index('HandToHand'))))
        base, mult = self.settings.get('fDamageSkillBase', 0.5), self.settings.get('fDamageSkillMult', 0.5)
        wobble = self.settings.get('fWobbleToSkillConversion', 0.5)
        out, worn = [], C.FO4.index('WornHasKeyword')
        for name in self.skills:
            av = actor_value_form(name, self.helper_index)
            owner, marked = R.pack_ctda(GREATER, 0.0, get, av), keyword(skill_keyword(C.FNV_AV_NAMES.index(_spaced(name))))
            weapon = R.pack_ctda(EQUAL, 1.0, has, marked)
            damage = {0: owner, WEAPON_TAB: weapon + unarmed}
            out += ([(bytes([DAMAGE, MULTIPLY, DAMAGE_TABS]), damage, [(b'EPFT', bytes([FLOAT_PARAM])),
                                                                          (b'EPFD', struct.pack('<f', base))]),
                     (bytes([DAMAGE, MULTIPLY_ONE_PLUS_AV, DAMAGE_TABS]), damage, _param(av, mult / (100 * base)))]
                    if base else [(bytes([DAMAGE, MULTIPLY_AV, DAMAGE_TABS]), damage, _param(av, mult / 100))])
            out.append((bytes([SPREAD, MULTIPLY_ONE_PLUS_AV, SPREAD_TABS]), {0: owner + not_player(),
                                                                             WEAPON_TAB: weapon},
                        _param(av, -wobble / 100)))
            held = R.pack_ctda(EQUAL, 1.0, worn, marked)
            out += vats_entries(av, held, wobble) + sway_entries(av, held, wobble)
        return out


def not_player() -> bytes:
    """A CTDA true on any owner but the player (GetIsReference Player == 0)."""
    return R.pack_ctda(EQUAL, 0.0, C.FO4.index('GetIsReference'), PLAYER_REF)


def sway_entries(av: int, worn: bytes, wobble: float) -> list:
    """Mod Actor Scope Stability on a `worn` weapon: FO4's scoped sway 1 - 0.5 x stability goes from SWAY_AT_ZERO
    at skill 0 to SWAY_AT_ZERO x (1 - wobble) at 100: Multiply Value m, then Multiply 1 + skill x k.
    See: docs/fork/fo4_build_next.md#sway
    """
    m = 2.0 * (1.0 - SWAY_AT_ZERO)
    k = ((1.0 - SWAY_AT_ZERO * (1.0 - wobble)) / (0.5 * m) - 1.0) / 100.0
    return [(bytes([SWAY, MULTIPLY, VATS_TABS]), {0: worn}, [(b'EPFT', bytes([FLOAT_PARAM])),
                                                       (b'EPFD', struct.pack('<f', m))]),
            (bytes([SWAY, MULTIPLY_ONE_PLUS_AV, VATS_TABS]), {0: worn}, _param(av, k))]


def vats_entries(av: int, worn: bytes, wobble: float) -> list:
    """Mod VATS Hit Chance x (1 - wobble) x (1 + skill x wobble / (100 x (1 - wobble))) on a `worn` weapon."""
    base, tabs = 1.0 - wobble, {0: worn}
    if base <= 0:
        return [(bytes([VATS_HIT, MULTIPLY_AV, VATS_TABS]), tabs, _param(av, wobble / 100))]
    return [(bytes([VATS_HIT, MULTIPLY, VATS_TABS]), tabs, [(b'EPFT', bytes([FLOAT_PARAM])),
                                                          (b'EPFD', struct.pack('<f', base))]),
            (bytes([VATS_HIT, MULTIPLY_ONE_PLUS_AV, VATS_TABS]), tabs, _param(av, wobble / (100 * base)))]


def _spaced(name: str) -> str:
    """FNV actor value `name` with its spaces (EnergyWeapons)."""
    return next(n for n in C.FNV_AV_NAMES if n.replace(' ', '') == name)
