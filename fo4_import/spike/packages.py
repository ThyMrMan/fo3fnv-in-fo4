"""FNV AI packages as FO4 package instances, for the cell spike.

FO4 packages, like Skyrim's, are instances of template packages filled with
data inputs. Each FNV package becomes a copy of a vanilla FO4 instance of the
matching template (PLANS) with its first input, schedule, conditions and
EditorID replaced, and its owner quest and scripts dropped. Packages whose
type, location or target do not convert are left out and counted by reason.

See: docs/fork/fo4_pipeline.md#packages
"""

import math
import struct

from fo4_import.base.vmad import package_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.dialogue import GREETING
from fo4_import.spike.say_topics import blocker, conditions_of
from fo4_import.spike.readiness import PACKAGE_LEFT_OUT
from fo4_import.spike.records import pack_flst
from fo4_import.spike.script import PACKAGE_PREFIX
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.packages.scripts_falloutnv import package_flags
from tes5_import.base.writer import pack_subrecord
from tes5_import.base.text_reader import get_hex_bytes
from tes5_import.record_types.navm_falloutnv import parse_vertices

#: Vanilla instances copied per template, inputs in its order at its defaults; their conditions give way to FNV's.
INSTANCES = {'Travel': 0x248982, 'Sit': 0x2471DB, 'Sandbox': 0x24674E, 'ForceGreet': 0x1BEAD3, 'Sleep': 0x1B9EB0,
             'Eat': 0x1AE26C, 'HoldPosition': 0x2491F8, 'Patrol': 0x248492, 'FollowNPC': 0x232257,
             'FleeTo': 0x204C1D, 'FleeFrom': 0x1D4388}
#: A copy's first input from FNV: its location, its target, its location as a Patrol start, or the template's.
PLACE, TARGET, START, KEEP = 'place', 'target', 'start', 'keep'
#: FNV PKDT type: (FO4 template, first input). Wander sandboxes; Guard holds its position; Patrol walks linked refs.
PLANS = {'1': ('FollowNPC', TARGET), '7': ('FollowNPC', TARGET), '3': ('Eat', PLACE), '4': ('Sleep', PLACE), '5': ('Sandbox', PLACE),
         '6': ('Travel', PLACE), '8': ('Sit', TARGET), '12': ('Sandbox', PLACE), '13': ('Patrol', START),
         '14': ('HoldPosition', PLACE), '15': ('ForceGreet', PLACE)}
FNV_SLEEP, FNV_TRAVEL, FNV_DIALOGUE, FNV_FLEE, FNV_AMBUSH, FNV_GUARD = '4', '6', '15', '10', '9', '14'
#: FNV Ambush type flag Hide While Ambushing (xEdit wbDefinitionsFNV), and the general flag both games call Always Sneak.
HIDE_WHILE_AMBUSHING, ALWAYS_SNEAK = 0x1, 0x20000
#: FO4 PLDT location type near the package's start location (FNV's near current location, the same code).
NEAR_START = 2
#: Fragments of a flee with no location or target: Cowardly while it runs (fo4_pipeline.md#packages).
COWER_SCRIPT = 'F3NV_CowerPackage'
#: Its fragment flags: OnBegin and OnEnd.
COWER_FRAGMENTS = 0x01 | 0x02
#: FNV PLDT location type "in cell", and FO4's near reference.
IN_CELL, NEAR_REFERENCE = '1', 0
#: Record flag Persistent; an FO4 package's place stays loaded only on a persistent reference.
PERSISTENT = 0x400
#: FNV package types whose copy is a Sandbox with FNV's own No flags: Wander, Sandbox.
SANDBOX_TYPES = ('5', '12')
#: FO4 Sandbox Allow inputs and the FNV type-specific No flag each negates (No Furniture covers both seats).
ALLOWS = {'Allow Eating': 0x1, 'Allow Sleeping': 0x2, 'Allow Conversation': 0x4, 'Allow Idle Markers': 0x8,
          'Allow Sitting': 0x10, 'Allow Special Furniture': 0x10, 'Allow Wandering': 0x20}
#: FNV PLDT location type near a reference, as the export writes it.
NEAR_LOCATION = '0'
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
#: ForceGreet's Target Trigger Location: its second location input (after the NPC Wait Location).
TRIGGER_INPUT = 1
#: PKDT general flags FNV and FO4 define alike (xEdit wbPackageFlags), e.g. Weapons Unequipped 0x200000; not 0x200.
SHARED_FLAGS = 0x1 | 0x4 | 0x40 | 0x80 | 0x400 | 0x20000 | 0x40000 | 0x200000 | 0x800000 | 0x8000000
#: PKDT interrupt override byte and None: vanilla's 1,872 NPC-list packages have 0, its 1,499 combat overrides 4.
INTERRUPT_OVERRIDE, NO_OVERRIDE, COMBAT_OVERRIDE = 5, 0, 4
#: FNV general flag 0x1000 (xEdit: Skip Fallout Behavior), set on every FNV package that authors its behavior flags.
OWN_BEHAVIOR = 0x1000
#: FO4 PKDT interrupt flags offset; the bits FNV's behavior flags share with them (Hellos To Player ... Idle Chatter).
INTERRUPT_FLAGS, SHARED_BEHAVIOR = 8, 0xFF
#: FNV general flag Continue During Combat.
CONTINUE_DURING_COMBAT = 0x4000000
#: derive_formid sites: a package's combat override copy (key: FNV package), an NPC's override list (key: FNV NPC).
COMBAT_SITE, COMBAT_LIST_SITE = 'FNV PACK combat', 'FNV ECOR'
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

    def __init__(self, builder, export_dir, furniture: set, cell_beds: dict, refs: list):
        """Index FNV packages and read the vanilla instances; `furniture` holds the FNV references that are seats,
        `cell_beds` each cell's beds (beds()), `refs` the build's references (in-cell places, _in_cell)."""
        self.builder, self.furniture, self.beds, self.made, self.greets = builder, furniture, cell_beds, {}, []
        self.topics, self.cell_refs, self.navmeshes, self.combat, self.combat_lists = {}, {}, {}, {}, {}
        for ref in refs:
            self.cell_refs.setdefault(ref.get('ParentCELL'), []).append(ref)
        self.boxes = {int(r['FormID'], 16): min(float(r['XPRM.BoundX']), float(r['XPRM.BoundY'])) for r in refs
                      if 'XPRM.BoundX' in r}
        for rec in export_records(export_dir, 'NAVM'):
            self.navmeshes.setdefault(rec.get('DATA.Cell'), []).append(rec)
        self.why, self.pending, self.scripted = {}, set(), set()
        self.packs = {r['FormID']: r for r in export_records(export_dir, 'PACK')}
        self.by_name = {r['EditorID'].lower(): fid for fid, r in self.packs.items() if r.get('EditorID')}
        packs ={r.form_id: r.body for r, _ in walk(builder.fo4, b'PACK')}
        self.vanilla = {name: packs[fid] for name, fid in INSTANCES.items()}
        self.slots = {name: value_slots(self.vanilla[name], packs) for name in ('Sandbox', 'FollowNPC')}

    def named(self, name: str) -> 'int | None':
        """The FO4 package for a script property naming FNV package `name`: made now once the NPCs' forms are known,
        else reserved on FNV's own id until write_pending(); None for no such package or one left out."""
        fnv = self.by_name.get(name.lower())
        self.scripted |= {fnv} - {None}
        npcs = getattr(self.builder, 'npcs', None)
        if fnv is None or npcs is None:
            self.pending |= {fnv} - {None}
            return self.builder.fnv_id(fnv) if fnv else None
        return self.package(fnv, npcs.form_map) or None

    def scripted_made(self) -> list:
        """[(FNV EditorID, FO4 package)] scripts named that were written."""
        made = [(self.packs[fnv].get('EditorID', fnv), self.made.get(fnv)) for fnv in self.scripted]
        return sorted((name, fid) for name, fid in made if fid)

    def write_pending(self, form_map: dict) -> None:
        """Write the packages named() reserved; count those left out."""
        for fnv in sorted(self.pending):
            if not self.package(fnv, form_map):
                self.builder.counts['package property names a package left out'] += 1

    def for_npc(self, npc: dict, form_map: dict) -> list:
        """FO4 FormIDs of FNV NPC `npc`'s packages that convert, in its order; `form_map` maps FNV forms. Each
        one left out is counted against the NPC: why, and how many of its packages it keeps."""
        out, lost = [], []
        total = len(listed(npc))
        for fnv in listed(npc):
            fid = self.package(fnv, form_map, int(npc['FormID'], 16))
            out += [fid] if fid else []
            lost += [] if fid else [fnv]
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
                self.made[fnv] = self._write(fnv, rec, plan, conditions, form_map)
        return self.made[fnv]

    def combat_list(self, npc: dict) -> int:
        """The FO4 Combat Override Package List (FLST) of FNV NPC `npc`'s packages held through combat (_write),
        after for_npc(npc); written once per NPC, 0 without any.
        See: docs/fork/fo4_pipeline.md#package-flags
        """
        held = [self.combat[fnv] for fnv in listed(npc) if fnv in self.combat]
        if not held:
            return 0
        key = int(npc['FormID'], 16)
        if key not in self.combat_lists:
            self.combat_lists[key] = fid = self.builder.writer.derive_formid(COMBAT_LIST_SITE, key)
            self.builder.writer.add_record('FLST', pack_flst(fid, f'FNV_{npc["EditorID"]}CombatOverrides', held))
            self.builder.counts['FLST (combat override packages)'] += 1
        return self.combat_lists[key]

    def _write(self, fnv: str, rec: dict, plan: tuple, conditions: bytes, form_map: dict) -> int:
        """Write FNV package `rec`'s copy by `plan` (_plan) with `conditions`; an FNV Guard kept through combat
        (CONTINUE_DURING_COMBAT) also gets a combat override copy, without fragments. The copy's FormID."""
        template, fid = plan[0], self.builder.fnv_id(fnv)
        values = {0: plan[2]} if len(plan) > 2 else self._values(rec, template)
        inputs = self._trigger(rec, form_map) if template == 'ForceGreet' else {}
        args = (self.vanilla[template], plan[1], conditions)
        self.builder.writer.add_record('PACK', pack_package(fid, rec, *args, self._fragments(rec), values, inputs))
        self.builder.counts[f'PACK {template}'] += 1
        if rec.get('PKDT.Type') == FNV_GUARD and fnv_flags(rec) & CONTINUE_DURING_COMBAT:
            self.combat[fnv] = held = self.builder.writer.derive_formid(COMBAT_SITE, int(fnv, 16))
            self.builder.writer.add_record('PACK', pack_package(held, {**rec, 'EditorID': rec['EditorID'] + 'Combat'},
                                                                *args, b'', values, inputs, COMBAT_OVERRIDE))
            self.builder.counts['PACK HoldPosition (combat override)'] += 1
        self.greets += [fid] if template == 'ForceGreet' else []
        topic = int(rec.get('PKDD.Topic', '0'), 16)
        self.topics.update({f'{topic:08X}': fid} if template == 'ForceGreet' and topic != GREETING else {})
        return fid

    def _values(self, rec: dict, template: str) -> dict:
        """{value slot: CNAM} of `rec`'s `template` copy: Sandbox Allows, FollowNPC radii."""
        return {'Sandbox': self._allows, 'FollowNPC': self._radii}.get(template, lambda _: {})(rec)

    def _allows(self, rec: dict) -> dict:
        """{value slot: Bool} of an FNV Sandbox or Wander `rec`'s copy: each FO4 Allow input from FNV's No flag.
        See: docs/fork/fo4_pipeline.md#sandbox-allows
        """
        if rec.get('PKDT.Type') not in SANDBOX_TYPES:
            return {}
        flags, slots = int(rec.get('PKDT.TypeFlags', 0) or 0), self.slots['Sandbox']
        return {slots[name]: bytes([not flags & bit]) for name, bit in ALLOWS.items() if name in slots}

    def _radii(self, rec: dict) -> dict:
        """{value slot: Float} of an FNV Follow or Accompany `rec`'s FollowNPC radii: its distance (PTDT count) as
        Min Radius, where the follower stops; Max Radius, where it runs, the vanilla one or that distance if farther.
        See: docs/fork/fo4_pipeline.md#follow-distance
        """
        distance, slots = int(rec.get('PTDT.Count', 0) or 0), self.slots['FollowNPC']
        if not distance:
            return {}
        cnams = [data for tag, data in subrecords(self.vanilla['FollowNPC']) if tag == b'CNAM']
        far = max(float(distance), struct.unpack('<f', cnams[slots['Max Radius']])[0])
        return {slots['Min Radius']: struct.pack('<f', distance), slots['Max Radius']: struct.pack('<f', far)}

    def _trigger(self, rec: dict, form_map: dict) -> dict:
        """{TRIGGER_INPUT: PLDT} of FNV Dialogue `rec`'s Trigger Location (PLD2), {} without one (the template's).
        A trigger box (XPRM) with radius 0 reaches its smaller half extent.
        See: docs/fork/fo4_pipeline.md#greet-trigger
        """
        place, ref = rec.get('PLD2.Type'), int(rec.get('PLD2.Location', '0') or '0', 16)
        if place not in SHARED_LOCATIONS or place in NAMED_LOCATIONS and ref not in form_map:
            return {}
        radius = int(rec.get('PLD2.Radius', 0) or 0) or round(self.boxes.get(ref, 0))
        return {TRIGGER_INPUT: struct.pack('<iIi', int(place), form_map.get(ref, 0), radius)}

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
        if kind == FNV_DIALOGUE and rec.get('PTDT.Target') != PLAYER_TARGET:
            return 'dialogue not with the player'
        template, first = PLANS[kind]
        if first == PLACE:
            bed = self._bed(rec, npc) if kind == FNV_SLEEP else None
            return ('Sleep', struct.pack('<iIi', NEAR_REFERENCE, form_map[bed], 0)) if bed in form_map \
                else self._at(rec, kind, template, form_map)
        if first == START:
            return self._start(rec, template, form_map)
        return self._aimed(rec, template, form_map) if first == TARGET else (template, b'')

    def _start(self, rec: dict, template: str, form_map: dict) -> tuple:
        """(template, PTDA payload) of a Patrol starting at FNV package `rec`'s location reference; the actor's
        linked reference (the template's) when it names none."""
        ref = int(rec.get('PLDT.Location', '0') or '0', 16)
        if rec.get('PLDT.Type') != NEAR_LOCATION or ref not in form_map:
            return template, b''
        return template, struct.pack('<iIi', TARGET_REFERENCE, form_map[ref], 0)

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
        if place == IN_CELL and (near := self._in_cell(ref, form_map)):
            return template, near
        return template, struct.pack('<iIi', int(place), form_map.get(ref, 0), int(rec.get('PLDT.Radius', 0)))

    def _in_cell(self, cell: int, form_map: dict) -> bytes:
        """PLDT near the built reference of FNV cell `cell` nearest its navmesh's middle (a persistent one when the
        cell has any), its radius reaching the navmesh's farthest vertex; b'' without navmesh or reference.
        See: docs/fork/fo4_pipeline.md#in-cell-places
        """
        verts = [v for rec in self.navmeshes.get(f'{cell:08X}', []) for v in parse_vertices(get_hex_bytes(rec, 'NVVX'))]
        refs = [r for r in self.cell_refs.get(f'{cell:08X}', []) if int(r['FormID'], 16) in form_map]
        refs = [r for r in refs if _persistent(r)] or refs
        if not verts or not refs:
            return b''
        middle = [(min(v[i] for v in verts) + max(v[i] for v in verts)) / 2 for i in range(3)]
        anchor = min(refs, key=lambda r: math.dist(_at_ref(r), middle))
        radius = math.ceil(max(math.dist(_at_ref(anchor), v) for v in verts))
        return struct.pack('<iIi', NEAR_REFERENCE, form_map[int(anchor['FormID'], 16)], radius)

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


def _persistent(ref: dict) -> bool:
    """True when FNV reference `ref` is written persistent (flagged, or a door)."""
    return bool(int(ref['RecordFlags']) & PERSISTENT) or 'XTEL.Door' in ref


def _at_ref(ref: dict) -> tuple:
    """FNV reference `ref`'s position."""
    return tuple(float(ref[f'Pos{k}']) for k in 'XYZ')


def beds(builder, refs: list) -> dict:
    """{FNV cell: [(bed reference, its XOWN owner or 0)]} of FNV furniture references `refs` that are beds, by
    FormID."""
    out = {}
    for ref in sorted(refs, key=lambda r: r['FormID']):
        if int(builder.bases[int(ref['NAME'], 16)][1].get('MNAM.Flags', 0)) & SLEEP_FURNITURE:
            out.setdefault(int(ref['ParentCELL'], 16), []).append(
                (int(ref['FormID'], 16), int(ref.get('XOWN.Owner', '0'), 16)))
    return out


def listed(npc: dict) -> list:
    """The FNV packages actor record `npc` lists, in its order."""
    return [npc[f'AIPackage[{i}]'] for i in range(int(npc.get('AIPackageCount', 0) or 0))]


def cowers(rec: dict) -> bool:
    """True for a Flee Not Combat with no location or target (it cowers)."""
    return rec.get('PKDT.Type') == FNV_FLEE and 'PLDT.Type' not in rec and 'PTDT.Type' not in rec


def fnv_flags(rec: dict) -> int:
    """`rec`'s general flags, Always Sneak added when an Ambush hides."""
    hides = rec.get('PKDT.Type') == FNV_AMBUSH and int(rec.get('PKDT.TypeFlags', 0) or 0) & HIDE_WHILE_AMBUSHING
    return int(rec.get('PKDT.Flags', 0) or 0) | (ALWAYS_SNEAK if hides else 0)


def schedule(rec: dict) -> bytes:
    """FO4 PSDT of FNV package `rec`'s schedule (MONTH_SHIFT, minutes)."""
    return struct.pack('<bbbbb3xi', int(rec.get('PSDT.Month', -1)) + MONTH_SHIFT, int(rec.get('PSDT.DayOfWeek', -1)),
                       int(rec.get('PSDT.Date', 0)), int(rec.get('PSDT.Time', -1)), ANY_MINUTE,
                       int(rec.get('PSDT.Duration', 0)) * 60)


def _pkdt(rec: dict, vanilla: bytes, override: int) -> bytes:
    """The vanilla PKDT with FNV package `rec`'s general flags the games share, interrupt override `override`, FNV's
    Always Run as FO4's preferred speed Run, and its own behavior flags (OWN_BEHAVIOR) as FO4's interrupt flags.
    See: docs/fork/fo4_pipeline.md#package-flags
    """
    flags = fnv_flags(rec)
    run = flags & ALWAYS_RUN
    speed = bytes([RUN]) if run else vanilla[SPEED:SPEED + 1]
    interrupt = struct.unpack_from('<H', vanilla, INTERRUPT_FLAGS)[0]
    if flags & OWN_BEHAVIOR:
        interrupt = interrupt & ~SHARED_BEHAVIOR | int(rec.get('PKDT.BehaviorFlags', 0) or 0) & SHARED_BEHAVIOR
    return (struct.pack('<I', flags & SHARED_FLAGS | run) + vanilla[4:INTERRUPT_OVERRIDE] + bytes([override]) + speed
            + vanilla[SPEED + 1:INTERRUPT_FLAGS] + struct.pack('<H', interrupt) + vanilla[INTERRUPT_FLAGS + 2:])


def value_slots(instance: bytes, packs: dict) -> dict:
    """{template data name: value slot (CNAM ordinal)} of vanilla package `instance`, its template in `packs`."""
    subs, names, last = list(subrecords(instance)), {}, None
    for tag, data in subrecords(packs[struct.unpack_from('<I', dict(subs)[b'PKCU'], 4)[0]]):
        last = data[0] if tag == b'UNAM' else last
        names.update({last: data[:-1].decode()} if tag == b'BNAM' and last is not None else {})
    order, slots, inputs, slot = [data[0] for tag, data in subs if tag == b'UNAM'], {}, -1, 0
    for tag, _ in subs:
        inputs += tag == b'ANAM'
        if tag == b'CNAM':
            slots[names.get(order[inputs]) if inputs < len(order) else None] = slot
            slot += 1
    return slots


def pack_package(fid: int, rec: dict, vanilla: bytes, first_input: bytes, conditions: bytes,
                 vmad: bytes = b'', values: 'dict | None' = None, inputs: 'dict | None' = None,
                 override: int = NO_OVERRIDE) -> bytes:
    """A copy of vanilla instance `vanilla` for FNV package `rec`: its EditorID, `vmad` (its fragments), schedule
    and conditions after PSDT, the first PLDT/PTDA from `first_input`, later ones from `inputs` (by ordinal;
    vanilla bytes past each kept), CNAMs (by slot) from `values`, PKDT flags the games share (_pkdt) and interrupt
    override `override`: none for an NPC's package list, where a combat override hangs the load.
    See: docs/fork/fo4_pipeline.md#packages
    """
    fields, out = {b'EDID': f'FNV_{rec["EditorID"]}'.encode() + b'\0', b'PSDT': schedule(rec)}, b''
    values, slot, inputs, ordinal = values or {}, 0, {**(inputs or {}), 0: first_input}, 0
    for tag, data in subrecords(vanilla):
        if tag == b'PKDT':
            data = _pkdt(rec, data, override)
        elif tag in (b'PLDT', b'PTDA'):
            payload, ordinal = inputs.get(ordinal, b''), ordinal + 1
            data = payload + data[len(payload):]
        elif tag == b'CNAM':
            data, slot = values.get(slot, data), slot + 1
        if tag not in DROPPED:
            out += pack_subrecord(tag.decode(), fields.get(tag, data)) + {b'PSDT': conditions, b'EDID': vmad}.get(tag, b'')
    return pack_fo4_record('PACK', fid, 0, out)
