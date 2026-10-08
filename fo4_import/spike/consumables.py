"""FNV consumables (ALCH) and ammunition (AMMO) as FO4 records, for the cell spike.

A consumable keeps its name, model, value, weight and kind (food, medicine)
and the effects FO4 has: FNV's effect is FO4's own where EFFECTS names one,
and a skill boost (IncreaseSkill*) a copy of Rad-X's timed boost on the FNV
skill's actor value (the helper plugin's). An effect a perk gates on (HasPerk)
counts as without the perk, as no FNV perk is converted; the rest (Hardcore
needs, scripted effects) are drift. Its category (food, drink, stimpak,
chem, alcohol, magazine), from FNV's equipment type and consume sound, gives
it a vanilla item's Pip-Boy preview, sounds and keyword (CATEGORIES). Ammunition keeps its name, model,
value and weight on FO4's 5.56 round (its projectile and casing). FormIDs are
hashed from FNV's (SITES), so no other record's id moves.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.base.install import FALLOUTNV_ESM
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike import conditions as C
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV magic effect EditorID -> Fallout4.esm's.
EFFECTS = {'RestoreHealth': 'RestoreHealthFood', 'DamageRadiationLevel': 'DamageRadiationChem',
           'NukaColaAddCap': 'NukaColaBottlecapAdder'}
SKILL_EFFECT_PREFIX = 'IncreaseSkill'
#: Fallout4.esm's timed actor-value boost a skill effect copies, and the DATA offset of its actor value.
BOOST_TEMPLATE, BOOST_AV_AT = 'FortifyResistRadsRadX', 0x44
#: Per category: the Fallout4.esm record its preview, sounds and consume sound come from, and its keyword.
CATEGORIES = {'food': ('Mutfruit', 'ObjectTypeFood'), 'drink': ('NukaCola', 'ObjectTypeDrink'),
              'stimpak': ('Stimpak', 'ObjectTypeStimpak'), 'chem': ('Mentats', 'ObjectTypeChem'),
              'alcohol': ('BeerGwinnettStout_Cold', 'ObjectTypeAlcohol'), 'paper': ('PerkMagTotalHack01', None)}
#: FNV ETYP equipment types of consumables.
ETYP_CHEM, ETYP_STIMPAK, ETYP_ALCOHOL = 10, 11, 13
#: Template subrecords a consumable takes, in vanilla's order around its own.
PREVIEW, SOUNDS = (b'PTRN',), (b'YNAM', b'ZNAM', b'CUSD')
AMMO_TEMPLATE = 'Ammo556'
#: FNV ALCH ENIT flags -> FO4's: no auto-calc and food keep their bit, medicine moves.
FNV_MEDICINE, FO4_MEDICINE = 0x4, 0x10000
#: FNV's HasPerk condition function.
HAS_PERK = 'HasPerk'
#: derive_formid sites (key: FNV FormID, or the skill's name for its boost).
SITES = {'ALCH': 'FNV ALCH', 'AMMO': 'FNV AMMO', 'MGEF': 'FNV skill boost'}


def _effects(rec: dict) -> list:
    """[(FNV effect EditorID, magnitude, area, duration, actor value index)] of an FNV consumable without perks."""
    out = []
    for i in range(int(rec.get('EffectCount', 0))):
        key = f'Effect[{i}]'
        conds = [C.parse(rec[f'{key}.Condition[{j}].Raw']) for j in range(int(rec.get(f'{key}.ConditionCount', 0)))]
        if any(c['func'] == HAS_PERK and not C.compare(c, 0.0) for c in conds):
            continue
        out.append((rec[f'{key}.EFID'], float(rec[f'{key}.Magnitude']), int(rec[f'{key}.Area']),
                    int(rec[f'{key}.Duration']), int(rec[f'{key}.ActorValue'])))
    return out


class Consumables:
    """FO4 consumables, ammunition and skill boosts, each written once through a cell builder."""

    def __init__(self, builder, helper_index: int):
        """Index Fallout4.esm's records the conversions draw on."""
        self.builder, self.helper_index, self.boosts = builder, helper_index, {}
        wanted = {*EFFECTS.values(), BOOST_TEMPLATE, AMMO_TEMPLATE, *(t for t, _ in CATEGORIES.values()),
                  *(k for _, k in CATEGORIES.values() if k)}
        self.vanilla, self.fnv = {}, _fnv_consumables()
        for rec, _ in walk(builder.fo4, b'MGEF', b'ALCH', b'AMMO', b'KYWD', b'BOOK'):
            subs = dict(subrecords(rec.body))
            edid = subs.get(b'EDID', b'').rstrip(b'\0').decode()
            if edid in wanted:
                self.vanilla[edid] = (rec.form_id, subs)

    def _effect(self, edid: str, av: int) -> 'int | None':
        """The FO4 magic effect for FNV effect `edid` (on FNV actor value index `av`); None when FO4 has none."""
        if edid in EFFECTS:
            return self.vanilla[EFFECTS[edid]][0]
        if not edid.startswith(SKILL_EFFECT_PREFIX) or not 0 <= av < len(C.FNV_AV_NAMES):
            return None
        skill = C.FNV_AV_NAMES[av].replace(' ', '')
        if skill not in self.boosts:
            self.boosts[skill] = self._boost(skill)
        return self.boosts[skill]

    def _boost(self, skill: str) -> int:
        """A copy of Rad-X's timed boost raising FNV skill `skill`; its FormID."""
        fid = self.builder.writer.derive_formid(SITES['MGEF'], skill)
        subs = dict(self.vanilla[BOOST_TEMPLATE][1])
        data = bytearray(subs[b'DATA'])
        data[BOOST_AV_AT:BOOST_AV_AT + 4] = struct.pack('<I', actor_value_form(skill, self.helper_index))
        body = pack_subrecord('EDID', f'FNV_Fortify{skill}\0'.encode()) + pack_subrecord('FULL', f'{skill}\0'.encode())
        body += pack_subrecord('DATA', bytes(data)) + pack_subrecord('DNAM', subs[b'DNAM'])
        self.builder.writer.add_record('MGEF', pack_fo4_record('MGEF', fid, 0, body))
        self.builder.counts['MGEF (skill boost)'] += 1
        return fid

    def alch(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 consumable for FNV ALCH `rec` (FormID `fnv`); None without a model."""
        if 'Model.MODL' not in rec:
            return None
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        fnv_flags = int(rec.get('ENIT.Flags', 0))
        flags = (fnv_flags & 0x3) | (FO4_MEDICINE if fnv_flags & FNV_MEDICINE else 0)
        name, keyword = CATEGORIES[_category(*self.fnv.get(fnv, (None, '')))]
        template = self.vanilla[name][1]
        body = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}\0'.encode()) + _obnd(bounds, rec)
        body += _copied(template, PREVIEW) + pack_subrecord('FULL', (rec.get('FULL', '') + '\0').encode())
        if keyword:
            body += pack_subrecord('KSIZ', struct.pack('<I', 1))
            body += pack_subrecord('KWDA', struct.pack('<I', self.vanilla[keyword][0]))
        body += pack_subrecord('MODL', (model + '\0').encode()) + _copied(template, SOUNDS)
        sound = template[b'ENIT'][16:20] if b'ENIT' in template else bytes(4)
        body += pack_subrecord('DATA', struct.pack('<f', float(rec.get('DATA.Weight', 0.0))))
        body += pack_subrecord('ENIT', struct.pack('<iIIf', int(rec.get('ENIT.Value', 0)), flags, 0, 0.0) + sound)
        body += self._effect_subs(rec)
        return self._write('ALCH', fnv, body)

    def _effect_subs(self, rec: dict) -> bytes:
        """EFID/EFIT pairs of the FNV consumable's effects FO4 has."""
        out = b''
        for edid, magnitude, area, duration, av in _effects(rec):
            effect = self._effect(edid, av)
            if effect is None:
                self.builder.counts[f'effect dropped ({edid})'] += 1
                continue
            out += pack_subrecord('EFID', struct.pack('<I', effect))
            out += pack_subrecord('EFIT', struct.pack('<fII', magnitude, area, duration))
        return out

    def ammo(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 ammunition for FNV AMMO `rec` (FormID `fnv`) on FO4's 5.56 round; None without a model."""
        if 'Model.MODL' not in rec:
            return None
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        template = self.vanilla[AMMO_TEMPLATE][1]
        name = (rec.get('FULL', '') + '\0').encode()
        body = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}\0'.encode()) + _obnd(bounds, rec)
        body += pack_subrecord('FULL', name) + pack_subrecord('MODL', (model + '\0').encode())
        body += b''.join(pack_subrecord(t.decode(), template[t]) for t in (b'YNAM', b'ZNAM', b'KSIZ', b'KWDA'))
        body += pack_subrecord('DATA', struct.pack('<If', int(rec.get('DATA.Value', 0)),
                                                   float(rec.get('DATA.Weight', 0.0))))
        body += pack_subrecord('DNAM', template[b'DNAM']) + pack_subrecord('ONAM', name)
        return self._write('AMMO', fnv, body)

    def _write(self, sig: str, fnv: int, body: bytes) -> int:
        """Add a `sig` record with `body` on its hashed FormID; the FormID."""
        fid = self.builder.writer.derive_formid(SITES[sig], fnv)
        self.builder.writer.add_record(sig, pack_fo4_record(sig, fid, 0, body))
        self.builder.counts[sig] += 1
        return fid


def _copied(template: dict, tags: tuple) -> bytes:
    """The template's subrecords `tags` it has, in that order."""
    return b''.join(pack_subrecord(t.decode(), template[t]) for t in tags if t in template)


def _fnv_consumables() -> dict:
    """{FNV ALCH FormID: (ETYP, consume sound EditorID)}: fields the export drops, read from FalloutNV.esm."""
    raw = FALLOUTNV_ESM.read_bytes()
    sounds = {rec.form_id: (first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode() for rec, _ in walk(raw, b'SOUN')}
    out = {}
    for rec, _ in walk(raw, b'ALCH'):
        subs = dict(subrecords(rec.body))
        etyp = struct.unpack('<i', subs[b'ETYP'])[0] if b'ETYP' in subs else None
        enit = subs.get(b'ENIT', b'')
        out[rec.form_id] = (etyp, sounds.get(struct.unpack_from('<I', enit, 16)[0], '') if len(enit) >= 20 else '')
    return out


def _category(etyp: 'int | None', sound: str) -> str:
    """A consumable's CATEGORIES key from FNV's equipment type and consume sound (NPCHumanDrinkingSoda...)."""
    if 'Comic' in sound:
        return 'paper'
    if 'Drinking' in sound:
        return 'alcohol' if etyp == ETYP_ALCOHOL else 'drink'
    if 'Stimpak' in sound or etyp == ETYP_STIMPAK:
        return 'stimpak'
    if etyp == ETYP_ALCOHOL:
        return 'alcohol'
    return 'chem' if etyp == ETYP_CHEM or 'Using' in sound or 'Mentats' in sound else 'food'


def _obnd(bounds, rec: dict) -> bytes:
    """OBND from the converted mesh, else the FNV record's."""
    box = bounds or tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))
    return pack_subrecord('OBND', struct.pack('<6h', *box))
