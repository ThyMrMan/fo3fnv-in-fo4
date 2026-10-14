"""FNV AI packages as FO4 package instances, for the cell spike.

FO4 packages, like Skyrim's, are instances of template packages filled with
data inputs. Each FNV package becomes a copy of a vanilla FO4 instance of the
matching template (PLANS) with its first input, schedule, conditions and
EditorID replaced, and its owner quest and scripts dropped. Packages whose
type, location or target do not convert are left out and counted by reason.

See: docs/fork/fo4_pipeline.md#packages
"""

import struct

from fo4_import.base.vmad import package_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.dialogue import GREETING
from fo4_import.spike.say_topics import blocker, conditions_of
from fo4_import.spike.readiness import PACKAGE_LEFT_OUT
from fo4_import.spike.script import PACKAGE_PREFIX
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.packages.scripts_falloutnv import package_flags
from tes5_import.base.writer import pack_subrecord

#: Vanilla instances copied per template, inputs in its order at its defaults; their conditions give way to FNV's.
INSTANCES = {'Travel': 0x248982, 'Sit': 0x2471DB, 'Sandbox': 0x24674E, 'ForceGreet': 0x1BEAD3, 'Sleep': 0x1B9EB0,
             'Eat': 0x1AE26C, 'HoldPosition': 0x2491F8, 'Patrol': 0x248492, 'FollowNPC': 0x232257,
             'FleeTo': 0x204C1D, 'FleeFrom': 0x1D4388}
#: What a copy's first input takes from FNV: its location (PLDT), its target (PTDT), or nothing (the template's).
PLACE, TARGET, KEEP = 'place', 'target', 'keep'
#: FNV PKDT type: (FO4 template, first input). Wander sandboxes; Guard holds its position; Patrol walks linked refs.
PLANS = {'1': ('FollowNPC', TARGET), '7': ('FollowNPC', TARGET), '3': ('Eat', PLACE), '4': ('Sleep', PLACE), '5': ('Sandbox', PLACE),
         '6': ('Travel', PLACE), '8': ('Sit', TARGET), '12': ('Sandbox', PLACE), '13': ('Patrol', KEEP),
         '14': ('HoldPosition', PLACE), '15': ('ForceGreet', PLACE)}
FNV_SLEEP, FNV_TRAVEL, FNV_DIALOGUE, FNV_FLEE, FNV_AMBUSH = '4', '6', '15', '10', '9'
#: FNV Ambush type flag Hide While Ambushing (xEdit wbDefinitionsFNV), and the general flag both games call Always Sneak.
HIDE_WHILE_AMBUSHING, ALWAYS_SNEAK = 0x1, 0x20000
#: FO4 PLDT location type near the package's start location (FNV's near current location, the same code).
NEAR_START = 2
#: Fragments of a flee with no location or target: Cowardly while it runs (fo4_pipeline.md#packages).
COWER_SCRIPT = 'TES4_CowerPackage'
#: Its fragment flags: OnBegin and OnEnd.
COWER_FRAGMENTS = 0x01 | 0x02
#: FNV PLDT location type "in cell", and FO4's near reference.
IN_CELL, NEAR_REFERENCE = '1', 0
#: FNV FURN MNAM flag of sleep furniture.
SLEEP_FURNITURE = 0x80000000
#: FNV PKDT package type names (xEdit's wbPackageTypeEnum), for the build's counts.
FNV_TYPES = {'0': 'Find', '1': 'Follow', '2': 'Escort', '3': 'Eat', '4': 'Sleep', '5': 'Wander', '6': 'Travel',
             '7': 'Accompany', '8': 'UseItemAt', '9': 'Ambush', '10': 'FleeNotCombat', '12': 'Sandbox',
             '13': 'Patrol', '14': 'Guard', '15': 'Dialogue', '16': 'UseWeapon'}
#: FNV PTDT target of a Dialogue package that talks to the player.
PLAYER_TARGET = '00000014'
#: FNV PLDT location types FO4 shares: near reference, in cell, near start or editor location, near linked reference.
SHARED_LOCATIONS = ('0', '1', '2', '3', '6')
#: FNV PLDT location types naming a form: a reference, a cell.
NAMED_LOCATIONS = ('0', '1')
#: PKDT general flags FNV and FO4 define alike (xEdit wbPackageFlags), e.g. Weapons Unequipped 0x200000; not 0x200.
SHARED_FLAGS = 0x1 | 0x4 | 0x40 | 0x80 | 0x400 | 0x20000 | 0x40000 | 0x200000 | 0x800000 | 0x8000000
#: PKDT interrupt override byte and None: vanilla's 1,872 NPC-list packages have 0, its 1,499 combat overrides 4.
INTERRUPT_OVERRIDE, NO_OVERRIDE = 5, 0
#: FNV PKDT flag Always Run; FO4's flag at that bit, Preferred Speed, uses PKDT byte SPEED (0 walk, 1 jog, 2 run).
ALWAYS_RUN, SPEED, RUN = 0x2000, 6, 2
#: PTDA/PTDT target types (the same codes in both games): a specific reference, the actor's linked reference.
TARGET_REFERENCE, TARGET_LINKED = 0, 3
#: PSDT month offset of form version 122+ records (xEdit wbPackagePSDTMonthValueToStr): 0 is Any, as vanilla's 1,872.
MONTH_SHIFT = 1
#: PSDT minute vanilla writes on 242 of its 252 timed schedules (FNV schedules start on the hour).
ANY_MINUTE = -1
#: Vanilla subrecords a copy drops: its owner quest, its scripts and its conditions.
DROPPED = (b'QNAM', b'VMAD', b'CTDA', b'CIS1', b'CIS2')


class Packages:
    """FO4 copies of FNV packages; `package` writes one through the builder, `greets` lists the force greets."""

    def __init__(self, builder, export_dir, furniture: set, cell_beds: dict):
        """Index FNV packages and read the vanilla instances; `furniture` holds the FNV references that are seats,
        `cell_beds` each cell's beds (beds())."""
        self.builder, self.furniture, self.beds, self.made, self.greets = builder, furniture, cell_beds, {}, []
        self.why, self.pending = {}, set()
        self.packs = {r['FormID']: r for r in export_records(export_dir, 'PACK')}
        self.by_name = {r['EditorID'].lower(): fid for fid, r in self.packs.items() if r.get('EditorID')}
        wanted = {fid: name for name, fid in INSTANCES.items()}
        self.vanilla = {wanted[r.form_id]: r.body for r, _ in walk(builder.fo4, b'PACK') if r.form_id in wanted}

    def named(self, name: str) -> 'int | None':
        """The FO4 package for a script property naming FNV package `name`: made now once the NPCs' forms are known,
        else reserved on FNV's own id until write_pending(); None for no such package or one left out."""
        fnv = self.by_name.get(name.lower())
        npcs = getattr(self.builder, 'npcs', None)
        if fnv is None or npcs is None:
            self.pending |= {fnv} - {None}
            return self.builder.fnv_id(fnv) if fnv else None
        return self.package(fnv, npcs.form_map) or None

    def write_pending(self, form_map: dict) -> None:
        """Write the packages named() reserved; count those left out."""
        for fnv in sorted(self.pending):
            if not self.package(fnv, form_map):
                self.builder.counts['package property names a package left out'] += 1

    def for_npc(self, npc: dict, form_map: dict) -> list:
        """FO4 FormIDs of FNV NPC `npc`'s packages that convert, in its order; `form_map` maps FNV forms. Each
        one left out is counted against the NPC: why, and how many of its packages it keeps."""
        out, lost = [], []
        total = int(npc.get('AIPackageCount', 0) or 0)
        for i in range(total):
            fid = self.package(npc[f'AIPackage[{i}]'], form_map, int(npc['FormID'], 16))
            out += [fid] if fid else []
            lost += [] if fid else [npc[f'AIPackage[{i}]']]
        for fnv in lost:
            detail = f'{self.packs[fnv].get("EditorID")} ({self.why[fnv]}; keeps {len(out)} of {total})'
            self.builder.counts[f'package left out for {npc.get("EditorID")}: {detail}'] += 1
            self.builder.readiness.add(PACKAGE_LEFT_OUT, npc['FormID'], detail)
        return out

    def package(self, fnv: str, form_map: dict, npc: int = 0) -> int:
        """The FO4 package for FNV package `fnv` (made once, for the first NPC `npc` that runs it), 0 when it
        does not convert."""
        if fnv not in self.made:
            rec = self.packs[fnv]
            plan = self._plan(rec, form_map, npc)
            conditions = conditions_of(rec, form_map, self.builder.script_vars)
            if isinstance(plan, str) or conditions is None:
                why = plan if isinstance(plan, str) else f'condition {blocker(rec, form_map, self.builder.script_vars)}'
                self.builder.counts[f'package left out ({why})'] += 1
                self.made[fnv], self.why[fnv] = 0, why
            else:
                self.made[fnv] = fid = self.builder.fnv_id(fnv)
                self.builder.writer.add_record('PACK', pack_package(fid, rec, self.vanilla[plan[0]], plan[1],
                                                                   conditions, self._fragments(rec), *plan[2:]))
                self.builder.counts[f'PACK {plan[0]}'] += 1
                self.greets += [fid] if plan[0] == 'ForceGreet' else []
        return self.made[fnv]

    def _fragments(self, rec: dict) -> bytes:
        """VMAD binding FNV package `rec`'s converted PF_ script, filled; a cower's (cowers()) COWER_SCRIPT; b''
        without either."""
        flags, name, scripts = package_flags(rec), PACKAGE_PREFIX + rec['FormID'].upper(), self.builder.scripts
        if cowers(rec) and not flags:
            self.builder.counts['cower package'] += 1
            return pack_subrecord('VMAD', package_fragments(COWER_SCRIPT, COWER_FRAGMENTS,
                                                            {'Confidence': FALLOUT4_ACTOR_VALUE_IDS['Confidence']}))
        if not flags or not scripts.dir or not (scripts.dir / f'{name}.psc').exists():
            return b''
        scripts.used.append(name)
        self.builder.counts['package fragments'] += 1
        return pack_subrecord('VMAD', package_fragments(name, flags, scripts.properties(name)))

    def _plan(self, rec: dict, form_map: dict, npc: int) -> 'tuple | str':
        """(template, first input payload[, second input payload]) for FNV package `rec` run by NPC `npc`; why it
        does not convert otherwise."""
        kind = rec.get('PKDT.Type')
        if kind == FNV_FLEE:
            return self._flee(rec, form_map)
        if kind == FNV_AMBUSH:
            template = 'HoldPosition' if not int(rec.get('PLDT.Radius', 0) or 0) else 'Sandbox'
            return self._at(rec, kind, template, form_map)
        if kind not in PLANS:
            return f'type {FNV_TYPES.get(kind, kind)}'
        if kind == FNV_DIALOGUE and not _greets_player(rec):
            return 'dialogue not with the player'
        template, first = PLANS[kind]
        if first == PLACE:
            bed = self._bed(rec, npc) if kind == FNV_SLEEP else None
            return ('Sleep', struct.pack('<iIi', NEAR_REFERENCE, form_map[bed], 0)) if bed in form_map \
                else self._at(rec, kind, template, form_map)
        return self._aimed(rec, template, form_map) if first == TARGET else (template, b'')

    def _at(self, rec: dict, kind: str, template: str, form_map: dict) -> 'tuple | str':
        """(template, PLDT payload) at FNV package `rec`'s location (none: where it starts, as FNV runs it); a
        Travel to a seat sits in it."""
        place = rec.get('PLDT.Type', str(NEAR_START))
        ref = int(rec.get('PLDT.Location', '0') or '0', 16)
        if place not in SHARED_LOCATIONS:
            return f'location type {place}'
        if place in NAMED_LOCATIONS and ref not in form_map:
            return 'location not built'
        if kind == FNV_TRAVEL and place == '0' and ref in self.furniture:
            return 'Sit', struct.pack('<iI', TARGET_REFERENCE, form_map[ref])
        return template, struct.pack('<iIi', int(place), form_map.get(ref, 0), int(rec.get('PLDT.Radius', 0)))

    def _flee(self, rec: dict, form_map: dict) -> 'tuple | str':
        """FNV Flee Not Combat `rec` as FleeTo its location, FleeFrom its target reference with its PTDT distance
        as FO4's Distance to Flee, or with neither (cowering) a HoldPosition where it starts, made Cowardly by
        COWER_SCRIPT (_vmad); why not when it has both (FleeFrom has no first location)."""
        place, target = 'PLDT.Type' in rec, 'PTDT.Type' in rec
        if place and target:
            return 'flee from a target by way of a location'
        if not place and not target:
            return 'HoldPosition', struct.pack('<iIi', NEAR_START, 0, 0)
        if place:
            return self._at(rec, FNV_FLEE, 'FleeTo', form_map)
        ref = int(rec.get('PTDT.Target', '0') or '0', 16)
        if rec.get('PTDT.Type') != str(TARGET_REFERENCE) or ref not in form_map:
            return 'target not built'
        return ('FleeFrom', struct.pack('<iIi', TARGET_REFERENCE, form_map[ref], 0),
                struct.pack('<f', float(rec.get('PTDT.Count', 0) or 0)))

    def _bed(self, rec: dict, npc: int) -> 'int | None':
        """In-cell Sleep `rec`'s bed for `npc`: one it owns, else an unowned one."""
        cell = int(rec.get('PLDT.Location', '0') or '0', 16) if rec.get('PLDT.Type') == IN_CELL else None
        owned = {owner: ref for ref, owner in reversed(self.beds.get(cell, []))}
        return owned.get(npc, owned.get(0))

    def _aimed(self, rec: dict, template: str, form_map: dict) -> 'tuple | str':
        """(template, PTDA payload) at FNV package `rec`'s target reference, or its actor's linked reference (FO4's
        Linked Reference with no keyword, as FNV links have none); a Sit's target must be a seat."""
        ref = int(rec.get('PTDT.Target', '0') or '0', 16)
        if rec.get('PTDT.Type') == str(TARGET_LINKED) and template != 'Sit':
            return template, struct.pack('<iIi', TARGET_LINKED, 0, int(rec.get('PTDT.Count', 0) or 0))
        if rec.get('PTDT.Type') != str(TARGET_REFERENCE) or ref not in form_map:
            return 'target not built'
        if template == 'Sit' and ref not in self.furniture:
            return 'target not a seat'
        return template, struct.pack('<iIi', TARGET_REFERENCE, form_map[ref], int(rec.get('PTDT.Count', 0) or 0))


def beds(builder, refs: list) -> dict:
    """{FNV cell: [(bed reference, its XOWN owner or 0)]} of FNV furniture references `refs` that are beds, by
    FormID."""
    out = {}
    for ref in sorted(refs, key=lambda r: r['FormID']):
        if int(builder.bases[int(ref['NAME'], 16)][1].get('MNAM.Flags', 0)) & SLEEP_FURNITURE:
            out.setdefault(int(ref['ParentCELL'], 16), []).append(
                (int(ref['FormID'], 16), int(ref.get('XOWN.Owner', '0'), 16)))
    return out


def cowers(rec: dict) -> bool:
    """True for a Flee Not Combat with no location or target (it cowers)."""
    return rec.get('PKDT.Type') == FNV_FLEE and 'PLDT.Type' not in rec and 'PTDT.Type' not in rec


def fnv_flags(rec: dict) -> int:
    """`rec`'s general flags, Always Sneak added when an Ambush hides."""
    hides = rec.get('PKDT.Type') == FNV_AMBUSH and int(rec.get('PKDT.TypeFlags', 0) or 0) & HIDE_WHILE_AMBUSHING
    return int(rec.get('PKDT.Flags', 0) or 0) | (ALWAYS_SNEAK if hides else 0)


def _greets_player(rec: dict) -> bool:
    """True when Dialogue package `rec` greets the player (GREETING or no topic)."""
    return rec.get('PTDT.Target') == PLAYER_TARGET and int(rec.get('PKDD.Topic', '0'), 16) in (0, GREETING)


def schedule(rec: dict) -> bytes:
    """FO4 PSDT of FNV package `rec`'s schedule (MONTH_SHIFT, minutes)."""
    return struct.pack('<bbbbb3xi', int(rec.get('PSDT.Month', -1)) + MONTH_SHIFT, int(rec.get('PSDT.DayOfWeek', -1)),
                       int(rec.get('PSDT.Date', 0)), int(rec.get('PSDT.Time', -1)), ANY_MINUTE,
                       int(rec.get('PSDT.Duration', 0)) * 60)


def _pkdt(flags: int, vanilla: bytes) -> bytes:
    """The vanilla PKDT with FNV `flags` the games share, no interrupt override, and FNV's Always Run as FO4's
    preferred speed Run."""
    run = flags & ALWAYS_RUN
    speed = bytes([RUN]) if run else vanilla[SPEED:SPEED + 1]
    return (struct.pack('<I', flags & SHARED_FLAGS | run) + vanilla[4:INTERRUPT_OVERRIDE] + bytes([NO_OVERRIDE])
            + speed + vanilla[SPEED + 1:])


def pack_package(fid: int, rec: dict, vanilla: bytes, first_input: bytes, conditions: bytes,
                 vmad: bytes = b'', second_input: bytes = b'') -> bytes:
    """A copy of vanilla instance `vanilla` for FNV package `rec`: its EditorID, `vmad` (its fragments), schedule
    and conditions after PSDT, the first PLDT/PTDA from `first_input` (the vanilla bytes past it kept) and the
    first value input (CNAM) from `second_input` when given, PKDT flags the games share (SHARED_FLAGS) and no
    interrupt override: it goes in an NPC's package list, where a combat override hangs the load.
    See: docs/fork/fo4_pipeline.md#packages
    """
    fields, out, replaced = {b'EDID': f'FNV_{rec["EditorID"]}'.encode() + b'\0', b'PSDT': schedule(rec)}, b'', False
    for tag, data in subrecords(vanilla):
        if tag == b'PKDT':
            data = _pkdt(fnv_flags(rec), data)
        elif tag in (b'PLDT', b'PTDA') and not replaced:
            data, replaced = first_input + data[len(first_input):], True
        elif tag == b'CNAM' and second_input:
            data, second_input = second_input, b''
        if tag not in DROPPED:
            out += pack_subrecord(tag.decode(), fields.get(tag, data)) + {b'PSDT': conditions, b'EDID': vmad}.get(tag, b'')
    return pack_fo4_record('PACK', fid, 0, out)
