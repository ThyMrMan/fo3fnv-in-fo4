"""FNV creatures' attack sets as per-NPC attack data on their FO4 stand-ins.

A converted creature keeps its stand-in's body and behaviour graph, so it can
only play attacks that graph knows: its race's attack data (event names).
Each creature gets its own attack list (as vanilla's DLC04 bloodworms carry
a subset of their race's): the race's attacks, each kept or disabled (chance
0) by what FNV lets that creature do (FalloutNV.exe):

- FNV melee hits only inside its hit cone (fCombatHitConeAngle 35, 0x9a6ae0),
  so an attack aimed beside or behind (|attack angle| over it) is off;
- power attacks are off when the creature's style never power attacks or it
  has no power-attack animation (0x644810, 0x97ff60);
- charge attacks are off when its style has no rushing attack (0x9cf090).

A creature's FNV damage is its own attack damage with no per-attack or power
multiplier (0x8ae98a skips the power bonus for creatures), so every kept
attack has damage mult 1. FO4 picks one attack by weight (Attack Chance,
Fallout4.exe 0xf7b5c0), power and normal alike, so the kept entries are
weighted to give power attacks FNV's share of attacks.

See: docs/fork/fo4_pipeline.md#creature-attacks
"""

import re
import struct
from pathlib import Path

from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FNV's melee hit cone in degrees (fCombatHitConeAngle; FalloutNV.esm does not override it).
HIT_CONE = 35.0
#: FO4 ATKD (xEdit): damage, chance, spell, flags, attack/strike angle, stagger, knockdown, recovery, AP, offset.
ATKD = struct.Struct('<2f2I6fi')
#: FO4 attack flags: power, charge.
POWER, CHARGE = 0x4, 0x8
#: The tags the attack list goes before (vanilla NPC_ order after RNAM/WNAM/ANAM).
ATTACKS_BEFORE = (b'SPOR', b'OCOR', b'GWOR', b'ECOR', b'PRKZ', b'PRKR', b'PRPS', b'FTYP', b'NTRM', b'COCT', b'CNTO',
                  b'AIDT')
#: FNV .kf name prefixes (hand type, then movement) before the group name (FalloutNV.exe 0x5f38d0).
KF_PREFIX = re.compile(r'^(?:pa)?(?:h2h|1hm|2hm|1hp|2hr|2ha|2hh|2hl|1gt|1md|1lm)?(?:sneak|swim|fly)?')
#: FNV normal-attack groups (0x1A..0x44, Attack9) and power-attack groups by direction (0x5C..0x60).
NORMAL_GROUPS = frozenset({'attackleft', 'attackright', *(f'attack{n}' for n in range(3, 10))})
POWER_GROUPS = {'attackpower': 'Normal', 'attackforwardpower': 'Forward', 'attackbackpower': 'Back',
                'attackleftpower': 'Left', 'attackrightpower': 'Right'}
#: FNV CSTD flag Choose Attack using % Chance: power-attack directions by their weights.
CHOOSE_BY_CHANCE = 0x1


def kf_group(name: str) -> str:
    """The FNV animation group of .kf file `name` (prefixes off, cut at the first '_')."""
    stem = Path(name).stem.lower()
    return KF_PREFIX.sub('', stem, count=1).split('_', 1)[0]


def fnv_groups(export_dir: Path, folder: str) -> frozenset:
    """The animation groups of skeleton folder `folder`'s .kf files."""
    root = Path(export_dir) / 'meshes' / folder
    return frozenset(kf_group(p.name) for p in root.rglob('*.kf')) if root.is_dir() else frozenset()


def power_directions(groups: frozenset, style: dict) -> frozenset:
    """The power-attack directions FNV can play: a group it has, weighted above 0 when its style chooses by chance;
    none when the style's power-attack chance is 0."""
    if int(style.get('CSTD.PowerAttackChance', 0) or 0) <= 0:
        return frozenset()
    by_chance = int(style.get('CSTD.Flags', 0) or 0) & CHOOSE_BY_CHANCE
    return frozenset(d for g, d in POWER_GROUPS.items()
                     if g in groups and (not by_chance or int(style.get(f'CSTD.PowerAttack{d}', 0) or 0) > 0))


def kept(values: tuple, groups: frozenset, powers: frozenset, style: dict) -> bool:
    """Whether FO4 attack `values` (ATKD fields) is one FNV's creature could make."""
    flags, angle = values[3], values[4]
    if abs(angle) > HIT_CONE:
        return False
    if flags & POWER:
        return bool(powers)
    if flags & CHARGE and int(style.get('CSTD.RushingAttackChance', 0) or 0) <= 0:
        return False
    return bool(groups & NORMAL_GROUPS) or not groups


def attacks_of(body: bytes) -> list:
    """[(ATKD bytes, ATKE bytes, its other attack subrecords packed)] of record `body`, in order."""
    attacks = []
    for tag, data in subrecords(body):
        if tag == b'ATKD':
            attacks.append([data, b'', b''])
        elif attacks and tag == b'ATKE':
            attacks[-1][1] = data
        elif attacks and tag in (b'ATKW', b'ATKS', b'ATKT'):
            attacks[-1][2] += pack_subrecord(tag.decode(), data)
    return [tuple(a) for a in attacks]


def race_attacks(fo4: bytes) -> dict:
    """{RACE FormID: attacks_of its body} of Fallout4.esm's races that have attacks."""
    return {rec.form_id: found for rec, _ in walk(fo4, b'RACE') if (found := attacks_of(rec.body))}


def power_share(style: dict) -> float:
    """FNV's chance an attack is a power attack, at full fatigue: rand() % 100 <= PA% + fatigue base (0x644810)."""
    chance = int(style.get('CSTD.PowerAttackChance', 0) or 0)
    if chance <= 0 or chance >= 100:
        return float(chance >= 100)
    return min(1.0, (int(chance + float(style.get('CSAD.PowerAttackFatigueModBase', 0) or 0)) + 1) / 100.0)


def weights(normal: int, power: int, share: float) -> tuple:
    """(normal, power) entry weights giving power attacks `share` of FO4's weighted pick over `normal` and `power`
    kept entries, the smaller at 1 so FO4's acceptance roll (rand01() > weight rejects) never fires."""
    if not normal or not power:
        return 1.0, 1.0
    if share >= 1.0 or share <= 0.0:
        return float(share < 1.0), float(share > 0.0)
    ratio = share * normal / ((1.0 - share) * power)
    return (1.0 / ratio, 1.0) if ratio < 1.0 else (1.0, ratio)


def attack_list(attacks: list, groups: frozenset, style: dict, spell: int = 0) -> tuple:
    """(subrecords of `attacks` as FNV's creature uses them, kept count). A kept attack (one FNV's creature could
    make, not disabled by vanilla) has damage mult 1 and its group's weight (weights); charge attacks keep 1;
    the rest have chance 0. Every attack casts `spell` (attack_spells; 0: none), not the stand-in's."""
    powers, decoded = power_directions(groups, style), [list(ATKD.unpack_from(a)) for a, _, _ in attacks]
    on = [v[1] > 0 and kept(tuple(v), groups, powers, style) for v in decoded]
    kinds = ['charge' if v[3] & CHARGE else 'power' if v[3] & POWER else 'normal' for v in decoded]
    count = {k: sum(o and t == k for o, t in zip(on, kinds)) for k in ('normal', 'power')}
    normal, power = weights(count['normal'], count['power'], power_share(style))
    out = b''
    for (atkd, atke, rest), values, use, kind in zip(attacks, decoded, on, kinds):
        values[0], values[1] = (1.0, {'normal': normal, 'power': power, 'charge': 1.0}[kind]) if use else (values[0], 0.0)
        values[2] = spell
        out += pack_subrecord('ATKD', ATKD.pack(*values) + atkd[ATKD.size:]) + pack_subrecord('ATKE', atke) + rest
    return out, sum(on)


def with_spell(subs: bytes, spell: int) -> bytes:
    """Attack subrecords `subs` with every attack casting `spell`."""
    out = b''
    for tag, data in subrecords(subs):
        if tag == b'ATKD':
            values = list(ATKD.unpack_from(data))
            values[2] = spell
            data = ATKD.pack(*values) + data[ATKD.size:]
        out += pack_subrecord(tag.decode(), data)
    return out


def with_attacks(race: int, subs: bytes):
    """A record edit setting ATKR to `race` and the attack list to `subs` (attack_list), where vanilla puts them."""
    block = pack_subrecord('ATKR', struct.pack('<I', race)) + subs

    def edit(record: bytes) -> bytes:
        """The subrecords with the stand-in's own attack race and list replaced."""
        out, placed = b'', False
        for tag, data in subrecords(record):
            if tag in (b'ATKR', b'ATKD', b'ATKE', b'ATKW', b'ATKS', b'ATKT'):
                continue
            if tag in ATTACKS_BEFORE and not placed:
                out, placed = out + block, True
            out += pack_subrecord(tag.decode(), data)
        return out if placed else out + block
    return edit
