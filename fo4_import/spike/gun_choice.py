"""Which Fallout 4 gun an FNV gun is built on: one held and fired like it, its parts laid out nearest.

Every playable FO4 gun (animation type Gun) with a default receiver is a
candidate: its default part combination, and that combination with each
receiver and grip its other combinations use swapped in. A candidate's
stance comes from the keywords its record and parts give (the AnimsGrip
ones first: AnimsGripPistol is a pistol, AnimsGripRifle* a rifle; else
WeaponTypePistol / WeaponTypeRifle), its firing mode from its parts'
IsAutomatic, else the record's Automatic flag, and whether it is a shotgun
from its projectile count (the parts' NumProjectiles, else FNAM's) over 1.
FNV's stance comes from its animation type (STANCES), its mode from
DNAM.Flags1 Is Automatic, a shotgun from DNAM.ProjectileCount. Among the
candidates matching all three, the nearest layout wins: the magazine mouth's and
the muzzle's offsets from the trigger, across and up (the muzzle weighted
MUZZLE_WEIGHT); ties go to the lower FormID.

See: docs/fork/fo4_spikes.md#spike-4-guns
"""

import math
import struct
from dataclasses import dataclass

import numpy as np

from asset_convert.havok.gun_vocabulary_falloutnv import FNV_AUTOMATIC
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

#: FNV WEAP animation type -> stance: one-handed pistols, two-handed rifles (xEdit's wbWeaponAnimTypeEnum).
STANCES = {3: 'pistol', 4: 'pistol', 5: 'rifle', 6: 'rifle', 7: 'rifle'}
#: FNV animation types that are guns (pistols to launchers).
GUN_TYPES = range(3, 10)
#: FO4 WEAP: DNAM animation type Gun, flags offset and its Automatic, Not Playable and Embedded bits.
ANIM_GUN, DNAM_ANIM, DNAM_FLAGS = 9, 54, 48
FO4_AUTOMATIC, FO4_NOT_PLAYABLE, FO4_EMBEDDED = 0x8000, 0x100000, 0x80000
NON_PLAYABLE_RECORD = 0x4
#: OMOD DATA: include and property counts, the attach point; a property is 24 bytes, its kind at 8.
DATA_ATTACH_POINT, PROPERTY_SIZE = 16, 24
#: Where a property's first value sits in it.
PROPERTY_VALUE = 12
#: OMOD properties (xEdit's wbWeaponPropertyEnum): IsAutomatic, Keywords, NumProjectiles; FormID function REM.
PROP_AUTOMATIC, PROP_KEYWORDS, PROP_PROJECTILES, FORM_REMOVE = 25, 31, 51, 1
#: OMOD property ZoomData (xEdit's wbWeaponPropertyEnum 67): a scope's ZOOM record.
PROP_ZOOM = 67
#: FNV WEAP DNAM.Flags1 Has Scope and DNAM.Flags2 Scope from Mod (xEdit's wbDefinitionsFNV WEAP DNAM).
FNV_HAS_SCOPE, FNV_SCOPE_FROM_MOD = 0x4, 0x2000
#: Fallout4.ini fDefaultWorldFOV, which a ZOOM's FOV multiplier divides.
FO4_WORLD_FOV = 70.0
#: FO4 WEAP FNAM: the projectile count byte.
FNAM_PROJECTILES = 28
POINTS = {'receiver': 'ap_gun_receiver', 'grip': 'ap_gun_Grip', 'scope': 'ap_gun_Scope'}
#: OBTS: its default flag, keyword count; an include is 7 bytes.
OBTS_DEFAULT, OBTS_KEYWORDS, INCLUDE_SIZE = 14, 15, 7
MUZZLE_WEIGHT = 0.25


@dataclass(frozen=True)
class Choice:
    """A FO4 gun to build on: its EditorID, default combination's includes (swaps made), receiver mod and
    model, and the receiver's layout (gun.receiver_layout)."""
    weapon: str
    includes: tuple
    receiver: 'int | None'
    model: str
    layout: dict


def includes_at(obts: bytes) -> int:
    """Where an OBTS's includes start: past its header, keywords, two level bytes."""
    return OBTS_KEYWORDS + 1 + 4 * obts[OBTS_KEYWORDS] + 2


def includes(obts: bytes) -> list:
    """An OBTS's include mod FormIDs."""
    start = includes_at(obts)
    return [struct.unpack_from('<I', obts, start + INCLUDE_SIZE * i)[0] for i in range(struct.unpack_from('<I', obts)[0])]


def properties(data: bytes) -> list:
    """[(value type, function, property, value 1 bytes)] of an OMOD DATA (they end it)."""
    count = struct.unpack_from('<I', data, 4)[0]
    start = len(data) - PROPERTY_SIZE * count
    return [struct.unpack_from('<B3xB3xH2x4s', data, start + PROPERTY_SIZE * i) for i in range(count)]


def traded(data: bytes, replaces: dict) -> bytes:
    """OMOD DATA `data` with each keyword its properties add or remove that `replaces` names swapped for the new."""
    out = bytearray(data)
    count = struct.unpack_from('<I', data, 4)[0]
    for i in range(count):
        at = len(data) - PROPERTY_SIZE * (count - i)
        _, _, prop, value = struct.unpack_from('<B3xB3xH2x4s', data, at)
        kw = struct.unpack('<I', value)[0]
        if prop == PROP_KEYWORDS and kw in replaces:
            struct.pack_into('<I', out, at + PROPERTY_VALUE, replaces[kw])
    return bytes(out)


def fnv_wants(rec: dict) -> tuple:
    """(stance or None, automatic, shotgun) of an FNV WEAP export record."""
    return (STANCES.get(int(rec.get('DNAM.FalloutAnimType', -1))), bool(int(rec.get('DNAM.Flags1', 0)) & FNV_AUTOMATIC),
            int(rec.get('DNAM.ProjectileCount', 1)) > 1)


def built_in_scope(rec: dict) -> bool:
    """Whether FNV gun `rec` has a scope of its own (Has Scope, not Scope from Mod).
    See: docs/fork/fo4_spikes.md#spike-4-gun-clips
    """
    return bool(int(rec.get('DNAM.Flags1', 0)) & FNV_HAS_SCOPE and not int(rec.get('DNAM.Flags2', 0)) & FNV_SCOPE_FROM_MOD)


class GunChoices:
    """FO4's playable guns as candidates for FNV guns, indexed once."""

    def __init__(self, fo4: bytes, mods: dict, keywords: dict, layouts):
        """Candidates from Fallout4.esm `fo4`; `mods` {FormID: OMOD subrecords}, `keywords` {EditorID: FormID},
        `layouts(model)` a receiver model's layout."""
        self.mods, self.layouts = mods, layouts
        self.names = {fid: name for name, fid in keywords.items()}
        self.points = {kind: keywords[name] for kind, name in POINTS.items()}
        self.weapons, self.candidates = {}, []
        self.zooms = {r.form_id: struct.unpack_from('<fII', first_sub(r.body, b'GNAM'))
                      for r, _ in walk(fo4, b'ZOOM')}
        for rec, _ in walk(fo4, b'WEAP'):
            subs = list(subrecords(rec.body))
            self.weapons[_edid(subs)] = (rec.form_id, subs)
            if self._playable_gun(rec, subs):
                self.candidates.append(_edid(subs))

    def _playable_gun(self, rec, subs: list) -> bool:
        """Whether a WEAP is a playable gun with a default combination."""
        d = dict(subs)
        dnam = d.get(b'DNAM', b'')
        if rec.flags & NON_PLAYABLE_RECORD or len(dnam) <= DNAM_ANIM or dnam[DNAM_ANIM] != ANIM_GUN:
            return False
        flags = struct.unpack_from('<I', dnam, DNAM_FLAGS)[0]
        return not flags & (FO4_NOT_PLAYABLE | FO4_EMBEDDED) and any(
            s == b'OBTS' and b[OBTS_DEFAULT] for s, b in subs)

    def attach(self, fid: int) -> int:
        """An OMOD's attach point keyword."""
        return struct.unpack_from('<I', dict(self.mods[fid])[b'DATA'], DATA_ATTACH_POINT)[0]

    def model(self, fid: int) -> str:
        """An OMOD's model ('' for none)."""
        return dict(self.mods.get(fid, [])).get(b'MODL', b'\0').rstrip(b'\0').decode('cp1252')

    def _of(self, kind: str, fids) -> list:
        """The mods in `fids` at `kind`'s point (receivers: with a model)."""
        return [f for f in fids if f in self.mods and self.attach(f) == self.points[kind]
                and (kind != 'receiver' or self.model(f))]

    def scope(self, combo) -> 'int | None':
        """The sights mod with a model in a combination, or None."""
        return next((f for f in self._of('scope', combo) if self.model(f)), None)

    def _variants(self, subs: list) -> list:
        """The default combination's includes, and with each receiver and grip any combination uses."""
        combos = [includes(b) for s, b in subs if s == b'OBTS']
        default = _default(subs)
        used = {f for combo in combos for f in combo}
        out = []
        for receiver in self._of('receiver', used) or [None]:
            for grip in self._of('grip', used) or [None]:
                out.append(tuple(_swap(_swap(default, receiver, self._of('receiver', default)), grip,
                                       self._of('grip', default))))
        return sorted(set(out))

    def _magnified(self, fid: int) -> 'tuple | None':
        """(FOV multiplier, image space modifier) of the zoom mod `fid` sets, or None."""
        zoom = self._property((fid,), PROP_ZOOM)
        return (self.zooms[zoom][0], self.zooms[zoom][2]) if zoom in self.zooms else None

    def magnified_scope(self, combo) -> 'int | None':
        """The scope part with a zoom in a combination, or None."""
        return next((f for f in self._of('scope', combo) if self._magnified(f)), None)

    def _scopes(self, subs: list) -> list:
        """The scope parts with a zoom that a WEAP's (`subs`) combinations use."""
        used = {f for s, b in subs if s == b'OBTS' for f in includes(b)}
        return [f for f in self._of('scope', used) if self._magnified(f)]

    def scoped(self, subs: list, combo: tuple, sight_fov: float) -> tuple:
        """`combo` with its scope part swapped for the scope a combination of the WEAP (`subs`) uses whose
        zoom comes nearest FNV's `sight_fov` (degrees), a plain one before night vision or recon; unchanged
        without one. FNV draws its scope in the gun's mesh; FO4's zoom and overlay come from the part.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        scopes = self._scopes(subs)
        if not scopes or sight_fov <= 0:
            return combo
        wanted = FO4_WORLD_FOV / sight_fov
        best = min(scopes, key=lambda f: (abs(math.log(self._magnified(f)[0] / wanted)), self._magnified(f)[1] != 0, f))
        return tuple(_swap(combo, best, self._of('scope', combo)))

    def keywords(self, subs: list, combo: tuple) -> set:
        """The keyword FormIDs a WEAP (`subs`) carries in combination `combo`: its own, as its parts add and remove."""
        kwda = dict(subs).get(b'KWDA', b'')
        out = set(struct.unpack(f'<{len(kwda) // 4}I', kwda))
        for fid in combo:
            for vtype, func, prop, value in properties(dict(self.mods.get(fid, [])).get(b'DATA', bytes(8))):
                if prop == PROP_KEYWORDS:
                    kw = struct.unpack('<I', value)[0]
                    out = out - {kw} if func == FORM_REMOVE else out | {kw}
        return out

    def clip_keywords(self, subs: list, combo: tuple) -> tuple:
        """(keywords a gun's own may replace: the WEAP's (`subs`) in order, then those its parts in `combo` add,
        every keyword it carries): gun_clips' template keywords."""
        kwda = dict(subs).get(b'KWDA', b'')
        own = list(struct.unpack(f'<{len(kwda) // 4}I', kwda))
        carried = self.keywords(subs, combo)
        return own + sorted(carried - set(own)), carried

    def _stance(self, subs: list, combo: tuple) -> 'str | None':
        """'pistol', 'rifle' or None from the record's and parts' keywords."""
        names = {self.names.get(k, '') for k in self.keywords(subs, combo)}
        grip = [n for n in names if n.startswith('AnimsGrip')] or [n for n in names if n.startswith('WeaponType')]
        if any('Pistol' in n for n in grip):
            return 'pistol'
        return 'rifle' if any('Rifle' in n for n in grip) else None

    def _property(self, combo: tuple, wanted: int) -> 'int | None':
        """The first value a part in `combo` sets property `wanted` to (as an int), or None."""
        for fid in combo:
            for _, _, prop, value in properties(dict(self.mods.get(fid, [])).get(b'DATA', bytes(8))):
                if prop == wanted:
                    return struct.unpack('<I', value)[0]
        return None

    def _fits(self, subs: list, combo: tuple, wants: tuple) -> bool:
        """Whether a combination is held, fired and spread as FNV's gun wants (fnv_wants)."""
        stance, automatic, shotgun = wants
        d = dict(subs)
        auto = self._property(combo, PROP_AUTOMATIC)
        auto = bool(auto) if auto is not None else bool(struct.unpack_from('<I', d[b'DNAM'], DNAM_FLAGS)[0]
                                                         & FO4_AUTOMATIC)
        count = self._property(combo, PROP_PROJECTILES)
        count = count if count is not None else (d[b'FNAM'][FNAM_PROJECTILES] if b'FNAM' in d else 1)
        return (auto == automatic and (count > 1) == shotgun
                and (stance is None or self._stance(subs, combo) == stance))

    def choose(self, rec: dict, layout: dict, only: 'str | None' = None) -> 'Choice | None':
        """The candidate for FNV gun `rec` (its layout from gun.fnv_layout); None when none matches. `only` (a
        table entry's FO4 gun) is taken as named, in its default combination; one without a receiver (a launcher)
        has its own model in the receiver's place (Choice.receiver None). A gun with a scope of its own
        (built_in_scope) is matched among the candidates with a scope part first.
        See: docs/fork/fo4_spikes.md#spike-4-gun-clips
        """
        if only:
            return self._best(rec, layout, [only], only)
        scoped = [n for n in self.candidates if self._scopes(self.weapons[n][1])] if built_in_scope(rec) else []
        return (scoped and self._best(rec, layout, scoped)) or self._best(rec, layout, self.candidates)

    def _best(self, rec: dict, layout: dict, names: list, only: 'str | None' = None) -> 'Choice | None':
        """choose() among the candidates `names`: the nearest layout, lower FormID on ties."""
        wants, best = fnv_wants(rec), None
        for name in names:
            fid, subs = self.weapons[name]
            for combo in [tuple(_default(subs))] if only else self._variants(subs):
                receivers = self._of('receiver', combo) or ([None] if only else [])
                if not receivers or not (only or self._fits(subs, combo, wants)):
                    continue
                model = self.model(receivers[0]) if receivers[0] else weapon_model(subs)
                theirs = self.layouts(model)
                score = (_distance(layout, theirs), fid)
                if best is None or score < best[0]:
                    best = (score, Choice(name, combo, receivers[0], model, theirs))
        return best[1] if best else None


def weapon_model(subs: list) -> str:
    """A WEAP's own model."""
    return dict(subs).get(b'MODL', b'\0').rstrip(b'\0').decode('cp1252')


def _default(subs: list) -> list:
    """A WEAP's default combination's includes."""
    return next(includes(b) for s, b in subs if s == b'OBTS' and b[OBTS_DEFAULT])


def _swap(combo, new, olds: list) -> list:
    """`combo` with its mod among `olds` replaced by `new` (unchanged without both)."""
    return [new if new is not None and f in olds else f for f in combo]


def _offsets(layout: dict) -> tuple:
    """(magazine, muzzle) offsets from the trigger (y, z), or None."""
    trigger = layout['trigger'] if layout['trigger'] is not None else np.zeros(3)
    return tuple(None if layout[k] is None else (layout[k] - trigger)[1:] for k in ('mag', 'muzzle'))


def _distance(ours: dict, theirs: dict) -> float:
    """How far apart two layouts are: squared magazine offset gap plus the weighted muzzle one."""
    (mag_a, muzzle_a), (mag_b, muzzle_b) = _offsets(ours), _offsets(theirs)
    out = float(np.sum((mag_a - mag_b) ** 2)) if mag_a is not None and mag_b is not None else 0.0
    if muzzle_a is not None and muzzle_b is not None:
        out += MUZZLE_WEIGHT * float(np.sum((muzzle_a - muzzle_b) ** 2))
    return out


def _edid(subs: list) -> str:
    """The EditorID in a subrecord list."""
    return dict(subs).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')
