"""FNV weapon mods as Fallout 4 object mods: FNV's slot data, the OMOD layout and the parts a converted gun gets.

See: docs/fork/fo4_pipeline.md#weapon-mods
"""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM, FALLOUTNV_ESM
from fo4_import.spike import weapon_mods as WM
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

needs_games = pytest.mark.skipif(not (FALLOUT4_ESM.exists() and FALLOUTNV_ESM.exists()), reason='needs FO4 and FNV')


@pytest.fixture(scope='module')
def fo4():
    """Fallout4.esm's bytes, its keywords by EditorID and its OMODs {FormID: subrecords}."""
    raw = FALLOUT4_ESM.read_bytes()
    keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id for r, _ in walk(raw, b'KYWD')}
    mods = {r.form_id: list(subrecords(r.body)) for r, _ in walk(raw, b'OMOD')}
    weapons = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): list(subrecords(r.body))
               for r, _ in walk(raw, b'WEAP')}
    return SimpleNamespace(raw=raw, keywords=keywords, mods=mods, weapons=weapons)


def _builder(fo4):
    """A cell builder stand-in recording what is written; items.item gives an IMOD's loose mod 0xA000000 | FormID."""
    written = []
    return SimpleNamespace(
        fo4=fo4.raw, keywords=fo4.keywords, counts=Counter(), written=written,
        writer=SimpleNamespace(derive_formid=lambda site, key: hash((site, key)) & 0xFFFFFF,
                               add_record=lambda sig, rec: written.append((sig, rec))),
        items=SimpleNamespace(item=lambda fid: 0xA000000 | fid))


def _records(builder, sig: str) -> dict:
    """{EditorID: {sig: body}} of the records of `sig` written."""
    out = {}
    for kind, rec in builder.written:
        if kind == sig:
            subs = dict(subrecords(rec[24:]))
            out[subs[b'EDID'].rstrip(b'\0').decode()] = subs
    return out


def _props(subs: dict) -> list:
    """(value type, function, property, value 1, value 2) of an OMOD's properties."""
    return [WM.PROPERTY.unpack(p)[:5] for p in WM.parse_part(subs[b'DATA']).properties]


@needs_games
def test_fnv_slots_name_all_50_imods_with_effect_and_value():
    """35 FNV guns name all 50 IMODs; the varmint rifle's three are magazine +3, night scope 15 degrees, silencer."""
    guns, imods = WM.fnv_guns(FALLOUTNV_ESM.read_bytes())
    assert (len(guns), len(imods)) == (35, 50)
    assert {imod for gun in guns.values() for _, imod, _, _ in gun.slots} == set(imods)
    varmint = next(g for g in guns.values() if g.edid == 'WeapNVVarmintRifle')
    assert [(s, e, v) for s, _, e, v in varmint.slots] == [(0, WM.CAPACITY, 3.0), (1, WM.ZOOM, 15.0), (2, WM.SILENCE, 0.0)]
    assert varmint.night_vision and not varmint.automatic


@needs_games
def test_part_layout_round_trips_every_vanilla_omod(fo4):
    """parse_part then pack_part gives back every vanilla OMOD DATA unchanged."""
    for subs in fo4.mods.values():
        data = dict(subs)[b'DATA']
        assert WM.pack_part(WM.parse_part(data)) == data


@needs_games
def test_varmint_rifle_on_the_hunting_rifle_gets_its_magazine_scope_and_silencer(fo4):
    """Extended mags copy the hunting rifle's large magazine (model, no FO4 numbers) with capacity +3; the night
    scope is a scope with the night-vision preset and FNV's 15 degrees; the silencer is silent at the muzzle; the
    gun loses vanilla's ma_ keywords for its own, which every mod targets;"""
    builder = _builder(fo4)
    mods = WM.WeaponMods(builder, fo4.mods)
    fnv = next(fid for fid, g in mods.guns.items() if g.edid == 'WeapNVVarmintRifle')
    subs = mods.wire(fnv, fo4.weapons['HuntingRifle'])
    kw, names = fo4.keywords, {v: k for k, v in fo4.keywords.items()}
    ours = _records(builder, 'KYWD')['FNV_ma_WeapNVVarmintRifle']
    keywords = WM._ids(dict(subs)[b'KWDA'])
    assert not any(names.get(k, '').startswith('ma_') for k in keywords) and len(keywords) == struct.unpack(
        '<I', dict(subs)[b'KSIZ'])[0]
    omods = _records(builder, 'OMOD')
    mag, scope, silencer = (omods[f'FNV_mod_WeapNVVarmintRifle_ModNVVarmintRifle{n}'] for n in
                            ('ExtMags', 'NightScope', 'Silencer'))
    assert all(struct.unpack('<I', m[b'MNAM'])[0] in keywords for m in (mag, scope, silencer))
    assert ours[b'TNAM'] == struct.pack('<I', WM.MOD_ASSOCIATION)
    assert mag[b'MODL'] == b'Ammo\\308\\308LargeMag.nif\0'
    assert [p for p in _props(mag) if p[0] == WM.FLOAT] == [(WM.FLOAT, WM.ADD, WM.AMMO_CAPACITY,
                                                             struct.unpack('<I', struct.pack('<f', 3.0))[0], 0)]
    assert WM.parse_part(mag[b'DATA']).point == kw['ap_gun_Mag']
    zoom = {p[2]: p for p in _props(scope)}
    assert zoom[WM.ZOOM_DATA][3] == mods.zooms['ZM_Standard_Scope_x4_NightVision'][0]
    assert struct.unpack('<f', struct.pack('<I', zoom[WM.FOV_MULT][3]))[0] == pytest.approx(70.0 / 15.0)
    assert (WM.FORM, WM.ADD, WM.KEYWORDS, kw['dn_HasNightVision'], WM.KEYWORD_VALUE2) in _props(scope)
    silent = _props(silencer)
    assert (WM.ENUM, WM.SET, WM.SOUND_LEVEL, WM.SILENT, 0) in silent
    assert (WM.FORM, WM.ADD, WM.KEYWORDS, kw['HasSilencer'], WM.KEYWORD_VALUE2) in silent
    assert WM.parse_part(silencer[b'DATA']).point == kw['ap_gun_Muzzle']
    assert all(b'LNAM' in m for m in (mag, scope, silencer))


def test_each_mod_s_recipe_is_locked_behind_the_hidden_perk(fo4):
    """A mod recipe has no components or bench and needs the lock perk no one holds, so only a mod item fits it."""
    builder = _builder(fo4)
    mods = WM.WeaponMods(builder, fo4.mods)
    fnv = next(fid for fid, g in mods.guns.items() if g.edid == 'WeapNVVarmintRifle')
    mods.wire(fnv, fo4.weapons['HuntingRifle'])
    recipes, lock = _records(builder, 'COBJ'), _records(builder, 'PERK')[WM.LOCK_EDID]
    recipe = recipes['FNV_co_mod_WeapNVVarmintRifle_ModNVVarmintRifleExtMags']
    ctda = struct.unpack('<B3xfH2xI', recipe[b'CTDA'][:16])
    assert len(recipes) == len(_records(builder, 'OMOD')) == 3
    assert b'FVPA' not in recipe and b'BNAM' not in recipe
    assert ctda[1:] == (1.0, WM.HAS_PERK, builder.writer.derive_formid(WM.LOCK_SITE, WM.LOCK_EDID))
    assert lock[b'DATA'] == WM.LOCK_DATA


def test_effects_follow_fnv_semantics():
    """Damage and capacity add, weight subtracts, spread cuts the cones by FNV's share, fire rate speeds an automatic's
    animation or shortens a semi-automatic's delay, a split beam adds beams sharing the damage."""
    mods = WM.WeaponMods.__new__(WM.WeaponMods)
    semi, auto = WM.Gun('Semi', False, 0.8, False, ()), WM.Gun('Auto', True, 2.0, False, ())

    def floats(effect, value, gun):
        """(property, function, value 1) of the effect's float properties."""
        return [(p[2], p[1], round(struct.unpack('<f', struct.pack('<I', p[3]))[0], 4))
                for p in (WM.PROPERTY.unpack(e) for e in mods._effect(effect, value, gun)) if p[0] == WM.FLOAT]
    assert floats(WM.WEIGHT, 1.5, semi) == [(WM.WEIGHT_PROP, WM.ADD, -1.5)]
    assert floats(WM.SPREAD, 0.4, semi) == [(WM.MIN_CONE, WM.MUL_ADD, -0.5), (WM.MAX_CONE, WM.MUL_ADD, -0.5)]
    assert floats(WM.RATE, 0.3, auto) == [(WM.SPEED, WM.MUL_ADD, 0.3)]
    assert floats(WM.RATE, 0.333, semi) == [(WM.ATTACK_DELAY, WM.MUL_ADD, round(-0.333 / 1.333, 4))]
    assert floats(WM.SPLIT_BEAM, 2.0, semi) == [(WM.ATTACK_DAMAGE, WM.MUL_ADD, round(1 / 3 - 1, 4))]
    assert mods._effect(WM.CONDITION, 75.0, semi) == []
