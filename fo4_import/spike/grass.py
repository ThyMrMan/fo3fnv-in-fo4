"""FNV grass as FO4 GRAS records, for the landscape textures that grow them.

Both games scatter grass at runtime from each LTEX's grass list (GNAM) over
the ground painted with it. FO4's GRAS DATA has FNV's layout (density, min
and max slope, units from water and its type, position, height and color
range, wave period, flags; 32 bytes), so the values copy across, density
scaled by DENSITY_SCALE; the model is FNV's grass mesh converted like any
other, then copied to where every
vanilla grass model lives (all 71: directly in Landscape/Grass; Skyrim has the
same contract, asset_convert/nif/grass_profile.py) as FNV_<name>.nif. FNV's
grass has no collision, so the copy needs no Elric pass. A GRAS's FormID is
hashed from FNV's (SITE), so no other record's id moves.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.elric_cache import mesh_bytes, write_new
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.writer import pack_subrecord

#: derive_formid site of a converted grass (key: FNV GRAS FormID).
SITE = 'FNV GRAS'
#: The folder (under Meshes) the grass renderer takes models from, and our models' name prefix.
GRASS_FOLDER, GRASS_PREFIX = 'Landscape\\Grass', 'FNV_'
DATA = struct.Struct('<BBBxHxxIffffBxxx')
#: FNV's density as FO4 draws it: thick at FNV's value, then at half (plays 1 and 2), so a quarter.
DENSITY_SCALE = 0.25


def pack_data(rec: dict) -> bytes:
    """FNV GRAS `rec`'s DATA fields as FO4's 32-byte DATA."""
    ints = [int(rec.get(f'DATA.{k}', 0)) for k in ('Density', 'MinSlope', 'MaxSlope', 'UnitFromWaterAmount',
                                                    'UnitFromWaterType')]
    ints[0] = max(1, round(ints[0] * DENSITY_SCALE))
    floats = [float(rec.get(f'DATA.{k}', 0.0)) for k in ('PositionRange', 'HeightRange', 'ColorRange', 'WavePeriod')]
    return DATA.pack(*ints, *floats, int(rec.get('DATA.Flags', 0)))


def _grass_copy(data_dir: Path, model: str) -> str:
    """Copy converted mesh `model` (under Meshes) to the grass folder; its path there."""
    name = chr(92).join((GRASS_FOLDER, GRASS_PREFIX + model.rsplit(chr(92), 1)[-1]))
    write_new(data_dir / 'Meshes' / name.replace(chr(92), '/'), mesh_bytes(data_dir / 'Meshes' / model.replace(chr(92), '/')))
    return name


class Grasses:
    """FNV's GRAS records, each written as an FO4 GRAS on first use."""

    def __init__(self, export_dir: Path):
        """Read FNV's GRAS records from the export."""
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'GRAS')}
        self.made = {}

    def grass(self, builder, fnv: int) -> 'int | None':
        """The FO4 GRAS for FNV GRAS `fnv`, made once; None when FNV has no such grass or model."""
        if fnv not in self.made:
            rec = self.records.get(fnv)
            self.made[fnv] = self._write(builder, fnv, rec) if rec and rec.get('Model.MODL') else None
        return self.made[fnv]

    def _write(self, builder, fnv: int, rec: dict) -> int:
        """Write FNV grass `rec` (its mesh converted by `builder`); its FormID."""
        fid = builder.writer.derive_formid(SITE, fnv)
        model, bounds = builder.mesh(rec['Model.MODL'])
        model = _grass_copy(builder.data_dir, model)
        subs = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}\0'.encode())
        subs += pack_subrecord('OBND', struct.pack('<6h', *(bounds or (0,) * 6)))
        subs += pack_subrecord('MODL', (model + '\0').encode()) + pack_subrecord('DATA', pack_data(rec))
        builder.writer.add_record('GRAS', pack_fo4_record('GRAS', fid, 0, subs))
        builder.counts['GRAS'] += 1
        return fid
