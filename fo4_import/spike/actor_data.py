"""FNV actor configuration (ACBS) and AI data (AIDT) on a converted NPC or creature, for the cell spike.

A converted actor is a copy of a vanilla body (DocWeathers, DoctorAmari,
Dogmeat, a creature template), whose ACBS and AIDT are that character's:
DocWeathers is Protected (only the player can kill him), DoctorAmari
Essential, both Unaggressive. The copy takes FNV's instead: the flags both
games define alike (Essential, Respawn, PC Level Mult; an NPC's Female and
Auto-calc too), the level band, and FNV's aggression, confidence, energy,
morality (from responsibility), assistance and aggro radius as the Skyrim
side reads them (tes5_import actors_falloutnv). FNV marks an NPC or
creature placed dead on its record (STARTS_DEAD_FNV); FO4 on the placed
actor (STARTS_DEAD). An actor whose FNV script resets its health when hit
(hit_proof_scripts) is Protected: FO4's hit lands before a script's reset.

See: docs/fork/fo4_pipeline.md#npcs
"""

import functools
import re
import struct
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord
from tes5_import.record_types.actor_common import morality
from tes5_import.record_types.actors_falloutnv import aggro_radius, aidt_tiers, assistance

#: FNV creature ACBS Is Ghost and Invulnerable (bits 29, 31; xEdit's FNV list repeats bit 27): FO4's same bits.
IS_GHOST, INVULNERABLE = 0x20000000, 0x80000000
#: FNV creature ACBS Allow PC Dialogue (bit 21); FO4 keeps it on the race.
ACBS_ALLOW_PC_DIALOGUE = 0x200000
#: FNV ACBS flags FO4 defines alike: an NPC's Female, Essential, Respawn, Auto-calc, PC Level Mult; a creature's 5.
NPC_FLAGS, CREATURE_FLAGS = 0x1 | 0x2 | 0x8 | 0x10 | 0x80, 0x2 | 0x8 | 0x80 | IS_GHOST | INVULNERABLE
#: A creature's flags FNV keeps under Base Data, not Stats: Essential, Respawn, Is Ghost, Invulnerable.
BASE_DATA_FLAGS = 0x2 | 0x8 | IS_GHOST | INVULNERABLE
#: The body's ACBS flags a copy drops besides those: Protected, and Unique, which FNV has no flag for.
PROTECTED, UNIQUE = 0x800, 0x20
#: FO4 ACBS offset of the template flags (u16).
ACBS_TEMPLATE = 14
#: FNV record flag of an NPC or creature placed dead (148 of FNV's 150 NPCs named dead; xEdit's Unknown 19).
STARTS_DEAD_FNV = 0x80000
#: FO4 ACHR record flag Starts Dead.
STARTS_DEAD = 0x200
#: FO4 ACBS offsets: flags, level, calc min, calc max (each after the last).
LEVEL_AT = 6
#: An FNV OnHit block (to its END) that resets the actor's health.
RESET_ON_HIT = re.compile(r'(?ims)^\s*begin\s+onhit\b(?:(?!^\s*end\b).)*\bresethealth\b')


@functools.cache
def hit_proof_scripts(export_dir: Path) -> frozenset:
    """FormIDs of FNV scripts whose OnHit block resets health.

    See: docs/fork/fo4_pipeline.md#hit-proof
    """
    return frozenset(int(r['FormID'], 16) for r in export_records(export_dir, 'SCPT')
                     if RESET_ON_HIT.search(r.get('SCTX', '')))


def hit_proof(export_dir: Path, rec: dict) -> bool:
    """Whether FNV actor `rec`'s script is one of hit_proof_scripts."""
    return int(rec.get('SCRI', '0'), 16) in hit_proof_scripts(export_dir)


def acbs(body: bytes, rec: dict, kept: int, protected: bool = False) -> bytes:
    """`body` ACBS with `rec`'s `kept` flags and level band, never Unique; Protected only when `protected`.
    See: docs/fork/fo4_creature_audit.md#unique
    """
    flags = struct.unpack_from('<I', body)[0] & ~(kept | PROTECTED | UNIQUE) | int(rec.get('ACBS.Flags', 0) or 0) & kept
    flags |= PROTECTED if protected else 0
    band = (int(rec.get(k, 0) or 0) for k in ('ACBS.Level', 'ACBS.CalcMin', 'ACBS.CalcMax'))
    return struct.pack('<I', flags) + body[4:LEVEL_AT] + struct.pack('<3H', *band) + body[LEVEL_AT + 6:]


def aidt(rec: dict) -> bytes:
    """FO4 AIDT of FNV `rec`'s AI data: neutral mood, no slow approach flag."""
    aggression, confidence = aidt_tiers(rec)
    behavior, radius = aggro_radius(rec)
    return struct.pack('<BBBBBBBBIIIB3x', aggression, confidence, int(rec.get('AIDT.EnergyLevel', 50) or 50),
                       morality(rec), 0, assistance(rec), behavior, 0, radius, radius, radius, 0)


def with_actor_data(stats: dict, ai: dict, kept: int, protected: bool = False):
    """A record edit giving an actor FNV `stats`' ACBS flags and level (`kept` flags; Protected when
    `protected`) and `ai`'s AIDT."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with ACBS and AIDT replaced."""
        out = b''
        for tag, data in subrecords(subs):
            data = acbs(data, stats, kept, protected) if tag == b'ACBS' else aidt(ai) if tag == b'AIDT' else data
            out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def starts_dead(rec: dict) -> int:
    """FO4's Starts Dead flag when FNV NPC or creature `rec` is placed dead, else 0."""
    return STARTS_DEAD if int(rec.get('RecordFlags', 0) or 0) & STARTS_DEAD_FNV else 0
