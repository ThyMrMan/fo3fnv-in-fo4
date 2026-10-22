"""FNV disguises on FO4: faction outfits keep their equip scripts, their quest joins the build, the pulse spell
converts, and DropMe drops.

See: docs/fork/fo4_pipeline.md#disguises
"""

import collections
import struct
from types import SimpleNamespace

from fo4_import.spike import equipment as E
from fo4_import.spike import quest_scope as QS
from fo4_import.spike import replacements as RP
from fo4_import.spike import script_effects as SE
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from tes5_import.base.tes5_reader import subrecords


def _writer(written: list) -> SimpleNamespace:
    """A plugin writer stub keeping (signature, record) in `written`."""
    return SimpleNamespace(derive_formid=lambda site, key: 0x01000000 + len(str(key)),
                           add_record=lambda sig, rec: written.append((sig, rec)))


def test_an_outfit_copy_carries_fnv_s_own_script_after_its_editor_id():
    """NCR Trooper Fatigues on FO4's clothes keep NCRFactionOutfitWarningScript (OnEquipped/OnUnequipped); the
    template's own VMAD stays dropped."""
    dnam = bytearray(100)
    dnam[E.DNAM_ANIM] = 1
    template = [(b'EDID', b'BaseballBat\0'), (b'VMAD', b'theirs'), (b'FULL', struct.pack('<I', 1)),
                (b'DNAM', bytes(dnam))]
    written, attached = [], []
    scripts = SimpleNamespace(vmad=lambda scpt: attached.append(scpt) or b'ours')
    builder = SimpleNamespace(counts=collections.Counter(), type_keywords=SimpleNamespace(of=lambda fnv: []),
                              writer=_writer(written), scripts=scripts)
    eq = E.Equipment.__new__(E.Equipment)
    eq.builder, eq.fnv, eq.vanilla, eq.by_anim, eq.strings = builder, {}, {'BaseballBat': template}, {}, {1: b'Bat'}
    eq.table = {'WeapScripted': RP.Replacement('Fallout4.esm', 'BaseballBat', 'stats')}
    eq.weapon_mods = eq.ammo_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire=lambda fnv, fid, subs: subs)
    eq.guns = SimpleNamespace(default_only=lambda subs: None)
    eq.weap(1, {'EditorID': 'WeapScripted', 'FULL': 'Bat', 'SCRI': '0012B03C'})
    subs = list(subrecords(written[0][1][24:]))
    assert [s for s, _ in subs][:2] == [b'EDID', b'VMAD'] and dict(subs)[b'VMAD'] == b'ours'
    assert attached == [0x12B03C]


def test_quest_scope_follows_what_actors_and_containers_carry():
    """An actor's inventory, its leveled entries and an inventory template reach an item; a template that does not
    give the inventory, and loose records, do not."""
    scope = QS.QuestScope.__new__(QS.QuestScope)
    npc = {'Item[0].FormID': '00000010', 'Item[0].Count': '1', 'ACBS.TemplateFlags': str(QS.USE_INVENTORY),
           'TPLT.Template': '00000030'}
    scope.holds = {0x1: QS._holds(npc), 0x10: QS._holds({'Entry[0].FormID': '00000020', 'Entry[0].Level': '1'}),
                   0x30: QS._holds({'Item[0].FormID': '00000031'}),
                   0x2: QS._holds({'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000040'}),
                   0x40: QS._holds({'Item[0].FormID': '00000041'})}
    assert scope._held({0x1}) == {0x10, 0x20, 0x30, 0x31}
    assert scope._held({0x2}) == set()


def _effects(builder) -> SE.ScriptEffects:
    """ScriptEffects over FNV's disguise pulse (DisguiseFactionPulseActorEffect) and a non-script effect."""
    fx = SE.ScriptEffects.__new__(SE.ScriptEffects)
    fx.builder, fx.made, fx.made_effects = builder, {}, {}
    fx.templates = ({b'DATA': bytes(152), b'ETYP': b'\x44\x3f\x01\x00'}, {b'ETYP': b'\x44\x3f\x01\x00'})
    fx.effects = {'DisguiseFactionPulseEffect': {'EditorID': 'DisguiseFactionPulseEffect', 'FormID': '001411A2',
                                                 'DATA.Flags': '7', 'DATA.AssocItem': '001411A4', 'FULL': 'Pulse'}}
    pulse = {'EditorID': 'DisguiseFactionPulseActorEffect', 'FormID': '001413D1', 'FULL': 'Disguise Faction Pulse',
             'SPIT.Type': '0', 'SPIT.Flags': '96', 'EffectCount': '1', 'Effect[0].EFID': 'DisguiseFactionPulseEffect',
             'Effect[0].Magnitude': '1', 'Effect[0].Area': '25', 'Effect[0].Duration': '5', 'Effect[0].Type': 'Touch',
             'Effect[0].ConditionCount': '0'}
    fx.spells = {'disguisefactionpulseactoreffect': pulse,
                 'restorehealth': {**pulse, 'Effect[0].EFID': 'RestoreHealth', 'EditorID': 'RestoreHealth'}}
    return fx


def test_the_disguise_pulse_becomes_a_fire_and_forget_touch_script_spell():
    """FNV's pulse (Touch, area 25, 5 s, scripted) takes vanilla BloodyMessNearbySpell's shape: SPIT fire and forget,
    Touch; one Script effect carrying the converted script; FNV's magnitude, area, duration and flags."""
    written = []
    scripts = SimpleNamespace(name=lambda scpt: 'FALLOUTNV_DisguiseFactionPulseScript', vmad=lambda scpt: b'vmad')
    builder = SimpleNamespace(counts=collections.Counter(), writer=_writer(written), scripts=scripts,
                              fnv_id=lambda fid: 0x02000000 | int(fid, 16))
    fx = _effects(builder)
    assert fx.spell('DisguiseFactionPulseActorEffect') == 0x021413D1 == fx.spell('disguisefactionpulseactoreffect')
    (_, mgef), (_, spel) = written
    effect = dict(subrecords(mgef[24:]))
    assert effect[b'VMAD'] == b'vmad' and struct.unpack_from('<I', effect[b'DATA'])[0] == 0x7
    assert struct.unpack_from('<II', effect[b'DATA'], SE.CAST_AT) == (SE.FIRE_AND_FORGET, SE.DELIVERY['Touch'])
    spell = dict(subrecords(spel[24:]))
    cost, flags, kind, _, cast, delivery = struct.unpack_from('<IIIfII', spell[b'SPIT'])
    assert (cost, flags, kind, cast, delivery) == (0, SE.MANUAL_COST | 0x200000, 0, SE.FIRE_AND_FORGET, 1)
    assert struct.unpack('<fII', spell[b'EFIT']) == (1.0, 25, 5)
    assert spell[b'EFID'] == mgef[12:16]


def test_a_spell_with_another_effect_is_left_out():
    """Only spells whose every effect is a converted script effect convert; others are counted, not made."""
    written = []
    builder = SimpleNamespace(counts=collections.Counter(), writer=_writer(written),
                              scripts=SimpleNamespace(name=lambda scpt: 'X'), fnv_id=lambda fid: int(fid, 16))
    assert _effects(builder).spell('RestoreHealth') is None and not written
    assert builder.counts['SPEL left out (not all unconditioned script effects)'] == 1


def test_dropme_drops_the_scripted_item():
    """DropMe (a companion refusing faction armor) is the item's Drop()."""
    src = 'scn T\nbegin OnAdd\n  DropMe\nend\n'
    out = ScriptConverter(CrossRefGraph()).convert_standalone('T', src, 'ObjectReference', 'T')
    assert 'Drop()' in out and 'TODO' not in out
