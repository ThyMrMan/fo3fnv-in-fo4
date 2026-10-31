"""FNV's player health, speed and V.A.T.S. damage on Fallout 4 (spike.combat_feel)."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import combat_feel as F

FNV = {'fAVDHealthEnduranceMult': 20.0, 'fAVDHealthLevelMult': 5.0, 'fAVDHealthEnduranceOffset': 0.0,
       'fVATSPlayerDamageMult': 0.75, 'fMoveBaseSpeed': 77.0, 'fMoveRunMult': 4.0}


def test_fnvs_health_mults_and_vats_damage_become_fo4_settings():
    """Endurance x 20, level x 5; V.A.T.S. slowed, FNV's damage taken."""
    assert F.fo4_settings(FNV) == {'fAVDHealthStartEndMult': 20.0, 'fHealthEnduranceMult': 0.0,
                                   'fHealthEnduranceOffset': 5.0, 'fVATSTimeMultTargetSelect': F.VATS_SLOW,
                                   'fVATSPlayerDamageMult': 0.75}


def test_the_ability_closes_the_base_health_and_run_speed_gaps():
    """FNV base 100 against FO4's 80 is +20 Health; run 308 against 372.98 is SpeedMult -17.4."""
    rules = F.PlayerRules.__new__(F.PlayerRules)
    rules.fnv, rules.fnv_base, rules.fo4_base, rules.fo4_run = FNV, 100.0, 80.0, 372.98
    values = rules.values()
    assert values[F.HEALTH] == 20.0 and round(values[F.SPEED_MULT], 1) == -17.4


def test_prps_reads_one_actor_value():
    """The float paired with the actor value; 0 when absent."""
    subs = {b'PRPS': struct.pack('<IfIf', 0x2D4, 40.0, 0x2DA, 100.0)}
    assert F.prps_value(subs, 0x2D4) == 40.0 and F.prps_value(subs, 0x2C2) == 0.0 and F.prps_value({}, 1) == 0.0


def test_the_ability_is_left_out_when_nothing_changes():
    """No gap and no effect: no spell."""
    rules = F.PlayerRules.__new__(F.PlayerRules)
    rules.builder = SimpleNamespace(perks=SimpleNamespace(constants={}), counts=Counter())
    rules.values = lambda: {F.HEALTH: 0.0}
    assert rules.write() is None
