"""The Fallout4.esm explosion an FNV/FO3 explosion's copy stands on, by the first route that finds one:

1. its namesake in Fallout4.esm;
2. STAND_INS by EditorID, then MODEL_STAND_INS by explosion art (the hand tables);
3. same art: the stand-in of a listed explosion (one 1-2 place) with the same art;
4. same kind: of a listed explosion of its kind (ExplosionRoutes.kind);
5. same damage: of a listed explosion that, like it, does damage or does none.

Among several, the one with the same impact data set, then the nearest outer radius, wins (gap). Only an export
with no listed explosion leaves one out.

See: docs/fork/fo4_pipeline.md#explosion-routes
"""

import math

#: FNV explosion EditorID -> the Fallout4.esm explosion standing in (none of these has a namesake).
STAND_INS = {
    'SmallNukeExplosion': 'CarNukeLargeVehicles', 'MediumExplosion': 'CarExplosion',
    'LargeExplosion': 'CarExplosion', 'MotorcycleExplosion': 'CarNukeSmallVehicles',
    'VMS08MonorailExplosion': 'CarNukeLargeVehicles', 'FFE08Explosion': 'CarNukeLargeVehicles',
    'NellisMunitionsExplosion': 'CarExplosion', 'VertibirdExplosion': 'VertibirdDeathExplosion',
    'GrenadeFragExplosion': 'fragGrenadeExplosion', 'AmmoBoxExplosion': 'fragGrenadeExplosion',
    'MineFragExplosion': 'fragMineExplosion', 'GrenadePlasmaExplosion': 'plasmaGrenadeExplosion',
    'ElectricBoxExplosion': 'ElectricalExplosionSmall', 'ElectricBoxExplosionSecurtronVault': 'ElectricalExplosionSmall',
    'vHDGeneratorExplosion': 'ElectricalExplosionSmall', 'HVRadioExplosion': 'ElectricalExplosionSmall',
    'GasTrapFireBurst': 'ExplosionTrapGas', 'V22GasTrapFireBurst': 'ExplosionTrapGas',
    'ExplosionFlamerCritEffect': 'ExplosionTrapGas', 'BloatFlyExplosion': 'GoreInsectSmallExplosion',
}
#: FNV explosion art (lower-case Model.MODL, '/') -> the Fallout4.esm explosion standing in after name and STAND_INS.
MODEL_STAND_INS = {
    'effects/fxnullexplosionart.nif': 'FakeForce100Explosion', 'effects/explosiongrenadefrag.nif': 'fragGrenadeExplosion',
    'effects/explosiongenericl01.nif': 'CarExplosion', 'effects/explosionlarge01.nif': 'FatManExplosion',
    'effects/fxpulseexplosion01.nif': 'pulseGrenadeExplosion', 'effects/fxexplosionplasma.nif': 'plasmaGrenadeExplosion',
    'effects/fxglowingonesburst.nif': 'GlowingOneResurrectExplosion', 'effects/fxmegatonnuke01.nif': 'CGPrewarNuke',
    'effects/fxravenrockexplosion01.nif': 'CarExplosion', 'effects/fxflashbangexplosion.nif': 'fragGrenadeExplosion',
}
#: An MGEF's Resist Value when it names none (-1 as the export writes it).
NO_RESIST = '4294967295'


def art(rec: dict) -> str:
    """EXPL export record `rec`'s art: lower-case Model.MODL with '/'; '' without one."""
    return rec.get('Model.MODL', '').replace(chr(92), '/').lower()


def effect_kinds(enchantments: dict, effects) -> dict:
    """{ENCH FormID: its first effect's resist value, else that effect's EditorID} of `enchantments` ({FormID:
    export record}) over MGEF export records `effects`."""
    resist = {rec.get('EditorID'): rec.get('DATA.ResistValue') for rec in effects}
    out = {}
    for fid, rec in enchantments.items():
        name = rec.get('Effect[0].EFID', '')
        out[fid] = name if resist.get(name) in (None, NO_RESIST) else resist[name]
    return out


def gap(one: dict, other: dict) -> tuple:
    """(impact data sets differ, log ratio of outer radii) of two EXPL records."""
    radius = [float(rec.get('DATA.Radius') or 0) + 1 for rec in (one, other)]
    return one.get('DATA.ImpactDataSet') != other.get('DATA.ImpactDataSet'), abs(math.log(radius[0] / radius[1]))


class ExplosionRoutes:
    """One build's explosion routes over Fallout4.esm's explosions and the export's (its masters' too)."""

    def __init__(self, names: dict, explosions: dict, kinds):
        """FO4 {EditorID: FormID}, export {FormID: EXPL}, kinds() -> effect_kinds()."""
        self.names, self.explosions, self.kinds, self.pool = names, explosions, kinds, None

    def listed(self, rec: dict) -> 'tuple | None':
        """(route, Fallout4.esm EditorID) of EXPL `rec` by its namesake or the hand tables; None."""
        name = rec.get('EditorID', '')
        for route, target in (('namesake', name), ('hand table', STAND_INS.get(name)),
                              ('art table', MODEL_STAND_INS.get(art(rec)))):
            if target in self.names:
                return route, target
        return None

    def kind(self, rec: dict) -> tuple:
        """(enchantment effect kind or None, does damage) of EXPL `rec`."""
        fid = int(rec.get('EITM') or '0', 16)
        return (self.kinds().get(fid, fid) if fid else None), float(rec.get('DATA.Damage') or 0) > 0

    def route(self, rec: dict) -> 'tuple | None':
        """(route, Fallout4.esm EditorID, the listed EditorID it follows or '') of EXPL `rec`; None."""
        found = self.listed(rec)
        if found:
            return *found, ''
        if self.pool is None:
            self.pool = sorted(((r, self.listed(r)[1]) for r in self.explosions.values() if self.listed(r)),
                               key=lambda pair: pair[0].get('EditorID', ''))
        kind = self.kind(rec)
        for route, test in (('same art', lambda r: art(r) and art(r) == art(rec)),
                            ('same kind', lambda r: self.kind(r) == kind),
                            ('same damage', lambda r: self.kind(r)[1] == kind[1])):
            near = [pair for pair in self.pool if test(pair[0])]
            if near:
                other, target = min(near, key=lambda pair: gap(pair[0], rec))
                return route, target, other.get('EditorID', '')
        return None
