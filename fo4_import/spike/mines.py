"""FNV placed mines (PGRE) as Fallout 4's: the projectile of the FO4 weapon the mine's weapon becomes.

FNV places an armed mine as a PGRE reference on a projectile (PROJ); FO4
does the same with its own mine projectiles (Fallout4.esm: 395 PGREs,
FragMineProjectile 340). The FNV weapon throwing that projectile (WEAP
DNAM) converts through the replacement table (items.item), and the FO4
weapon names its projectile in FNAM; a reference keeps FNV's position.
The weapon is Fallout4.esm's own (an `item` entry) or the build's copy of
one (`stats`, `fnv`: Equipment.fired, its FNAM as written). A projectile no
weapon throws, or one whose weapon is not converted, is left out and counted.

See: docs/fork/fo4_pipeline.md#placed-mines
"""

import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.projectiles import FNAM_OVERRIDE
from tes5_import.base.tes5_reader import first_sub, walk


class Mines:
    """FO4 mine projectiles for FNV mine projectiles, through a cell builder's items."""

    def __init__(self, builder, export_dir: Path):
        """Index the FNV weapons by projectile and Fallout4.esm's weapons' projectiles."""
        self.builder = builder
        self.weapons = {int(r['DNAM.Projectile'], 16): int(r['FormID'], 16)
                        for r in export_records(export_dir, 'WEAP') if r.get('DNAM.Projectile')}
        self.fired = {r.form_id: struct.unpack_from('<I', fnam, FNAM_OVERRIDE)[0]
                      for r, _ in walk(builder.fo4, b'WEAP')
                      if (fnam := first_sub(r.body, b'FNAM')) and len(fnam) >= FNAM_OVERRIDE + 4}

    def projectile(self, fnv_projectile: int) -> 'int | None':
        """The FO4 projectile placed for FNV projectile `fnv_projectile`, or None (counted)."""
        weapon = self.weapons.get(fnv_projectile)
        made = self.builder.items.item(weapon) if weapon else None
        found = (self.fired.get(made) or self.builder.equipment.fired.get(made)) if made else None
        if not found:
            reason = 'no weapon throws it' if not weapon else 'its weapon is not converted'
            self.builder.counts[f'placed mine left out: {reason}'] += 1
        return found or None
