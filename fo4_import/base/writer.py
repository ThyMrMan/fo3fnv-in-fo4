"""Fallout 4 plugin writer.

FO4 keeps Skyrim's framing (24-byte record and GRUP headers, 6-byte
subrecords, XXXX for long subrecords), so this reuses tes5_import's packers and
PluginWriter. What differs is the form version (131), the file header (HEDR
1.0, INTV, a required INCC) and the top-level group order. Dialogue does not
get a top-level group: each quest is followed by its own quest-children group
(type 10) holding its DLBR, DIAL (each with a type-7 group of INFOs) and SCEN.

See: docs/fork/research/fo4_target.md#formats
"""

import struct

from tes5_import.base.writer import (
    PluginWriter, pack_group, pack_record, pack_string_subrecord, pack_subrecord,
)

FORM_VERSION_FO4 = 131
HEDR_VERSION_FO4 = 1.0
#: The INTV value XDI.esm and CK-saved plugins carry; the runtime ignores it.
INTV_FO4 = 1

GRP_TOPIC_CHILDREN = 7
GRP_QUEST_CHILDREN = 10

#: First-seen top-level group order of Fallout4.esm 1.11.240; DLCRobot.esm and UFO4P follow it.
FO4_GROUP_ORDER = (
    'GMST', 'KYWD', 'LCRT', 'AACT', 'TRNS', 'CMPO', 'TXST', 'GLOB', 'DMGT',
    'CLAS', 'FACT', 'HDPT', 'RACE', 'SOUN', 'ASPC', 'MGEF', 'LTEX', 'ENCH',
    'SPEL', 'ACTI', 'TACT', 'ARMO', 'BOOK', 'CONT', 'DOOR', 'INGR', 'LIGH',
    'MISC', 'STAT', 'SCOL', 'MSTT', 'GRAS', 'TREE', 'FLOR', 'FURN', 'WEAP',
    'AMMO', 'NPC_', 'LVLN', 'KEYM', 'ALCH', 'IDLM', 'NOTE', 'PROJ', 'HAZD',
    'BNDS', 'TERM', 'LVLI', 'WTHR', 'CLMT', 'SPGD', 'RFCT', 'REGN', 'NAVI',
    'CELL', 'WRLD', 'QUST', 'IDLE', 'PACK', 'CSTY', 'LSCR', 'ANIO', 'WATR',
    'EFSH', 'EXPL', 'DEBR', 'IMGS', 'IMAD', 'FLST', 'PERK', 'BPTD', 'ADDN',
    'AVIF', 'CAMS', 'CPTH', 'VTYP', 'MATT', 'IPCT', 'IPDS', 'ARMA', 'ECZN',
    'LCTN', 'MESG', 'DOBJ', 'DFOB', 'LGTM', 'MUSC', 'FSTP', 'FSTS', 'SMBN',
    'SMQN', 'SMEN', 'MUST', 'DLVW', 'EQUP', 'RELA', 'ASTP', 'OTFT', 'ARTO',
    'MATO', 'MOVT', 'SNDR', 'SNCT', 'SOPM', 'COLL', 'CLFM', 'REVB', 'PKIN',
    'RFGP', 'AMDL', 'LAYR', 'COBJ', 'OMOD', 'MSWP', 'ZOOM', 'INNR', 'KSSM',
    'AECH', 'SCCO', 'AORU', 'SCSN', 'STAG', 'NOCM', 'LENS', 'GDRY', 'OVIS',
)

FLAG_ESM = 0x1
FLAG_ESL = 0x200


def pack_fo4_record(sig: str, form_id: int, flags: int, subrecords: bytes) -> bytes:
    """A record with the FO4 form version."""
    return pack_record(sig, form_id, flags, subrecords, FORM_VERSION_FO4)


def pack_topic(dial_record: bytes, dial_fid: int, infos: list) -> bytes:
    """A DIAL record, then its topic-children group of INFOs (none if no INFOs)."""
    if not infos:
        return dial_record
    return dial_record + pack_group(GRP_TOPIC_CHILDREN, struct.pack('<I', dial_fid), b''.join(infos))


def pack_quest(qust_record: bytes, qust_fid: int, branches: list = (),
               topics: list = (), scenes: list = ()) -> bytes:
    """A QUST record and its quest-children group, in vanilla's order.

    branches are DLBR records, topics are pack_topic() blobs, scenes are SCEN
    records. A quest with none of them gets no group.
    """
    children = b''.join(branches) + b''.join(topics) + b''.join(scenes)
    if not children:
        return qust_record
    return qust_record + pack_group(GRP_QUEST_CHILDREN, struct.pack('<I', qust_fid), children)


def count_records(blob: bytes, sig: bytes) -> int:
    """How many records of one signature a serialized group holds, at any depth."""
    count, pos = 0, 0
    while pos + 24 <= len(blob):
        tag, size = struct.unpack_from('<4sI', blob, pos)
        if tag == b'GRUP':
            count += count_records(blob[pos + 24:pos + size], sig)
            pos += size
        else:
            count += tag == sig
            pos += 24 + size
    return count


def pack_fo4_header(masters: list, num_records: int, next_object_id: int,
                    interior_cells: int, author: str, description: str = '',
                    flags: int = FLAG_ESM, overridden_forms: list = ()) -> bytes:
    """The TES4 file header in FO4's layout: HEDR, CNAM, SNAM, masters, ONAM, INTV, INCC."""
    subs = pack_subrecord('HEDR', struct.pack('<fII', HEDR_VERSION_FO4, num_records, next_object_id))
    subs += pack_string_subrecord('CNAM', author)
    if description:
        subs += pack_string_subrecord('SNAM', description)
    for master in masters:
        subs += pack_string_subrecord('MAST', master) + pack_subrecord('DATA', b'\x00' * 8)
    if overridden_forms:
        subs += pack_subrecord('ONAM', b''.join(struct.pack('<I', f) for f in sorted(set(overridden_forms))))
    subs += pack_subrecord('INTV', struct.pack('<I', INTV_FO4))
    subs += pack_subrecord('INCC', struct.pack('<I', interior_cells))
    return pack_fo4_record('TES4', 0, flags, subs)


class FO4PluginWriter(PluginWriter):
    """PluginWriter with FO4's header and group order.

    Quests carry their dialogue: add each pack_quest() blob with
    add_record('QUST', blob).
    """

    def __init__(self, masters: list = None, is_esm: bool = True, is_esl: bool = False,
                 author: str = 'fo3fnv-in-fo4', description: str = ''):
        """Pass masters=['Fallout4.esm'] when records reference the base game."""
        super().__init__(masters=masters, is_esm=is_esm, author=author, description=description)
        self.is_esl = is_esl

    def _pack_header(self, total_count: int, overridden: list, group_blobs: list) -> bytes:
        """FO4 header; INCC counts the interior CELL records actually written."""
        flags = (FLAG_ESM if self.is_esm else 0) | (FLAG_ESL if self.is_esl else 0)
        interior = sum(count_records(b, b'CELL') for b in group_blobs if b[8:12] == b'CELL')
        return pack_fo4_header(self.masters, total_count, self._high_water_id(), interior,
                               self.author, self.description, flags, overridden)

    def _group_order(self) -> list:
        """FO4_GROUP_ORDER, then any other signature present, in insertion order."""
        order = list(FO4_GROUP_ORDER)
        order += [sig for sig in self._top_groups if sig not in order]
        return order
