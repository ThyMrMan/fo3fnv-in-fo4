"""FNV's sneak attacks: a critical hit's chance multiplied, melee and unarmed damage multiplied.

FalloutNV.exe (GOG 1.4.0.525) flags a hit a sneak attack (0x400) when the attacker sneaks and the living target
has not detected it (0x9B7060): the critical chance is multiplied by fCombatSneakAttackBonusMult (100 in
FalloutNV.esm, so in practice a critical hit); then (0x9B73D0) the hit's damage by
fCombatDamageBonusMeleeSneakingMult (the engine's 5) with a hand-to-hand or melee weapon (animation types 0-2), else
by fCombatDamageBonusSneakingMult (1). FO4 multiplies sneak attack damage by its own fCombatSneak*Mult (guns 2,
melee 3); the combat rules perk sets FNV's on Mod Sneak Attack Mult (18). The critical part is criticals' (the
conditions here); it tests the target not detecting the player, as vanilla's FortifySneakAttackBonus2xChemPerk
does, so it is the player's.

See: docs/fork/fo4_pipeline.md#sneak-attacks
"""

import struct

from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.type_tests import ANIM_TYPES, anim_keyword

#: FO4 entry point Mod Sneak Attack Mult, its tab count (owner, weapon, target), the weapon's; Set Value; EPFT.
SNEAK_MULT, SNEAK_TABS, WEAPON_TAB, SET_VALUE, FLOAT_PARAM = 18, 3, 1, 1, 1
#: FNV animation types FNV counts melee for a sneak attack's damage.
MELEE = ('HandToHand', 'Melee1Hand', 'Melee2Hand')
#: The player's base NPC and reference; CTDA operators equal and not equal (OR flag), run on the hit's target.
PLAYER_BASE, PLAYER_REF, EQUAL, NOT_EQUAL, OR = 0x7, 0x14, 0x00, 0x20, 0x01


def sneaking() -> bytes:
    """Owner conditions: the player, sneaking, undetected by the target."""
    return (R.pack_ctda(EQUAL, 1.0, C.FO4.index('GetIsID'), PLAYER_BASE)
            + R.pack_ctda(EQUAL, 1.0, C.FO4.index('IsSneaking'))
            + R.pack_ctda(EQUAL, 0.0, C.FO4.index('GetDetected'), PLAYER_REF, run_on=R.RUN_TARGET))


def in_vats() -> bytes:
    """Owner tab condition of an attack in V.A.T.S."""
    return R.pack_ctda(NOT_EQUAL, 0.0, C.FO4.index('GetVATSMode'))


class SneakAttacks:
    """The sneak attack damage entries of the combat rules perk."""

    def __init__(self, builder, settings: dict):
        """FNV's `settings` (fnv_settings)."""
        self.builder = builder
        self.melee = settings.get('fCombatDamageBonusMeleeSneakingMult', 5.0)
        self.other = settings.get('fCombatDamageBonusSneakingMult', 1.0)

    def entries(self) -> list:
        """[(DATA, tabs, parameters)]: Mod Sneak Attack Mult set to FNV's other value with a weapon of FNV's other
        animation types (any of their keywords), else to its melee value: FNV counts no weapon as melee, and FO4's
        fists and creatures' attacks carry no FNV keyword."""
        keyword, has = self.builder.type_keywords.keyword, C.FO4.index('HasKeyword')
        ranged = [keyword(anim_keyword(i)) for i, kind in enumerate(ANIM_TYPES) if kind not in MELEE]
        any_ranged = b''.join(R.pack_ctda(EQUAL | (OR if i < len(ranged) - 1 else 0), 1.0, has, k)
                              for i, k in enumerate(ranged))
        none = b''.join(R.pack_ctda(EQUAL, 0.0, has, k) for k in ranged)
        data = bytes([SNEAK_MULT, SET_VALUE, SNEAK_TABS])
        return [(data, {WEAPON_TAB: tabs}, [(b'EPFT', bytes([FLOAT_PARAM])), (b'EPFD', struct.pack('<f', value))])
                for tabs, value in ((any_ranged, self.other), (none, self.melee))]
