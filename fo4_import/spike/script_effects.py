"""FNV spells of script effects as FO4's, made when a converted script names one (a Spell property).

An FNV effect is a script effect when its associated item (MGEF DATA.AssocItem)
is a script. It becomes an FO4 Script-archetype effect carrying that script's
conversion (attach.ObjectScripts.vmad), on the DATA of Fallout4.esm's scripted
area effect (TEMPLATES) with FNV's flags (FLAGS), cast and delivered as the
spell uses it: an ability is a constant effect, any other spell fire and
forget, delivered at the effect's range. The spell keeps FNV's FormID, name,
type, magnitudes, areas and durations. A spell with any other effect, an
effect condition or a script that did not convert is left out, counted.

See: docs/fork/fo4_pipeline.md#disguises
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.consumable_effects import effect_pair
from fo4_import.spike.perks import pack_spell
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Fallout4.esm's scripted area effect and its spell (fire and forget, Touch, area 25): the shape FNV's pulse takes.
TEMPLATES = ('BloodyMessNearbyEffect', 'BloodyMessNearbySpell')
#: FNV MGEF flag bit -> FO4's (xEdit layouts); FNV's others (allowed ranges, use skill) have no FO4 bit.
FLAGS = {0: 0, 1: 1, 2: 2, 7: 9, 8: 10, 9: 11, 10: 12, 12: 14, 24: 26, 27: 27, 28: 28}
#: FNV SPIT flag -> FO4's: area effect ignores LOS, disable absorb/reflect. FO4's Manual Cost Calc (cost 0).
SPELL_FLAGS, MANUAL_COST = {0x10: 0x80000, 0x40: 0x200000}, 0x1
#: FNV effect range -> FO4 delivery: self, touch, aimed.
DELIVERY = {'Self': 0, 'Touch': 1, 'Target': 2}
#: FNV spell type Ability; FO4 casting types.
ABILITY, CONSTANT, FIRE_AND_FORGET = 4, 0, 1
#: FO4 MGEF DATA offsets of the flags and of casting type and delivery (two u32).
FLAGS_AT, CAST_AT = 0x00, 0x50
#: derive_formid site of an effect (key: FNV EditorID, casting type, delivery).
SITE = 'FNV script effect'
#: Export keys of one FNV spell effect.
EFFECT_KEYS = ('EFID', 'Magnitude', 'Area', 'Duration', 'Type', 'ConditionCount')


def _effects(rec: dict) -> list:
    """FNV spell `rec`'s effects: EFFECT_KEYS' text per effect."""
    count = int(rec.get('EffectCount', 0) or 0)
    return [tuple(rec.get(f'Effect[{i}].{k}', '') for k in EFFECT_KEYS) for i in range(count)]


def _number(text: str) -> int:
    """An export integer field; 0 when blank."""
    return int(text or 0)


class ScriptEffects:
    """FO4 spells of FNV's script effects, each written once through a cell builder (`spell`)."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV's spells and script effects."""
        self.builder, self.made, self.made_effects, self.templates = builder, {}, {}, None
        scripts = {r['FormID'] for r in export_records(export_dir, 'SCPT')}
        self.effects = {r['EditorID']: r for r in export_records(export_dir, 'MGEF')
                        if r.get('EditorID') and r.get('DATA.AssocItem') in scripts}
        self.spells = {r['EditorID'].lower(): r for r in export_records(export_dir, 'SPEL') if r.get('EditorID')}

    def spell(self, edid: str) -> 'int | None':
        """The FO4 spell of FNV spell `edid` (any case), written once; None for another name or one left out."""
        key = edid.lower()
        if key in self.spells and key not in self.made:
            self.made[key] = None
            self.made[key] = self._spell(self.spells[key])
        return self.made.get(key)

    def _converts(self, effect: tuple) -> bool:
        """Whether an FNV effect is an unconditioned, converted script effect."""
        rec = self.effects.get(effect[0])
        return bool(rec) and not _number(effect[5]) and bool(self.builder.scripts.name(int(rec['DATA.AssocItem'], 16)))

    def _spell(self, rec: dict) -> 'int | None':
        """Write FNV spell `rec` as FO4's; its FormID, or None (counted) unless every effect _converts."""
        effects = _effects(rec)
        if not effects or not all(self._converts(e) for e in effects):
            self.builder.counts['SPEL left out (not all unconditioned script effects)'] += 1
            return None
        kind = _number(rec.get('SPIT.Type'))
        cast, delivery = CONSTANT if kind == ABILITY else FIRE_AND_FORGET, DELIVERY.get(effects[0][4], 0)
        pairs = b''.join(effect_pair(self._effect(self.effects[e[0]], cast, DELIVERY.get(e[4], 0)),
                                     float(e[1] or 0), _number(e[2]), _number(e[3])) for e in effects)
        fnv_flags = _number(rec.get('SPIT.Flags'))
        flags = MANUAL_COST | sum(fo4 for fnv, fo4 in SPELL_FLAGS.items() if fnv_flags & fnv)
        spit = struct.pack('<IIIfIIffI', 0, flags, kind, 0.0, cast, delivery, 0.0, 0.0, 0)
        fid = self.builder.fnv_id(rec['FormID'])
        template = {b'ETYP': self._templates()[1][b'ETYP'], b'SPIT': spit}
        self.builder.writer.add_record('SPEL', pack_spell(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''),
                                                          template, pairs))
        self.builder.counts['SPEL (script effects)'] += 1
        return fid

    def _effect(self, rec: dict, cast: int, delivery: int) -> int:
        """The FO4 script effect of FNV effect `rec` cast and delivered so, written once on its hashed FormID."""
        key = f'{rec["EditorID"]} {cast} {delivery}'
        if key not in self.made_effects:
            fid = self.made_effects[key] = self.builder.writer.derive_formid(SITE, key)
            data = bytearray(self.effect_data(cast, delivery))
            fnv_flags = _number(rec.get('DATA.Flags'))
            struct.pack_into('<I', data, FLAGS_AT, sum(1 << fo4 for fnv, fo4 in FLAGS.items() if fnv_flags >> fnv & 1))
            vmad = self.builder.scripts.vmad(int(rec['DATA.AssocItem'], 16))
            body = pack_string_subrecord('EDID', f'FNV_{rec["EditorID"]}_{cast}{delivery}') + pack_subrecord('VMAD', vmad)
            body += pack_string_subrecord('FULL', rec.get('FULL', '')) + pack_subrecord('DATA', bytes(data))
            body += pack_subrecord('SNDD', b'') + pack_subrecord('DNAM', b'\0')
            self.builder.writer.add_record('MGEF', pack_fo4_record('MGEF', fid, 0, body))
            self.builder.counts['MGEF (script effects)'] += 1
        return self.made_effects[key]

    def effect_data(self, cast: int, delivery: int) -> bytes:
        """A Script-archetype MGEF DATA (the TEMPLATES effect's) cast and delivered so, with no flags."""
        data = bytearray(self._templates()[0][b'DATA'])
        struct.pack_into('<I', data, FLAGS_AT, 0)
        struct.pack_into('<II', data, CAST_AT, cast, delivery)
        return bytes(data)

    def _templates(self) -> tuple:
        """{tag: data} of Fallout4.esm's TEMPLATES (effect, spell), read once."""
        if self.templates is None:
            found = {}
            for rec, _ in walk(self.builder.fo4, b'MGEF', b'SPEL'):
                subs = dict(subrecords(rec.body))
                found.setdefault(subs.get(b'EDID', b'').rstrip(b'\0').decode(), subs)
            self.templates = tuple(found[name] for name in TEMPLATES)
        return self.templates
