"""FNV's per-entry item condition (COED) on containers, actors and leveled lists, read from FalloutNV.esm.

The export leaves COED out. FNV authors an entry's condition as a COED right
after its CNTO (container, NPC, creature item) or LVLO (leveled list entry):
owner, global or rank, then the condition (a float, 0 to 1). Fallout 4's
COED has the same layout and gives the spawned item that health.

See: docs/fork/fo4_condition.md#entry-condition
"""

import struct
from functools import lru_cache

from fo4_import.base.install import source_walk
from tes5_import.base.tes5_reader import subrecords

#: The records whose entries carry a COED, by the entry subrecord before it.
ENTRY_TAGS = {b'CONT': b'CNTO', b'NPC_': b'CNTO', b'CREA': b'CNTO', b'LVLI': b'LVLO', b'LVLN': b'LVLO',
              b'LVLC': b'LVLO'}
#: COED's condition offset.
CONDITION_AT = 8


@lru_cache(maxsize=1)
def entry_conditions() -> dict:
    """{FNV FormID: [condition or None, per entry in order]} of the records with an entry that has a COED."""
    out = {}
    for rec, _ in source_walk(*ENTRY_TAGS):
        tag, entries, found = ENTRY_TAGS[rec.sig], [], False
        for sub, data in subrecords(rec.body):
            if sub == tag:
                entries.append(None)
            elif sub == b'COED' and entries and len(data) >= CONDITION_AT + 4:
                entries[-1] = struct.unpack_from('<f', data, CONDITION_AT)[0]
                found = True
        if found:
            out[rec.form_id] = entries
    return out


def condition_of(fnv: int, index: int) -> 'float | None':
    """The condition FNV record `fnv` authors on its entry `index`; None without one."""
    entries = entry_conditions().get(fnv, ())
    return entries[index] if index < len(entries) else None
