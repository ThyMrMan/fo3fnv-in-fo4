"""FNV's weapon requirement penalties on gun spread, as fixed multipliers on FO4's cone of fire.

FalloutNV.exe's gun spread (0x646910) is a sum of penalties (standing, unaimed, moving, crippled arms) plus
fWeapStrengthReqPenalty per point of Strength short of the weapon's requirement and the same per started 10 points
of skill short of its skill requirement, all then scaled by the skill (weapon_skills). FO4's Mod Cone-of-fire Mult
(134) only multiplies, so a shortfall becomes 1 + penalty / fStandingSpreadPenalty: FNV's ratio for a standing,
aimed shooter. One entry per shortfall band, under the weapon's requirement keyword (type_tests) and an owner
condition on that band; NPCs only, as FNV widens no player's cone (the player's shortfall moves sway: drift).

See: docs/fork/fo4_pipeline.md#requirement-spread
"""

import math
import struct

from fo4_import.base.install import plugin_walk
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.type_tests import DNAM_SKILL, SKILL_REQ, STRENGTH_REQ, requirements, skill_keyword
from fo4_import.spike.weapon_skills import FLOAT_PARAM, MULTIPLY, SPREAD, SPREAD_TABS, WEAPON_TAB, not_player
from tes5_import.base.tes5_reader import first_sub

#: CTDA operators: equal, at least, less than.
EQUAL, AT_LEAST, LESS = 0x00, 0x60, 0x80
#: FNV counts at most 10 points of a Strength shortfall, and a skill shortfall in started steps of 10.
MAX_STRENGTH_SHORT, SKILL_STEP = 10, 10


def requirement_census(plugin: bytes) -> tuple:
    """(Strength requirements above 1, {(skill, skill requirement)} above 0) of `plugin`'s weapons, sorted."""
    strengths, skills = set(), set()
    for rec, _ in plugin_walk(plugin, b'WEAP'):
        dnam = first_sub(rec.body, b'DNAM') or b''
        strength, skill_req = requirements(dnam)
        if strength > 1:
            strengths.add(strength)
        skill = struct.unpack_from('<i', dnam, DNAM_SKILL)[0] if len(dnam) >= DNAM_SKILL + 4 else -1
        if skill_req and 0 <= skill < len(C.FNV_AV_NAMES):
            skills.add((skill, skill_req))
    return sorted(strengths), sorted(skills)


def _multiply(value: float) -> list:
    """A Multiply Value parameter."""
    return [(b'EPFT', bytes([FLOAT_PARAM])), (b'EPFD', struct.pack('<f', value))]


class RequirementSpread:
    """The cone-of-fire entries of FNV's Strength and skill requirements."""

    def __init__(self, builder, settings: dict, helper_index: int):
        """FNV's `settings` (fnv_settings); its weapons' requirements, read once."""
        self.builder, self.helper_index = builder, helper_index
        self.step = settings.get('fWeapStrengthReqPenalty', 0.025) / settings.get('fStandingSpreadPenalty', 0.1)
        self.strengths, self.skills = requirement_census(None)

    def entries(self) -> list:
        """[(DATA, tabs, parameters)]: per requirement and shortfall band, its spread multiplier."""
        keyword, has, get = self.builder.type_keywords.keyword, C.FO4.index('HasKeyword'), C.FO4.index('GetValue')
        data, strength = bytes([SPREAD, MULTIPLY, SPREAD_TABS]), actor_value_form('Strength', self.helper_index)
        out = []
        for need in self.strengths:
            weapon = R.pack_ctda(EQUAL, 1.0, has, keyword(f'{STRENGTH_REQ}{need}'))
            for short in range(1, min(MAX_STRENGTH_SHORT, need - 1) + 1):
                owner = R.pack_ctda(EQUAL, float(need - short), get, strength) + not_player()
                out.append((data, {0: owner, WEAPON_TAB: weapon}, _multiply(1.0 + short * self.step)))
        for skill, need in self.skills:
            av = actor_value_form(C.FNV_AV_NAMES[skill].replace(' ', ''), self.helper_index)
            if av is None:
                continue
            weapon = (R.pack_ctda(EQUAL, 1.0, has, keyword(f'{SKILL_REQ}{need}'))
                      + R.pack_ctda(EQUAL, 1.0, has, keyword(skill_keyword(skill))))
            for steps in range(1, math.ceil(need / SKILL_STEP) + 1):
                owner = (R.pack_ctda(LESS, float(need - SKILL_STEP * (steps - 1)), get, av)
                         + R.pack_ctda(AT_LEAST, float(need - SKILL_STEP * steps), get, av) + not_player())
                out.append((data, {0: owner, WEAPON_TAB: weapon}, _multiply(1.0 + steps * self.step)))
        return out
