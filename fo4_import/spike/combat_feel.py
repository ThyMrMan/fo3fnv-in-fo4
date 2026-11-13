"""FNV's player health, speed and V.A.T.S. damage on Fallout 4: settings and one player ability.

- Health: FalloutNV.exe gives the player base + (Endurance + fAVDHealthEnduranceOffset) x fAVDHealthEnduranceMult
  + (level - 1) x fAVDHealthLevelMult; Fallout4.exe (0x1406c9e10) base + Endurance x fAVDHealthStartEndMult +
  (level - 1) x (Endurance x fHealthEnduranceMult + fHealthEnduranceOffset). FNV's mults go on FO4's settings
  (HEALTH_SETTINGS); the base difference (FNV's player record against FO4's player and race PRPS) and FNV's
  offset term are the ability's Health.
- Speed: the ability's SpeedMult brings Player_Default_MT's forward run to FNV's fMoveBaseSpeed x fMoveRunMult.
- V.A.T.S.: target selection slows time to VATS_SLOW; the player takes FNV's fVATSPlayerDamageMult.
Difficulty needs nothing: FO4's five non-Survival multipliers are FNV's numbers.

See: docs/fork/fo4_combat_feel.md#built
"""

import struct

from fo4_import.base.support_records import pack_gmst
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.creature_speed import forward_run
from fo4_import.face.tint import HUMAN_RACE
from fo4_import.spike.perks import SPELL_TEMPLATE, pack_spell
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FO4 health settings -> the FNV setting giving its value (None: 0, the level term's Endurance part).
HEALTH_SETTINGS = {'fAVDHealthStartEndMult': 'fAVDHealthEnduranceMult', 'fHealthEnduranceMult': None,
                   'fHealthEnduranceOffset': 'fAVDHealthLevelMult'}
#: FO4's V.A.T.S. target-select time (Fallout4.esm 0.04; the user chose slower, not a pause) and its damage setting.
VATS_SLOW, VATS_TIME, VATS_DAMAGE = 0.02, 'fVATSTimeMultTargetSelect', 'fVATSPlayerDamageMult'
#: FO4 actor values Health and SpeedMult; Fallout4.esm's player base record and default movement type.
HEALTH, SPEED_MULT, PLAYER, PLAYER_MOVEMENT = 0x2D4, 0x2DA, 0x7, 'Player_Default_MT'
#: derive_formid sites (key: the setting's EditorID; the ability's EditorID).
SITES = {'GMST': 'FNV combat setting', 'SPEL': 'FNV player rules'}
ABILITY = 'FNV_PlayerRules'


def fo4_settings(fnv: dict) -> dict:
    """{FO4 GMST EditorID: value} carrying FNV's `fnv` settings (fnv_settings)."""
    out = {fo4: float(fnv.get(name, 0.0)) if name else 0.0 for fo4, name in HEALTH_SETTINGS.items()}
    return {**out, VATS_TIME: VATS_SLOW, VATS_DAMAGE: float(fnv.get(VATS_DAMAGE, 0.1))}


def prps_value(subs: dict, av: int) -> float:
    """Actor value `av` in a record's PRPS (FormID, float pairs); 0 without one."""
    raw = subs.get(b'PRPS', b'')
    pairs = struct.iter_unpack('<If', raw[:len(raw) // 8 * 8])
    return next((value for form, value in pairs if form == av), 0.0)


def write_settings(builder, fnv: dict) -> None:
    """Write fo4_settings as GMSTs on Fallout4.esm's FormIDs (a new one for a setting the esm lacks)."""
    wanted = fo4_settings(fnv)
    found = {}
    for rec, _ in walk(builder.fo4, b'GMST'):
        edid = dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode()
        if edid in wanted:
            found[edid] = rec.form_id
    for edid, value in wanted.items():
        fid = found.get(edid) or builder.writer.derive_formid(SITES['GMST'], edid)
        builder.writer.add_record('GMST', pack_gmst(fid, edid, value))
        builder.counts['GMST (combat feel)'] += 1


class PlayerRules:
    """The player's ability: FNV's base health and speed against FO4's."""

    def __init__(self, builder, export_dir, fnv: dict):
        """Read FNV's player record and Fallout4.esm's player, race and movement type."""
        self.builder, self.fnv = builder, fnv
        player = next(r for r in export_records(export_dir, 'NPC_') if int(r['FormID'], 16) == PLAYER)
        self.fnv_base = float(player.get('DATA.BaseHealth', 0) or 0)
        self.fo4_base, self.fo4_run = 0.0, 0.0
        for rec, _ in walk(builder.fo4, b'NPC_', b'RACE', b'MOVT'):
            subs = dict(subrecords(rec.body))
            if rec.form_id in (PLAYER, HUMAN_RACE) and rec.sig in (b'NPC_', b'RACE'):
                self.fo4_base += prps_value(subs, HEALTH)
            elif rec.sig == b'MOVT' and subs.get(b'EDID', b'').rstrip(b'\0').decode() == PLAYER_MOVEMENT:
                self.fo4_run = forward_run(subs[b'SPED'])

    def values(self) -> dict:
        """{FO4 actor value: the ability's magnitude}: Health the base gap, SpeedMult the run speed's."""
        health = self.fnv_base + self.fnv.get('fAVDHealthEnduranceOffset', 0.0) * self.fnv.get(
            'fAVDHealthEnduranceMult', 0.0) - self.fo4_base
        run = self.fnv.get('fMoveBaseSpeed', 0.0) * self.fnv.get('fMoveRunMult', 0.0)
        speed = 100.0 * run / self.fo4_run - 100.0 if self.fo4_run and run else 0.0
        return {HEALTH: health, SPEED_MULT: speed}

    def write(self) -> 'int | None':
        """Write the ability on Fallout4.esm's constant effects; its FormID, None with nothing to change."""
        constants, pairs = self.builder.perks.constants, b''
        for av, magnitude in self.values().items():
            effect = constants.get((av, False, True)) or constants.get((av, False, False))
            if not effect or abs(magnitude) < 0.01:
                self.builder.counts[f'player rule left out ({av:X})'] += not effect
                continue
            pairs += pack_subrecord('EFID', struct.pack('<I', effect))
            pairs += pack_subrecord('EFIT', struct.pack('<fII', magnitude, 0, 0))
        if not pairs:
            return None
        fid = self.builder.writer.derive_formid(SITES['SPEL'], ABILITY)
        template = self.builder.perks.vanilla[SPELL_TEMPLATE][1]
        self.builder.writer.add_record('SPEL', pack_spell(fid, ABILITY, '', template, pairs))
        self.builder.counts['SPEL (player rules)'] += 1
        return fid
