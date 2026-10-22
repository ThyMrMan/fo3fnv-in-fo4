"""FO3/FNV ammunition: AMMO's own layout and FNV's ammo effects (AMEF).

See: docs/commentary/tes4_export_falloutnv.md#ammo-is-a-bolt
"""

import struct

from ..tes4_reader import Record, get_all_subrecords, get_formid_str, get_subrecord
from .common import emit_float, emit_formid, emit_string, emit_u32

#: FNV AMMO DAT2 with a casing: projectiles per shot, projectile, weight, casing (Consumed Ammo), its chance in percent.
DAT2_CASING = 20


def emit_ammo_deltas(lines: list, rec: Record):
    """AMMO's FO3/FNV layout: a 13-byte DATA, then DAT2, the short name and abbreviation, and the effects.

    DATA: speed f32, flags u8 (bit 0 Ignores Normal Weapon Resistance, bit 1
    Non-Playable), 3 unused, value s32, clip rounds u8. DAT2: projectiles
    per shot u32, projectile FormID, weight f32, and in FNV the casing given
    on firing and its chance in percent. ONAM short name, QNAM HUD
    abbreviation, one RCIL per ammo effect (AMEF). The TES4 keys are emitted
    for the shared fields.
    """
    data = get_subrecord(rec, "DATA")
    if data and len(data.data) >= 13:
        d = data.data
        lines.append(f"DATA.Speed={struct.unpack_from('<f', d, 0)[0]}")
        lines.append(f"DATA.Flags={d[4]}")
        lines.append(f"DATA.Value={struct.unpack_from('<i', d, 8)[0]}")
        lines.append(f"DATA.ClipRounds={d[12]}")
    dat2 = get_subrecord(rec, "DAT2")
    if dat2 and len(dat2.data) >= 12:
        d = dat2.data
        lines.append(f"DAT2.ProjPerShot={struct.unpack_from('<I', d, 0)[0]}")
        lines.append(f"DAT2.Projectile={get_formid_str(struct.unpack_from('<I', d, 4)[0])}")
        lines.append(f"DATA.Weight={struct.unpack_from('<f', d, 8)[0]}")
    if dat2 and len(dat2.data) >= DAT2_CASING:
        lines.append(f"DAT2.Casing={get_formid_str(struct.unpack_from('<I', dat2.data, 12)[0])}")
        emit_float(lines, "DAT2.CasingChance", dat2, 16)
    emit_string(lines, "ONAM", get_subrecord(rec, "ONAM"))
    emit_string(lines, "QNAM", get_subrecord(rec, "QNAM"))
    for i, sub in enumerate(get_all_subrecords(rec, "RCIL")):
        emit_formid(lines, f"RCIL[{i}]", sub)


def export_AMMO_EFFECT(rec: Record) -> list:
    """An AMEF: its name and DATA type (Damage, DR, DT, Spread, Condition, Fatigue), operation (Add, Multiply,
    Subtract) and value."""
    lines = []
    emit_string(lines, "EditorID", get_subrecord(rec, "EDID"))
    emit_string(lines, "FULL", get_subrecord(rec, "FULL"))
    data = get_subrecord(rec, "DATA")
    emit_u32(lines, "DATA.Type", data)
    emit_u32(lines, "DATA.Operation", data, 4)
    emit_float(lines, "DATA.Value", data, 8)
    return lines


#: FO3/FNV-only ammunition record exporters.
AMMO_EXPORTERS = {"AMEF": export_AMMO_EFFECT}
