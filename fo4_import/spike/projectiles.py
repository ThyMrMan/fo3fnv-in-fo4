"""Which Fallout 4 projectile an FNV gun or round flies (data/projectiles.json).

FNV names the projectile on the gun (WEAP DNAM Projectile); a round
overrides it for its subtypes (AMMO DAT2 Projectile: slugs, coin shot, HE
missiles). Fallout 4 names it on the round (AMMO DNAM); a gun overrides it
in its FNAM (Override Projectile, as 47 of Fallout4.esm's guns do) and a
mod through OverrideProjectile. The table names the Fallout4.esm projectile
each FNV one becomes. A converted gun carries its FNV projectile's as its
FNAM override, beside FNV's projectile count (fnam); a round's mod carries
its override's (override). A round itself flies its override's, else that
of the lowest-FormID FNV gun FNV does not mark embedded loading it first
(ammo). An FNV projectile the table leaves out is counted.

See: docs/fork/fo4_pipeline.md#nv-ammo
"""

import json
import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'projectiles.json'
#: FNV WEAP DNAM Flags1 Embedded Weapon (xEdit's FNV WEAP).
FNV_EMBEDDED = 0x20
#: FO4 WEAP FNAM: the projectile count byte, then the Override Projectile FormID (xEdit's FO4 WEAP).
FNAM_COUNT, FNAM_OVERRIDE = 28, 29


def load_table(path: Path = TABLE) -> dict:
    """{FNV projectile EditorID: Fallout4.esm projectile EditorID}."""
    return json.loads(path.read_text(encoding='utf-8'))['projectiles']


def first_ammo(rec: dict, lists: dict) -> int:
    """An export WEAP's ammo: its NAM0, or that list's first entry; 0 for none."""
    source = int(rec.get('NAM0', '0'), 16)
    entries = lists.get(source)
    return int(entries['LNAM[0]'], 16) if entries and 'LNAM[0]' in entries else source


class Projectiles:
    """The table resolved against one build's export and Fallout4.esm."""

    def __init__(self, builder, table: 'dict | None' = None):
        """Index FO4's projectiles, FNV's, each round's override and its first gun's projectile."""
        self.builder, table = builder, load_table() if table is None else table
        fo4 = {(first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252'): rec.form_id
               for rec, _ in walk(builder.fo4, b'PROJ')}
        missing = sorted(set(table.values()) - set(fo4))
        if missing:
            raise ValueError(f'projectiles.json names projectiles Fallout4.esm lacks: {missing}')
        export = builder.export_dir
        self.names = {int(r['FormID'], 16): r['EditorID'] for r in export_records(export, 'PROJ')}
        self.mapped = {fid: fo4[table[edid]] for fid, edid in self.names.items() if edid in table}
        self.overrides = {int(r['FormID'], 16): int(r.get('DAT2.Projectile', '0'), 16)
                          for r in export_records(export, 'AMMO')}
        lists = {int(r['FormID'], 16): r for r in export_records(export, 'FLST')}
        self.first, self.unmapped = {}, set()
        for rec in sorted(export_records(export, 'WEAP'), key=lambda r: int(r['FormID'], 16)):
            ammo, projectile = first_ammo(rec, lists), int(rec.get('DNAM.Projectile', '0'), 16)
            if ammo and projectile and not int(rec.get('DNAM.Flags1', 0)) & FNV_EMBEDDED:
                self.first.setdefault(ammo, projectile)

    def of(self, fnv: int) -> 'int | None':
        """The FO4 projectile for FNV projectile `fnv` (None for none); one left out is counted once."""
        if not fnv:
            return None
        if fnv not in self.mapped and fnv not in self.unmapped:
            self.unmapped.add(fnv)
            self.builder.counts[f'projectile not mapped ({self.names.get(fnv, f"{fnv:08X}")})'] += 1
        return self.mapped.get(fnv)

    def gun(self, rec: dict) -> 'int | None':
        """The FO4 projectile FNV gun `rec` fires."""
        return self.of(int(rec.get('DNAM.Projectile', '0'), 16))

    def override(self, ammo: int) -> 'int | None':
        """The FO4 projectile FNV round `ammo` overrides its gun's with; None without one."""
        return self.of(self.overrides.get(ammo, 0))

    def ammo(self, ammo: int) -> 'int | None':
        """The FO4 projectile FNV round `ammo` flies: its override's, else its first gun's."""
        return self.override(ammo) or self.of(self.first.get(ammo, 0))

    def fnam(self, fnam: bytes, rec: dict) -> bytes:
        """A gun copy's FNAM with FNV gun `rec`'s projectile count and its projectile as the override."""
        out = bytearray(fnam)
        out[FNAM_COUNT] = min(max(int(rec.get('DNAM.ProjectileCount', 1)), 1), 255)
        projectile = self.gun(rec)
        if projectile is not None:
            struct.pack_into('<I', out, FNAM_OVERRIDE, projectile)
        return bytes(out)
