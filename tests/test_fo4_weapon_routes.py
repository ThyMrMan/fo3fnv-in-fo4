"""fo4_import.spike.weapon_routes and weapon_checks: the route ladder, the stand-ins, the report, the checks.

See: docs/fork/fo4_weapon_routes_plan.md#order
"""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.spike import gun_choice as GC
from fo4_import.spike import replacements as RP
from fo4_import.spike import weapon_checks as WC
from fo4_import.spike.weapon_routes import WeaponRoutes


def _rec(edid: str, fnv: int, model: str = '', anim: int = 3) -> dict:
    """A WEAP export record."""
    return {'EditorID': edid, 'FormID': f'{fnv:08X}', 'Model.MODL': model, 'DNAM.FalloutAnimType': str(anim)}


def _routes(*records) -> WeaponRoutes:
    """Routes over the defaults plus WeapNV10mmPistol, from WEAP `records`."""
    table = RP.Table.of({'WeapNV10mmPistol': RP.Replacement(RP.BASE, '10mm', 'fnv', category='weapon')})
    return WeaponRoutes(table, records, Counter())


def test_a_variant_takes_the_listed_weapon_s_entry_by_model():
    """A weapon sharing a listed weapon's model (any case or slash) takes its entry, named in how."""
    listed = _rec('WeapNV10mmPistol', 1, 'Weapons\\10mmPistol\\10mm.nif')
    routes = _routes(listed)
    variant = _rec('WeapNV10mmPistolUnique', 2, 'weapons/10MMPISTOL/10mm.nif')
    entry, how = routes.listed(variant)
    assert entry.edid == '10mm' and how == 'same model as WeapNV10mmPistol'
    assert routes.listed(listed)[1] == 'hand table' and routes.listed(_rec('Other', 3, 'x.nif')) is None


def test_anything_unlisted_and_not_its_own_gun_takes_its_type_s_stand_in():
    """A modelless gun and a thrown weapon take their animation type's rule; a modelled gun waits for its mesh."""
    routes = _routes()
    assert routes.entry(_rec('NoModel', 1, '', 5)).edid == 'HuntingRifle'
    assert routes.entry(_rec('Spear', 2, 'spear.nif', 13)).edid == 'fragGrenade'
    assert routes.entry(_rec('ModGun', 3, 'modgun.nif', 5)) is None
    turret = {**_rec('TurretLaser', 4, '', 5), 'DNAM.Flags1': '128'}
    assert routes.entry(turret) is None and routes.entry({**turret, 'Model.MODL': 'gun.nif'}) is None


def test_a_decided_entry_wins_and_every_route_is_reported(tmp_path, monkeypatch):
    """demoted() makes the template's mesh the entry from then on; write() lists each route with its checks."""
    monkeypatch.setattr('fo4_import.spike.weapon_routes.moved_in', lambda path: path)
    routes = _routes()
    gun = _rec('ModGun', 3, 'modgun.nif', 5)
    routes.demoted(gun, 'HuntingRifle', 'no ProjectileNode in its mesh', {'muzzle': 'no'})
    routes.note(_rec('Bat', 4, 'bat.nif', 2), 'type rule', 'BaseballBat')
    assert (routes.entry(gun).edid, routes.entry(gun).mode) == ('HuntingRifle', 'stats')
    assert routes.counts == Counter({'weapon route (template mesh)': 1, 'weapon route (type rule)': 1})
    assert routes.write(tmp_path / 'Mod.esp') == 2
    lines = (tmp_path / 'Mod.esp.weapons.tsv').read_text(encoding='utf-8').splitlines()
    assert lines[1] == 'ModGun\t00000003\ttemplate mesh\tHuntingRifle\tno ProjectileNode in its mesh\tmuzzle=no'


def test_a_semi_automatic_gun_fires_at_fnv_s_rate():
    """The anti-materiel rifle's 0.448 shots a second on a Speed 1.25 copy is Attack Delay 2.79; an automatic
    FNV gun and a bolt-action copy keep the template's."""
    dnam = bytearray(140)
    struct.pack_into('<f', dnam, GC.DNAM_SPEED, 1.25)
    rec = {'DNAM.ShotsPerSec': '0.448', 'DNAM.Flags1': '0'}
    assert GC.paced(dnam, rec) and struct.unpack_from('<f', dnam, GC.DNAM_ATTACK_DELAY)[0] == pytest.approx(2.79, 0.01)
    assert not GC.paced(dnam, {**rec, 'DNAM.Flags1': str(GC.FNV_AUTOMATIC)})
    struct.pack_into('<I', dnam, GC.DNAM_FLAGS, GC.FO4_BOLT_ACTION)
    assert not GC.paced(dnam, rec)


def test_a_gun_without_a_projectile_node_fails_before_its_clips_are_built():
    """No ProjectileNode fails the muzzle check; one whose clips do not convert plays the template's and passes."""
    built = []
    guns = SimpleNamespace(preview=lambda rec, chosen, clip: built.append(clip))
    checks = WC.WeaponChecks(guns)
    assert checks.failed({}, (None, None, (None, None, None, {'Gun'}))) == (
        'no ProjectileNode in its mesh', {'muzzle': 'no'})
    assert not built
    assert checks.failed({}, (None, None, (None, None, None, {WC.MUZZLE}))) == (
        '', {'muzzle': 'yes', 'clips': 'template'})
    assert built == [WC.SIGHTED]


def test_only_a_rifle_fails_on_its_hand_in_view(monkeypatch):
    """A rifle aiming with 50% of its hand in view drops; a pistol (aimed hand in view) is reported only."""
    guns = SimpleNamespace(preview=lambda rec, chosen, clip: (SimpleNamespace(lift=0.0), b'clip'))
    checks = WC.WeaponChecks(guns)
    checks.arms = SimpleNamespace(hand_share=lambda clip, lift: 0.5)
    chosen = (None, None, (None, None, None, {WC.MUZZLE}))
    assert checks.failed({'DNAM.FalloutAnimType': '5'}, chosen)[0] == '50% of the right hand in view while aiming'
    assert checks.failed({'DNAM.FalloutAnimType': '3'}, chosen) == ('', {'muzzle': 'yes', 'aim_hand': '50%'})
