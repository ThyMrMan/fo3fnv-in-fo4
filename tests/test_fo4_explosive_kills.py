"""Explosive kills: the explosions FNV's weapons set off carry a mark naming those weapons; their lists come last.

See: docs/fork/fo4_pipeline.md#challenges-explosives
"""

import collections
import struct
from types import SimpleNamespace

from fo4_import.spike import explosive_kills as K
from fo4_import.spike.attack_spells import ENIT_EXPLOSION
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def _kills(written: list, vanilla: 'dict | None' = None) -> K.ExplosiveKills:
    """ExplosiveKills over FNV explosion 0x30 (set off by weapons 0x10 and 0x11), recording (sig, body) written."""
    kills = K.ExplosiveKills.__new__(K.ExplosiveKills)
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x01000000 + len(str(key)), own_index=1,
                             add_record=lambda sig, body: written.append((sig, body)))
    effects = SimpleNamespace(vmad_effect=lambda edid, vmad, delivery, flags=0: written.append(('MGEF', flags)) or 0x77)
    kills.builder = SimpleNamespace(writer=writer, counts=collections.Counter(), fo4=b'',
                                    scripts=SimpleNamespace(used=[], effects=effects, vmad=lambda fid, scripts: b'v'))
    kills.weapons, kills.lists, kills.effects, kills.enchantments = {0x30: [0x10, 0x11]}, {}, {}, {}
    kills.vanilla = vanilla
    return kills


def _pairs(body: bytes) -> list:
    """The EFID FormIDs of a written ENCH."""
    return [struct.unpack('<I', data)[0] for tag, data in subrecords(body[24:]) if tag == b'EFID']


def test_explosions_map_to_the_weapons_setting_them_off(monkeypatch):
    """A weapon's projectile's explosion lists that weapon; a projectile with no explosion lists none."""
    recs = {'PROJ': [{'FormID': '00000001', 'DATA.Explosion': '00000030'}, {'FormID': '00000002'}],
            'WEAP': [{'FormID': '00000010', 'DNAM.Projectile': '00000001'},
                     {'FormID': '00000011', 'DNAM.Projectile': '00000001'},
                     {'FormID': '00000012', 'DNAM.Projectile': '00000002'}]}
    monkeypatch.setattr(K, 'export_records', lambda path, sig: recs[sig])
    assert K.explosion_weapons('x') == {0x30: [0x10, 0x11]}


def test_a_weapons_explosion_carries_fnvs_effects_and_the_mark_once():
    """FNV's converted pairs, then the No Death Dispel mark, as EITM before MNAM; a second copy reuses both."""
    written = []
    kills = _kills(written)
    subs = [(b'EDID', b''), (b'MNAM', b''), (b'DATA', b'')]
    fnv = pack_subrecord('EFID', struct.pack('<I', 0x55)) + pack_subrecord('EFIT', bytes(12))
    out = kills.marked(subs, {'FormID': '00000030', 'EditorID': 'GrenadeFragExplosion'}, lambda: fnv)
    again = kills.marked(subs, {'FormID': '00000030', 'EditorID': 'GrenadeFragExplosion'}, lambda: fnv)
    assert [t for t, _ in out] == [b'EDID', b'EITM', b'MNAM', b'DATA'] and out == again
    (_, flags), (sig, ench) = written
    assert flags == K.NO_DEATH_DISPEL and sig == 'ENCH' and _pairs(ench) == [0x55, 0x77]
    assert dict(subrecords(ench[24:]))[b'ENIT'] == ENIT_EXPLOSION


def test_a_stand_ins_own_effect_is_kept_beside_the_mark():
    """A stand-in's Fallout4.esm enchantment: its ENIT and pairs go into the marked copy."""
    written, enit = [], bytes(range(36))
    vanilla = {0x99: [(b'EDID', b'x\0'), (b'ENIT', enit), (b'EFID', struct.pack('<I', 0x44)), (b'EFIT', bytes(12))]}
    kills = _kills(written, vanilla)
    subs = [(b'EDID', b''), (b'EITM', struct.pack('<I', 0x99)), (b'DATA', b'')]
    out = kills.marked(subs, {'FormID': '00000030', 'EditorID': 'GrenadePlasmaExplosion'}, lambda: b'')
    ench = written[-1][1]
    assert [t for t, _ in out].count(b'EITM') == 1 and _pairs(ench) == [0x44, 0x77]
    assert dict(subrecords(ench[24:]))[b'ENIT'] == enit


def test_an_explosion_no_weapon_sets_off_is_left_alone_and_lists_come_last():
    """A car's explosion gets no mark; the weapon list holds the made weapons, and the script is used."""
    written = []
    kills = _kills(written)
    assert kills.marked([(b'DATA', b'')], {'FormID': '00000099', 'EditorID': 'CarExplosion'}, lambda: b'') is None
    kills.marked([(b'DATA', b'')], {'FormID': '00000030', 'EditorID': 'G'}, lambda: b'')
    kills.write({0x10: 0x5010}.get)
    sig, body = written[-1]
    members = [struct.unpack('<I', d)[0] for t, d in subrecords(body[24:]) if t == b'LNAM']
    assert sig == 'FLST' and members == [0x5010] and kills.builder.scripts.used == [K.SCRIPT]
