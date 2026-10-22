"""Hotkey aid items: a weightless, worthless ALCH for the Favorites wheel whose Script-archetype effect (fire and
forget, on self) runs a script, which gives the item back and does the hotkey's work.

Used by the Ammo Type hotkey (ammo_switch) and the Repair hotkey (condition).

See: docs/fork/fo4_pipeline.md#ammo-switch
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.consumable_effects import effect_pair
from fo4_import.spike.script_effects import FIRE_AND_FORGET
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: The vanilla ammo whose model a hotkey item takes; Self delivery; FO4 ENIT flag No Auto-Calc.
MODEL_FROM, SELF, NO_AUTO_CALC = 'Ammo556', 0, 0x1


def hotkey_effect(builder, fid: int, edid: str, name: str, vmad: bytes) -> None:
    """A hotkey's Script-archetype effect `edid` named `name`: fire and forget on self, carrying `vmad`."""
    body = pack_string_subrecord('EDID', edid) + pack_subrecord('VMAD', vmad) + pack_string_subrecord('FULL', name)
    body += pack_subrecord('DATA', builder.scripts.effects.effect_data(FIRE_AND_FORGET, SELF))
    body += pack_subrecord('SNDD', b'') + pack_subrecord('DNAM', b'\0')
    builder.writer.add_record('MGEF', pack_fo4_record('MGEF', fid, 0, body))


def hotkey_item(builder, fid: int, edid: str, name: str, effect: int) -> None:
    """A hotkey aid item `edid` named `name` running `effect`: no weight or value, on vanilla MODEL_FROM's model."""
    body = pack_string_subrecord('EDID', edid) + pack_subrecord('OBND', bytes(12))
    body += pack_string_subrecord('FULL', name) + pack_subrecord('MODL', model(builder.fo4))
    body += pack_subrecord('DATA', struct.pack('<f', 0.0))
    body += pack_subrecord('ENIT', struct.pack('<iIIfI', 0, NO_AUTO_CALC, 0, 0.0, 0))
    body += effect_pair(effect, 0.0, 0, 0)
    builder.writer.add_record('ALCH', pack_fo4_record('ALCH', fid, 0, body))


def model(fo4: bytes) -> bytes:
    """Vanilla MODEL_FROM's MODL."""
    for rec, _ in walk(fo4, b'AMMO'):
        subs = dict(subrecords(rec.body))
        if subs.get(b'EDID', b'').rstrip(b'\0').decode() == MODEL_FROM:
            return subs[b'MODL']
    raise KeyError(MODEL_FROM)
