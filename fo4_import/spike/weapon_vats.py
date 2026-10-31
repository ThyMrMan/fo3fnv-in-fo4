"""FNV's V.A.T.S. AP cost and critical data on a converted weapon (one copied from an FO4 weapon).

- AP cost (DNAM Action Point Cost): FNV's own when its "Override - Action Points" flag is set, else the
  `fActionPointsAttack*` setting of its weapon class, as FNV charges it.
- Crit Damage Mult (CRDT): FO4 multiplies a critical hit's damage by it; FNV adds its Critical Damage to the
  hit, so it is (damage + critical damage) / damage. A weapon with no base damage keeps the FO4 weapon's.
- Crit Charge Bonus (CRDT): how fast the weapon fills FO4's critical meter (1 normal); FNV's Crit % Mult,
  how much more often it crits (1 normal, 0 never).
- Crit Effect: FNV's critical effects are death effects (laser ash, plasma goo, flames, nuke) and two
  knockdowns, cast on the victim; FO4's energy weapons carry their own counterparts. A weapon with one keeps
  the FO4 weapon's effect and its on-death flag, else takes FNV's spell as converted script effects (the
  knockdowns); one without has none.

See: docs/fork/fo4_pipeline.md#weapon-criticals
"""

import struct

from fo4_import.spike.combat_styles import fnv_settings

#: FO4 WEAP DNAM offset of the Action Point Cost (float).
DNAM_AP = 112
#: FO4 WEAP CRDT: Crit Damage Mult, Crit Charge Bonus (floats), Crit Effect (SPEL); xEdit's defaults.
CRDT = struct.Struct('<ffI')
DEFAULT_CRDT = CRDT.pack(2.0, 1.0, 0)
#: FNV WEAP DNAM Flags2 bit: the weapon's own AP cost applies.
FNV_AP_OVERRIDE = 0x8
#: FNV weapon animation type -> the weapon class of the fActionPointsAttack<class> setting FNV charges.
AP_CLASS = {0: 'Unarmed', 1: 'OneHandMelee', 2: 'TwoHandMelee', 3: 'Pistol', 4: 'Pistol', 5: 'Rifle', 6: 'Rifle',
            7: 'Rifle', 8: 'Handle', 9: 'Launcher', 10: 'Grenade', 11: 'Mine', 12: 'Mine', 13: 'Thrown'}


def ap_cost(rec: dict, settings: dict) -> 'float | None':
    """FNV WEAP `rec`'s V.A.T.S. AP cost: its override, else its class's setting in `settings`; None without."""
    if int(rec.get('DNAM.Flags2', 0) or 0) & FNV_AP_OVERRIDE and 'DNAM.ActionPoints' in rec:
        return float(rec['DNAM.ActionPoints'])
    setting = f"fActionPointsAttack{AP_CLASS.get(int(rec.get('DNAM.FalloutAnimType', -1)), '')}"
    return float(settings[setting]) if setting in settings else None


def critical_data(rec: dict, crdt: bytes, spell=lambda fnv: None) -> bytes:
    """FO4 CRDT `crdt` (an FO4 weapon's) carrying FNV WEAP `rec`'s critical data (module notes); as it is when
    FNV's is absent. `spell`: the FO4 spell of an FNV spell FormID, or None."""
    if 'CRDT.Damage' not in rec:
        return crdt
    mult, charge, effect = CRDT.unpack_from(crdt.ljust(CRDT.size, b'\0') if len(crdt) < CRDT.size else crdt)
    damage = int(rec.get('DATA.Damage', 0) or 0)
    if damage > 0:
        mult = (damage + int(rec['CRDT.Damage'])) / damage
    charge = float(rec.get('CRDT.ChanceMult', charge))
    fnv = int(rec.get('CRDT.Effect', '0'), 16)
    effect = (effect or spell(fnv) or 0) if fnv else 0
    return CRDT.pack(mult, charge, effect) + crdt[CRDT.size:]


class WeaponVats:
    """FNV's AP cost and critical data for the weapons a build copies."""

    def __init__(self, builder):
        """FNV's settings (fnv_settings) read once."""
        self.builder, self.settings = builder, fnv_settings(builder.export_dir)

    def apply(self, rec: dict, dnam: bytearray, template: dict) -> bytes:
        """Write FNV WEAP `rec`'s AP cost into FO4 DNAM `dnam`; the copy's CRDT, from `template`'s."""
        cost = ap_cost(rec, self.settings)
        if cost is not None and len(dnam) >= DNAM_AP + 4:
            struct.pack_into('<f', dnam, DNAM_AP, cost)
        return critical_data(rec, template.get(b'CRDT', DEFAULT_CRDT), self.builder.scripts.effects.spell_of)
