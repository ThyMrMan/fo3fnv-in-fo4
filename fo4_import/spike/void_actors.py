"""FNV's void creatures as one FO4 actor that removes itself on load: a leveled list's chance of nothing.

FNV makes a list's chance of nothing with void entries (`CRVoid`,
`VCrILikeOblivionChancedSpawns`: the empty `creatures\\nvvoid` mesh, the
second killing and destroying itself on load); LVLD chance none is 0 in all
343 lists, and neither Skyrim nor Fallout 4 gives a placed actor's list a
partial chance none. Every void entry becomes one actor: a copy of the mole
rat on its own race (a copy of `MoleratRace`) wearing an empty skin, with no
factions, packages, inventory or aggression, running SCRIPT. A template actor
whose list can draw the void runs SCRIPT too, checking its race (`check`).

See: docs/fork/fo4_creature_audit.md#void
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.actor_data import ACBS_TEMPLATE
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

VOID_FOLDER, SCRIPT, SITE = 'creatures\\nvvoid', 'F3NV_VoidActor', 'FNV void actor'
#: The Fallout4.esm actor and race the void copies.
BODY, RACE = 'EncMolerat01Template', 'MoleratRace'
#: The copy's parts the void leaves out: scripts, factions, packages, items, outfit, spells, perks, template, attacks.
DROPPED = frozenset({b'VMAD', b'SNAM', b'PKID', b'COCT', b'CNTO', b'DOFT', b'INAM', b'SPCT', b'SPLO', b'PRKZ',
                     b'PRKR', b'TPLT', b'TPTA', b'ATKR', b'ECOR'})
#: A skin's addon list (ARMO): index and addon.
ADDONS = frozenset({b'INDX', b'MODL'})
#: AIDT's aggression byte (0: unaggressive).
AGGRESSION = 0
#: Offset of an FO4 RACE DATA's flags (after the heights and default weights).
RACE_FLAGS_AT = 32


def invisible_race(builder, race_edid: str, site: str, name: str, flags: int = 0) -> tuple:
    """(race, skin) FormIDs: Fallout4.esm race `race_edid` copied as `FNV_<name>Race`, its DATA flags or'd with
    `flags`, wearing `FNV_<name>Skin`, a copy of its skin with no addons (nothing drawn); hashed at `site`."""
    race = next(rec for rec, _ in walk(builder.fo4, b'RACE')
                if dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode() == race_edid)
    subs = dict(subrecords(race.body))
    skin_of = struct.unpack('<I', subs[b'WNAM'])[0]
    armo = next(rec for rec, _ in walk(builder.fo4, b'ARMO') if rec.form_id == skin_of)
    skin, race_fid = (builder.writer.derive_formid(site, part) for part in ('ARMO', 'RACE'))
    builder.writer.add_record('ARMO', copy_record(armo, skin, f'FNV_{name}Skin', drop=ADDONS))
    builder.writer.add_record('RACE', copy_record(race, race_fid, f'FNV_{name}Race',
                                                  {b'WNAM': struct.pack('<I', skin),
                                                   b'DATA': with_race_flags(subs[b'DATA'], flags)}))
    return race_fid, skin


def with_race_flags(data: bytes, flags: int) -> bytes:
    """RACE DATA `data` with its flags or'd with `flags`."""
    out = bytearray(data)
    struct.pack_into('<I', out, RACE_FLAGS_AT, struct.unpack_from('<I', out, RACE_FLAGS_AT)[0] | flags)
    return bytes(out)


class VoidActors:
    """The build's void actor, written on first use through `builder`."""

    def __init__(self, builder):
        """Void actors for `builder`'s plugin (its writer, scripts and Fallout4.esm bytes)."""
        self.builder, self.fid, self.race = builder, None, None

    def actor(self) -> int:
        """The void actor's FormID, written once with its race and skin."""
        if self.fid is None:
            self._write()
        return self.fid

    def check(self) -> tuple:
        """The VMAD entry a template actor drawing from a list with void entries runs."""
        self.actor()
        return ((SCRIPT, {'VoidRace': self.race}, {}),)

    def _write(self) -> None:
        """Write the empty skin, the race copy wearing it and the actor on it, SCRIPT on the actor."""
        body = next(rec for rec, _ in walk(self.builder.fo4, b'NPC_')
                    if dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0').decode() == BODY)
        self.race, skin = invisible_race(self.builder, RACE, SITE, 'Void')
        self.fid = self.builder.writer.derive_formid(SITE, 'NPC_')
        self.builder.writer.add_record('NPC_', copy_record(body, self.fid, 'FNV_VoidActor', drop=DROPPED,
                                                           edit=self._actor_edit(skin)))
        self.builder.scripts.used.append(SCRIPT)
        self.builder.counts['void actor'] += 1

    def _actor_edit(self, skin: int):
        """The void actor's subrecords: SCRIPT after EDID, on the void race in the empty skin, no template,
        unaggressive."""
        values = {b'RNAM': struct.pack('<I', self.race), b'WNAM': struct.pack('<I', skin)}

        def edit(tag: bytes, data: bytes) -> bytes:
            """One subrecord as the void actor's."""
            if tag == b'ACBS':
                data = data[:ACBS_TEMPLATE] + b'\0\0' + data[ACBS_TEMPLATE + 2:]
            elif tag == b'AIDT':
                data = bytes([AGGRESSION]) + data[1:]
            out = pack_subrecord(tag.decode(), values.get(tag, data))
            return out + (pack_subrecord('VMAD', self.builder.scripts.vmad(0, ((SCRIPT, {}, {}),)))
                          if tag == b'EDID' else b'')
        return edit


def copy_record(vanilla, fid: int, edid: str, values: dict = None, drop: frozenset = frozenset(), edit=None) -> bytes:
    """Vanilla record `vanilla` as `fid` named `edid`: `values` replaced, `drop` left out, each subrecord through
    `edit(tag, data)` when given."""
    values, out = values or {}, b''
    for tag, data in subrecords(vanilla.body):
        if tag in drop:
            continue
        data = edid.encode() + b'\0' if tag == b'EDID' else values.get(tag, data)
        out += edit(tag, data) if edit else pack_subrecord(tag.decode(), data)
    return pack_fo4_record(vanilla.sig.decode(), fid, vanilla.flags, out)
