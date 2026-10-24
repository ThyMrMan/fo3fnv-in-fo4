"""FNV consumables (ALCH) and ammunition (AMMO) as FO4 records, for the cell spike.

A consumable keeps its name, model, value, weight and kind (food, medicine),
the effects FO4 has (consumable_effects) and its Hardcore needs as Survival's
(survival_needs). Its category (food, drink, stimpak,
chem, alcohol, magazine), from FNV's equipment type and consume sound, gives
it a vanilla item's Pip-Boy preview, sounds and keyword (CATEGORIES). Ammunition keeps its name, model,
value, weight and short name on FO4's 5.56 round (its projectile and casing). FormIDs are
hashed from FNV's (SITES), so no other record's id moves.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.base.install import source_esm
from fo4_import.spike import survival_needs as S
from fo4_import.spike.consumable_effects import NEEDS, WANTED, Effects, fnv_effects
from fo4_import.spike.records import pack_keywords
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

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
#: derive_formid sites (key: FNV FormID).
SITES = {'ALCH': 'FNV ALCH', 'AMMO': 'FNV AMMO'}


class Consumables:
    """FO4 consumables and ammunition, each written once through a cell builder."""

    def __init__(self, builder, helper_index: int):
        """Index Fallout4.esm's records the conversions draw on."""
        self.builder = builder
        wanted = {*WANTED, *S.WANTED, AMMO_TEMPLATE, *(t for t, _ in CATEGORIES.values()),
                  *(k for _, k in CATEGORIES.values() if k)}
        self.vanilla, self.fnv = {}, _fnv_consumables()
        for rec, _ in walk(builder.fo4, b'MGEF', b'ALCH', b'AMMO', b'KYWD', b'BOOK', b'GLOB', b'QUST'):
            subs = dict(subrecords(rec.body))
            edid = subs.get(b'EDID', b'').rstrip(b'\0').decode()
            if edid in wanted:
                self.vanilla[edid] = (rec.form_id, subs)
        needs = S.SurvivalNeeds(builder, self.vanilla, S.fnv_per_hour(builder.export_dir))
        self.effects = Effects(builder, helper_index, self.vanilla, needs)

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
        body += pack_keywords([self.vanilla[k][0] for k in (keyword, survival_keyword(rec)) if k])
        body += pack_subrecord('MODL', (model + '\0').encode()) + _copied(template, SOUNDS)
        sound = template[b'ENIT'][16:20] if b'ENIT' in template else bytes(4)
        body += pack_subrecord('DATA', struct.pack('<f', float(rec.get('DATA.Weight', 0.0))))
        body += pack_subrecord('ENIT', struct.pack('<iIIf', int(rec.get('ENIT.Value', 0)), flags, 0, 0.0) + sound)
        body += self.effects.subs(rec)
        return self._write('ALCH', fnv, body)

    def ammo(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 ammunition for FNV AMMO `rec` (FormID `fnv`) on FO4's 5.56 round, with FNV's short name (ONAM,
        else its name); None without a model."""
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
        short = (rec.get('ONAM') or rec.get('FULL', '')) + '\0'
        body += pack_subrecord('DNAM', template[b'DNAM']) + pack_subrecord('ONAM', short.encode())
        return self._write('AMMO', fnv, body)

    def _write(self, sig: str, fnv: int, body: bytes) -> int:
        """Add a `sig` record with `body` on its hashed FormID; the FormID."""
        fid = self.builder.writer.derive_formid(SITES[sig], fnv)
        self.builder.writer.add_record(sig, pack_fo4_record(sig, fid, 0, body))
        self.builder.counts[sig] += 1
        return fid


def survival_keyword(rec: dict) -> 'str | None':
    """S.IGNORE_AS_FOOD when consumable `rec` has FNV need effects, else None."""
    return S.IGNORE_AS_FOOD if any(e[0] in NEEDS for e in fnv_effects(rec)) else None


def _copied(template: dict, tags: tuple) -> bytes:
    """The template's subrecords `tags` it has, in that order."""
    return b''.join(pack_subrecord(t.decode(), template[t]) for t in tags if t in template)


def _fnv_consumables() -> dict:
    """{FNV ALCH FormID: (ETYP, consume sound EditorID)}: fields the export drops, read from FalloutNV.esm."""
    raw = source_esm()
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
