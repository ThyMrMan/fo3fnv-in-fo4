"""FNV activators as FO4 ACTI records, for the cell spike.

An activator keeps its name, model and converted script (VMAD; properties
filled from same-named Fallout4.esm records and the spike's converted
messages). One without a model is a trigger volume: its references keep
FNV's primitive. An activator FNV drinks water from (sink, toilet) takes
vanilla's drinkFromFountainScript, irradiated when FNV's water spell damages
radiation. The export lacks ACTI WNAM and WATR XNAM; they are read from
FalloutNV.esm.

See: docs/fork/fo4_spikes.md#spike-2-activators
"""

import struct
from pathlib import Path

from fo4_import.base.install import FALLOUTNV_ESM
from fo4_import.base.vmad import object_scripts, read_entry
from fo4_import.spike import records as R
from fo4_import.spike.script import declared_properties, fill, fo4_forms
from script_convert.constants import papyrus_script_name
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.base.text_reader import parse_export_file

SCRIPT_PREFIX = 'FALLOUTNV_'
#: Vanilla sink whose drinkFromFountainScript (sounds, drinking idle) drinkable FNV activators take.
DRINK_TEMPLATE, DRINK_SCRIPT = 'PlayerHouse_Ruin_KitchenSink01Activator', 'drinkfromfountainscript'
#: FO4 drink spells for clean and irradiated water, and the FNV effect that makes water irradiated.
CLEAN_WATER, IRRADIATED_WATER, RADIATION_EFFECT = 'WaterFountainCleanDrinking', 'WaterRadiationDrinking', \
    'DamageRadiationLevel'
#: MESG DNAM Message Box, the one flag FNV and FO4 share (FNV bit 1 is Auto Display, FO4's Delay Initial Display).
MESSAGE_BOX = 0x1
#: The activation prompt of a drinkable activator.
DRINK_PROMPT = 'Drink'


def fnv_links(raw: bytes, sig: bytes, tag: bytes) -> dict:
    """{FormID: FormID} of FNV records of type `sig` with a FormID subrecord `tag`."""
    return {r.form_id: struct.unpack('<I', v)[0] for r, _ in walk(raw, sig) for v in [first_sub(r.body, tag)] if v}


def _records(export_dir: Path, sig: str, key: str = 'FormID') -> dict:
    """{FormID (int) or EditorID: record} of an export file."""
    return {int(r[key], 16) if key == 'FormID' else r.get(key): r for r in parse_export_file(str(export_dir / f'{sig}.txt'))}


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
    """FO4 ACTI and MESG records for FNV activators, written through a cell builder."""

    def __init__(self, builder, export_dir: Path, scripts_dir: 'Path | None'):
        """Activators made through `builder`; scripts from the converted `scripts_dir` (None: none attached)."""
        fnv = FALLOUTNV_ESM.read_bytes()
        self.builder, self.scripts_dir, self.used = builder, scripts_dir, []
        self.water, self.water_spell = fnv_links(fnv, b'ACTI', b'WNAM'), fnv_links(fnv, b'WATR', b'XNAM')
        self.spells, self.messages = _records(export_dir, 'SPEL'), _records(export_dir, 'MESG', 'EditorID')
        self.script_names = {fid: r['EditorID'] for fid, r in _records(export_dir, 'SCPT').items()}
        self.drink = drink_template(builder.fo4)
        self.fo4_spells = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                           for r, _ in walk(builder.fo4, b'SPEL')}
        self.forms, self.made_messages = fo4_forms(), {}

    def record(self, fid: int, rec: dict, model: str, bounds: tuple) -> bytes:
        """The FO4 ACTI of FNV activator `rec` with converted `model` ('' for a trigger) and `bounds`."""
        fnv_fid, vmad, prompt = int(rec['FormID'], 16), b'', ''
        if fnv_fid in self.water:
            vmad, prompt = self._drink(self.water[fnv_fid]), DRINK_PROMPT
        elif 'SCRI' in rec:
            vmad = self._script(int(rec['SCRI'], 16))
        return R.pack_acti(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), model, bounds, vmad, prompt)

    def _drink(self, water: int) -> bytes:
        """The drinking script VMAD for FNV water type `water`."""
        spell = self.spells.get(self.water_spell.get(water), {})
        irradiated = RADIATION_EFFECT in [v for k, v in spell.items() if k.endswith('.EFID')]
        script, objects, values = self.drink
        objects = {**objects, 'spellOnDrink': self.fo4_spells[IRRADIATED_WATER if irradiated else CLEAN_WATER]}
        return object_scripts([(script, objects, values)])

    def _script(self, scpt: int) -> bytes:
        """The VMAD attaching FNV script `scpt`'s conversion, filled; b'' when it is not converted."""
        name = papyrus_script_name(self.script_names.get(scpt, ''), SCRIPT_PREFIX)
        path = self.scripts_dir / f'{name}.psc' if self.scripts_dir else None
        if path is None or not path.exists():
            self.builder.counts['activator script not attached'] += 1
            return b''
        declared = declared_properties(path.read_text(encoding='utf-8'))
        messages = {prop: self.message(prop) for kind, prop in declared if kind == 'Message' and prop in self.messages}
        self.used.append(name)
        return object_scripts([(name, fill(declared, {**self.forms, 'Message': messages}, None), {})])

    def message(self, edid: str) -> int:
        """The FO4 MESG for FNV message `edid`, made once."""
        if edid not in self.made_messages:
            rec, fid = self.messages[edid], self.builder.new_id()
            buttons, i = [], 0
            while f'Button[{i}].Text' in rec:
                buttons.append(rec[f'Button[{i}].Text'])
                i += 1
            self.builder.writer.add_record('MESG', R.pack_mesg(
                fid, f'FNV_{edid}', rec.get('FULL', ''), rec.get('DESC', ''), int(rec.get('DNAM', 0)) & MESSAGE_BOX,
                buttons))
            self.builder.counts['MESG'] += 1
            self.made_messages[edid] = fid
        return self.made_messages[edid]
