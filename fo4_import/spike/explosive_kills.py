"""Kills by an explosion the player's weapon set off (a thrown grenade, a placed mine) credited to that weapon.

FNV's kill challenges name the weapon that killed. Fallout 4's OnKill names none, its GetKillerObject crashes
on an explosion kill, and the weapon held is not the grenade thrown. So every explosion copy some FNV weapon's
projectile sets off carries an object effect (EITM, as Fallout4.esm's 24 explosion effects do): its stand-in's
or FNV's own effects plus a script effect (SCRIPT) that hands F3NV_Challenges each actor caught and the form list
of those weapons. A player's kill of that actor within seconds is credited to them.

See: docs/fork/fo4_pipeline.md#challenges-explosives
"""

import struct

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.attack_spells import ENIT_EXPLOSION, pack_explosion_ench
from fo4_import.spike.challenges import counting_quest
from fo4_import.spike.consumable_effects import effect_pair
from fo4_import.spike.script_effects import DELIVERY
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of this module's records (key: the FNV explosion's FormID and what the record is).
SITE = 'FNV explosive kill'
#: The marking script effect's script.
SCRIPT = 'F3NV_ExplosiveHit'
#: FO4 MGEF flag No Death Dispel (xEdit wbDefinitionsFO4): the effect still starts on an actor the blast killed.
NO_DEATH_DISPEL = 1 << 28
#: Seconds the marking effect lasts.
SECONDS = 1


def explosion_weapons(export_dir) -> dict:
    """{FNV explosion FormID: the FNV weapons (masters' too) whose projectile sets it off}."""
    explosions = {int(r['FormID'], 16): int(r.get('DATA.Explosion') or '0', 16)
                  for r in export_records(export_dir, 'PROJ')}
    out = {}
    for rec in export_records(export_dir, 'WEAP'):
        explosion = explosions.get(int(rec.get('DNAM.Projectile') or '0', 16), 0)
        if explosion:
            out.setdefault(explosion, []).append(int(rec['FormID'], 16))
    return out


class ExplosiveKills:
    """The marks of one build's explosion copies; their weapon lists are written last (write)."""

    def __init__(self, builder):
        """FNV's explosions and the weapons setting each off, for `builder`'s plugin."""
        self.builder, self.weapons = builder, explosion_weapons(builder.export_dir)
        self.lists, self.effects, self.enchantments, self.vanilla = {}, {}, {}, None

    def marked(self, subs: list, rec: dict, fnv_pairs) -> 'list | None':
        """Explosion copy `subs` of FNV EXPL `rec` with an object effect marking the actors caught: the stand-in's
        effect, else `fnv_pairs()` (FNV's, converted), plus the mark; None when no weapon sets `rec` off."""
        fnv = int(rec['FormID'], 16)
        if fnv not in self.weapons:
            return None
        own = dict(subs).get(b'EITM', b'')
        key = f'{fnv:08X} {own.hex()}'
        if key not in self.enchantments:
            enit, pairs = self._vanilla(struct.unpack('<I', own)[0]) if own else (ENIT_EXPLOSION, fnv_pairs())
            fid = self.enchantments[key] = self.builder.writer.derive_formid(SITE, key)
            mark = effect_pair(self._effect(fnv, rec['EditorID']), 0.0, 0, SECONDS)
            self.builder.writer.add_record('ENCH', pack_explosion_ench(fid, f'FNV_{rec["EditorID"]}Hit',
                                                                       pairs + mark, enit))
            self.builder.counts['ENCH (explosive kill mark)'] += 1
        subs = [(tag, data) for tag, data in subs if tag != b'EITM']
        at = next(i for i, (tag, _) in enumerate(subs) if tag in (b'MNAM', b'DATA'))
        return subs[:at] + [(b'EITM', struct.pack('<I', self.enchantments[key]))] + subs[at:]

    def _effect(self, fnv: int, edid: str) -> int:
        """The script effect marking actors caught by FNV explosion `fnv` for its weapons' list, written once."""
        if fnv not in self.effects:
            self.lists[fnv] = self.builder.writer.derive_formid(SITE, f'{fnv:08X} weapons')
            vmad = self.builder.scripts.vmad(0, ((SCRIPT, {'Weapons': self.lists[fnv],
                                                           'Hub': counting_quest(self.builder.writer)}, {}),))
            self.effects[fnv] = self.builder.scripts.effects.vmad_effect(f'FNV_{edid}Hit', vmad, DELIVERY['Touch'],
                                                                         flags=NO_DEATH_DISPEL)
        return self.effects[fnv]

    def _vanilla(self, fid: int) -> tuple:
        """(ENIT, its other subrecords packed) of Fallout4.esm enchantment `fid`, past its EditorID and bounds."""
        if self.vanilla is None:
            self.vanilla = {rec.form_id: list(subrecords(rec.body)) for rec, _ in walk(self.builder.fo4, b'ENCH')}
        subs = self.vanilla.get(fid, [])
        enit = dict(subs).get(b'ENIT', ENIT_EXPLOSION)
        rest = b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs
                        if tag not in (b'EDID', b'OBND', b'FULL', b'ENIT'))
        return enit, rest

    def write(self, made) -> None:
        """Write each marked explosion's weapon list: the FO4 forms `made(fnv)` gives its FNV weapons (None: none)."""
        if self.lists and SCRIPT not in self.builder.scripts.used:
            self.builder.scripts.used.append(SCRIPT)
        for fnv, fid in sorted(self.lists.items()):
            forms = sorted({made(w) for w in self.weapons[fnv]} - {None})
            self.builder.writer.add_record('FLST', R.pack_flst(fid, f'FNV_Explosion{fnv:08X}Weapons', forms))
