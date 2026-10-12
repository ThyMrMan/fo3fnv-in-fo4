"""FNV activators as FO4 ACTI records, for the cell spike.

An activator keeps its name, model and converted script (attach.py). One
without a model is a trigger volume: its references keep FNV's primitive. An
activator FNV drinks water from (sink, toilet) takes vanilla's
drinkFromFountainScript, irradiated when FNV's water spell damages
radiation. The export lacks ACTI WNAM and WATR XNAM; they are read from
FalloutNV.esm.

See: docs/fork/fo4_spikes.md#spike-2-activators
"""

import struct
from pathlib import Path

from fo4_import.base.install import fnv_esm
from fo4_import.base.vmad import object_scripts, read_entry
from fo4_import.spike import records as R
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk

#: Vanilla sink whose drinkFromFountainScript (sounds, drinking idle) drinkable FNV activators take.
DRINK_TEMPLATE, DRINK_SCRIPT = 'PlayerHouse_Ruin_KitchenSink01Activator', 'drinkfromfountainscript'
#: FO4 drink spells for clean and irradiated water, and the FNV effect that makes water irradiated.
CLEAN_WATER, IRRADIATED_WATER, RADIATION_EFFECT = 'WaterFountainCleanDrinking', 'WaterRadiationDrinking', \
    'DamageRadiationLevel'
#: The activation prompt of a drinkable activator.
DRINK_PROMPT = 'Drink'


def fnv_links(raw: bytes, sig: bytes, tag: bytes) -> dict:
    """{FormID: FormID} of FNV records of type `sig` with a FormID subrecord `tag`."""
    return {r.form_id: struct.unpack('<I', v)[0] for r, _ in walk(raw, sig) for v in [first_sub(r.body, tag)] if v}


def drink_template(fo4: bytes) -> tuple:
    """(script, {property: FormID}, {property: value}) of DRINK_TEMPLATE's drinking script."""
    for r, _ in walk(fo4, b'ACTI'):
        if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == DRINK_TEMPLATE:
            vmad = first_sub(r.body, b'VMAD')
            pos = 6
            for _ in range(struct.unpack_from('<H', vmad, 4)[0]):
                entry, pos = read_entry(vmad, pos)
                if entry[0].lower() == DRINK_SCRIPT:
                    return entry
    raise SystemExit(f'no {DRINK_TEMPLATE} in Fallout4.esm')


class Activators:
    """FO4 ACTI records for FNV activators, written through a cell builder (whose `scripts` attach theirs)."""

    def __init__(self, builder, export_dir: Path):
        """Activators made through `builder`."""
        fnv = fnv_esm()
        self.builder, self.drink = builder, drink_template(builder.fo4)
        self.water, self.water_spell = fnv_links(fnv, b'ACTI', b'WNAM'), fnv_links(fnv, b'WATR', b'XNAM')
        self.spells = {int(r['FormID'], 16): r for r in export_records(export_dir, 'SPEL')}
        self.fo4_spells = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                           for r, _ in walk(builder.fo4, b'SPEL')}

    def record(self, fid: int, rec: dict, model: str, bounds: tuple) -> bytes:
        """The FO4 ACTI of FNV activator `rec` with converted `model` ('' for a trigger) and `bounds`."""
        fnv_fid, vmad, prompt = int(rec['FormID'], 16), b'', ''
        if fnv_fid in self.water:
            vmad, prompt = self._drink(self.water[fnv_fid]), DRINK_PROMPT
        elif 'SCRI' in rec:
            vmad = self.builder.scripts.vmad(int(rec['SCRI'], 16))
        return R.pack_acti(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds, vmad, prompt,
                           self.builder.sounds.field(rec, 'SNAM'))

    def _drink(self, water: int) -> bytes:
        """The drinking script VMAD for FNV water type `water`."""
        spell = self.spells.get(self.water_spell.get(water), {})
        irradiated = RADIATION_EFFECT in [v for k, v in spell.items() if k.endswith('.EFID')]
        script, objects, values = self.drink
        objects = {**objects, 'spellOnDrink': self.fo4_spells[IRRADIATED_WATER if irradiated else CLEAN_WATER]}
        return object_scripts([(script, objects, values)])
