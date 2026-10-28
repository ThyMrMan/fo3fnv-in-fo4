"""FNV Hardcore need effects on consumables as Fallout 4 Survival's hunger, thirst and sleep.

See: docs/fork/fo4_pipeline.md#survival-needs
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.spike import consumable_effects as CE
from fo4_import.spike import consumables as CS
from fo4_import.spike import survival_needs as S

#: FalloutNV.esm's IsHardcore == 1 condition, as its water carries it.
IS_HARDCORE = '000000000000803F4A02000000000000000000000000000000000000'
EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
#: FNV points per game hour: 120 real seconds per hour over 25, 10 and 50 seconds per point.
PER_HOUR = {S.HUNGER: 4.8, S.THIRST: 12.0, S.SLEEP: 2.4}


def _rec(*effects) -> dict:
    """An FNV export ALCH with (EFID, magnitude, conditions) effects."""
    rec = {'EditorID': 'Test', 'EffectCount': str(len(effects))}
    for i, (edid, magnitude, conds) in enumerate(effects):
        key = f'Effect[{i}]'
        rec.update({f'{key}.EFID': edid, f'{key}.Magnitude': str(magnitude), f'{key}.Area': '0',
                    f'{key}.Duration': '0', f'{key}.ActorValue': '73', f'{key}.ConditionCount': str(len(conds))})
        rec.update({f'{key}.Condition[{j}].Raw': raw for j, raw in enumerate(conds)})
    return rec


def _needs(monkeypatch) -> tuple:
    """A SurvivalNeeds on stand-in records, and the [(edid, VMAD or keywords)] it writes."""
    written = []
    monkeypatch.setattr(S, 'hotkey_effect', lambda b, fid, edid, name, vmad: written.append((edid, vmad)))
    monkeypatch.setattr(S, 'hotkey_item', lambda b, fid, edid, name, effect, kw: written.append((edid, kw)))
    builder = SimpleNamespace(counts=Counter(), scripts=SimpleNamespace(used=[]),
                              writer=SimpleNamespace(derive_formid=lambda site, key: hash(key) & 0xFFFFFF))
    vanilla = {k: (0x100 + i, {}) for i, k in enumerate(sorted({*S.WANTED, CE.NO_EFFECT}))}
    return S.SurvivalNeeds(builder, vanilla, PER_HOUR), written


def test_need_effects_count_hardcore_as_on_and_other_effects_as_off():
    """An IsHardcore-gated need effect runs; an IsHardcore-gated heal does not."""
    rec = _rec(('RestoreDehydrationLevel', 50, [IS_HARDCORE]), ('RestoreHealth', 2, [IS_HARDCORE]))
    assert [e[0] for e in CE.fnv_effects(rec)] == ['RestoreDehydrationLevel']


def test_food_and_drink_cover_the_same_hours_in_survival(monkeypatch):
    """FNV's hours of need at Survival's 4 per hour; one effect per amount; a raise is negative."""
    needs, written = _needs(monkeypatch)
    assert needs.effects('RestoreDehydrationLevel', 50)[0][1] == 17.0
    assert needs.effects('RestoreStarvationLevel', 50)[0][1] == 42.0
    assert needs.effects('RestoreStarvationLevel', 1)[0][1] == 1.0
    assert needs.effects('DamageDehydrationLevel', 25)[0][1] == 8.0
    needs.effects('RestoreDehydrationLevel', 50)
    assert len(written) == 4 and needs.builder.scripts.used == [S.SCRIPT] * 4
    assert struct.pack('<f', -8.0) in dict(written)['FNV_Survival_DamageDehydrationLevel_25']


def test_sleep_becomes_survival_caffeine_by_hours_and_raised_sleep_is_dropped(monkeypatch):
    """Under EXTRA_AT hours is Caffeinated, from it Extra Caffeinated; each tier's potion is written once."""
    needs, written = _needs(monkeypatch)
    small = needs.effects('RestoreSleepDeprivationLevel', 5)
    large = needs.effects('RestoreSleepDeprivationLevel', 15)
    assert (small[0][1], large[0][1]) == S.CAFFEINE_HOURS
    needs.effects('RestoreSleepDeprivationLevel', 100)
    potions = [kw for edid, kw in written if isinstance(kw, tuple)]
    assert sorted(len(kw) for kw in potions) == [1, 2]
    assert needs.effects('DamageSleepDeprivationLevel', 10) == []


def test_item_with_need_effects_is_hidden_from_survivals_price_feeding():
    """HC_IgnoreAsFood on an item with need effects, none on one without."""
    assert CS.survival_keyword(_rec(('RestoreStarvationLevel', 50, [IS_HARDCORE]))) == S.IGNORE_AS_FOOD
    assert CS.survival_keyword(_rec(('RestoreHealth', 2, []))) is None


@pytest.mark.skipif(not (EXPORT / 'GMST.txt').exists(), reason='needs the FalloutNV.esm export')
def test_fnv_rates_come_from_its_settings_and_timescale():
    """The ESM's 25 s hunger, 50 s sleep, the exe's 10 s thirst, TimeScale 30."""
    assert S.fnv_per_hour(EXPORT) == pytest.approx(PER_HOUR)


def test_an_embedded_guns_ammo_fires_its_templates_projectile():
    """write_ammo writes each ammo() on the 5.56 round's DNAM; ammo an embedded gun fires takes the projectile of
    its FO4 template's ammo (the lowest FNV weapon FormID's), other ammo keeps the 5.56 projectile."""
    added = []
    cons = CS.Consumables.__new__(CS.Consumables)
    cons.builder = SimpleNamespace(counts=Counter(), projectiles=SimpleNamespace(ammo=lambda fnv: None),
                                   writer=SimpleNamespace(derive_formid=lambda site, key: 0x03000000 | key,
                                                          add_record=lambda sig, rec: added.append(rec)))
    cons.vanilla = {CS.AMMO_TEMPLATE: (0x1F278, {b'DNAM': struct.pack('<I', 0x481F) + bytes(12)})}
    cons.projectiles, cons.fired_by = {0xC1897: struct.pack('<I', 0x9C663), 0xCABA3: struct.pack('<I', 0xCABA4)}, {}
    cons.pending = {0xA1: (b'', b''), 0xA2: (b'', b'')}
    cons.fired_from(0xA1, 0x20, 0xCABA3)
    cons.fired_from(0xA1, 0x10, 0xC1897)
    cons.write_ammo()
    projectiles = [struct.unpack_from('<I', rec, 24 + 6)[0] for rec in added]
    assert projectiles == [0x9C663, 0x481F]


def test_other_ammo_fires_its_own_fnv_projectile():
    """Ammo no creature gun fires takes the projectile spike.projectiles gives it; a creature gun's still wins."""
    added = []
    cons = CS.Consumables.__new__(CS.Consumables)
    cons.builder = SimpleNamespace(counts=Counter(), projectiles=SimpleNamespace(ammo=lambda fnv: 0x125C9B),
                                   writer=SimpleNamespace(derive_formid=lambda site, key: 0x03000000 | key,
                                                          add_record=lambda sig, rec: added.append(rec)))
    cons.vanilla = {CS.AMMO_TEMPLATE: (0x1F278, {b'DNAM': struct.pack('<I', 0x481F) + bytes(12)})}
    cons.projectiles, cons.fired_by = {0xC1897: struct.pack('<I', 0x9C663)}, {}
    cons.pending = {0xA1: (b'', b''), 0xA2: (b'', b'')}
    cons.fired_from(0xA1, 0x10, 0xC1897)
    cons.write_ammo()
    assert [struct.unpack_from('<I', rec, 24 + 6)[0] for rec in added] == [0x9C663, 0x125C9B]
