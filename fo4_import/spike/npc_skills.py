"""FNV NPCs' skills as Fallout 4 actor values on the converted NPC (PRPS), read from FalloutNV.esm.

The export leaves NPC_ DNAM out. FNV authors 14 skill values, then 14 offsets,
in actor value order from Barter (FIRST_SKILL); an NPC's skill is its value
plus its offset, at most 100. The converted NPC carries each as the actor
value of that name, so a vendor's Repair skill sets its repair cap.

See: docs/fork/fo4_condition.md#vendor-repair
"""

import struct
from functools import lru_cache

from fo4_import.base.install import source_walk
from fo4_import.helpers_plugin import actor_value_form
from fo4_import.spike.conditions import fnv_av_name
from fo4_import.spike.readables import FIRST_SKILL
from tes5_import.base.tes5_reader import first_sub, subrecords
from tes5_import.base.writer import pack_subrecord

#: FNV NPC_ DNAM's skill count (values, then offsets) and the highest skill.
SKILLS, MAX_SKILL = 14, 100
#: The tags vanilla's PRPS comes right before (xEdit's NPC_ order; AIDT is in every NPC).
PRPS_BEFORE = (b'FTYP', b'NTRM', b'COCT', b'CNTO', b'AIDT')


@lru_cache(maxsize=1)
def npc_skills() -> dict:
    """{FNV NPC_ FormID: its 14 skills (value plus offset, at most 100)}, from the source plugin's DNAM."""
    out = {}
    for rec, _ in source_walk(b'NPC_'):
        dnam = first_sub(rec.body, b'DNAM') or b''
        if len(dnam) >= 2 * SKILLS:
            out[rec.form_id] = [min(MAX_SKILL, dnam[i] + dnam[SKILLS + i]) for i in range(SKILLS)]
    return out


def merged_prps(subs: bytes, values: dict) -> bytes:
    """Subrecords `subs` with PRPS holding `values` {actor value FormID: value} over its own (one added before
    PRPS_BEFORE when it has none)."""
    found = dict(subrecords(subs))
    own = found.get(b'PRPS', b'')
    pairs = {**dict(struct.unpack_from('<If', own, i) for i in range(0, len(own), 8)), **values}
    prps = pack_subrecord('PRPS', b''.join(struct.pack('<If', av, v) for av, v in pairs.items()))
    at = b'PRPS' if b'PRPS' in found else next((t for t, _ in subrecords(subs) if t in PRPS_BEFORE), None)
    out, placed = b'', at is None
    for tag, data in subrecords(subs):
        if tag == at and not placed:
            out, placed = out + prps, True
        out += b'' if tag == b'PRPS' else pack_subrecord(tag.decode(), data)
    return out if at else out + prps


def with_skills(fnv: int, helper_index: int):
    """A record edit giving an NPC FNV NPC `fnv`'s skills as actor values (PRPS); None when it has none."""
    skills = npc_skills().get(fnv)
    pairs = {actor_value_form(fnv_av_name(FIRST_SKILL + i), helper_index): float(v)
             for i, v in enumerate(skills or ())}
    pairs.pop(None, None)
    return (lambda subs: merged_prps(subs, pairs)) if pairs else None


#: FNV CREA DATA offset of Combat Skill (u8), and the skills FalloutNV.exe reads it for (0x5FA180, flag 0x400).
COMBAT_AT, COMBAT_SKILLS = 1, ('EnergyWeapons', 'Explosives', 'MeleeWeapons', 'Guns', 'Unarmed')


@lru_cache(maxsize=1)
def creature_combat() -> dict:
    """{FNV CREA FormID: Combat Skill}, from the source plugin's DATA (the export leaves it out)."""
    out = {}
    for rec, _ in source_walk(b'CREA'):
        data = first_sub(rec.body, b'DATA') or b''
        if len(data) > COMBAT_AT:
            out[rec.form_id] = data[COMBAT_AT]
    return out


def with_creature_skills(fnv: int, helper_index: int):
    """A record edit giving a converted creature FNV creature `fnv`'s Combat Skill as each COMBAT_SKILLS actor
    value (PRPS), as FNV reads it for every combat skill; None when it has none.
    See: docs/fork/fo4_build_next.md#creature-skill
    """
    combat = creature_combat().get(fnv & 0xFFFFFF)
    pairs = {actor_value_form(name, helper_index): float(combat) for name in COMBAT_SKILLS} if combat else {}
    pairs.pop(None, None)
    return (lambda subs: merged_prps(subs, pairs)) if pairs else None
