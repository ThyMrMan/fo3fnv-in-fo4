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
from fo4_import.spike.condition_forms import condition_items
from fo4_import.spike.dialogue import GREETING
from fo4_import.spike.greet_once import GreetOnce
from fo4_import.spike.say_topics import blocker, conditions_of
from fo4_import.spike.readiness import PACKAGE_LEFT_OUT
from fo4_import.spike.records import pack_flst
from fo4_import.spike.script import PACKAGE, QUEST, declared_properties, prefix
from script_convert.constants import FALLOUT4_ACTOR_VALUE_IDS, FALLOUT4_CHAT_PREFIX
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.packages.scripts_falloutnv import package_flags
from tes5_import.base.writer import pack_subrecord
from tes5_import.base.text_reader import get_hex_bytes
from tes5_import.record_types.navm_falloutnv import parse_vertices

#: Vanilla instances copied per template, inputs in its order at its defaults; their conditions give way to FNV's.
INSTANCES = {'Travel': 0x248982, 'Sit': 0x2471DB, 'Sandbox': 0x24674E, 'ForceGreet': 0x1BEAD3, 'Sleep': 0x1B9EB0,
             'Eat': 0x1AE26C, 'HoldPosition': 0x2491F8, 'Patrol': 0x248492, 'FollowNPC': 0x232257,
             'FleeTo': 0x204C1D, 'FleeFrom': 0x1D4388, 'UseWeapon': 0x19632E, 'EscortPlayer': 0x112EED}
#: A copy's first input from FNV: its location, its target, its location as a Patrol start, or the template's.
PLACE, TARGET, START, KEEP = 'place', 'target', 'start', 'keep'
#: FNV PKDT type: (FO4 template, first input). Wander sandboxes; Guard holds its position; Patrol walks linked refs.
PLANS = {'1': ('FollowNPC', TARGET), '7': ('FollowNPC', TARGET), '3': ('Eat', PLACE), '4': ('Sleep', PLACE), '5': ('Sandbox', PLACE),
         '6': ('Travel', PLACE), '8': ('Sit', TARGET), '12': ('Sandbox', PLACE), '13': ('Patrol', START),
         '14': ('HoldPosition', PLACE), '15': ('ForceGreet', PLACE)}
FNV_SLEEP, FNV_TRAVEL, FNV_DIALOGUE, FNV_FLEE, FNV_AMBUSH, FNV_GUARD = '4', '6', '15', '10', '9', '14'
#: FNV PKDT type Escort: lead its target (PTDT) to its location; FO4 EscortPlayer's Target to Escort input.
FNV_ESCORT, ESCORTED_INPUT = '2', 1
#: FNV PKDT type Use Weapon: weapon in PTDT, target in PTD2, firing in PKW3; FO4's UseWeapon inputs 1 and 2.
FNV_USE_WEAPON, WEAPON_INPUT, SHOT_INPUT = '16', 1, 2
#: PTDA target types naming an object by form or by type (the same codes in both games).
TARGET_OBJECT, TARGET_TYPE = 1, 2
#: FNV object type codes for weapons (any, ranged, melee, none) as FO4's (xEdit wbObjectTypeEnum of each game).
WEAPON_TYPES = {'12': 11, '21': 20, '22': 19, '23': 18}
#: FO4 UseWeapon Bool inputs and the FNV PKW3 flag each copies.
WEAPON_FLAGS = {'Always Hit?': 0x1, 'Do No Damage?': 0x100, 'Crouch Reload?': 0x10000,
                'Hold When Blocked?': 0x1000000}
#: FNV Ambush type flag Hide While Ambushing (xEdit wbDefinitionsFNV), and the general flag both games call Always Sneak.
HIDE_WHILE_AMBUSHING, ALWAYS_SNEAK = 0x1, 0x20000
#: FO4 PLDT location type near the package's start location (FNV's near current location, the same code).
NEAR_START = 2
#: Fragments of a flee with no location or target: Cowardly while it runs (fo4_pipeline.md#packages).
COWER_SCRIPT = 'F3NV_CowerPackage'
#: Its fragment flags: OnBegin and OnEnd.
COWER_FRAGMENTS = 0x01 | 0x02
#: Fragments of a Dialogue package aimed at an NPC: its arrival plays the topic's chat scene; and their flags.
DIALOGUE_SCRIPT, DIALOGUE_FRAGMENTS = 'F3NV_DialoguePackage', 0x01 | 0x02
#: FNV PLDT location type "in cell", and FO4's near reference.
IN_CELL, NEAR_REFERENCE = '1', 0
#: Record flag Persistent; an FO4 package's place stays loaded only on a persistent reference.
PERSISTENT = 0x400
#: FNV package types whose copy is a Sandbox with FNV's own No flags: Wander, Sandbox.
SANDBOX_TYPES = ('5', '12')
#: FO4 Sandbox Allow inputs and the FNV type-specific No flag each negates (No Furniture covers both seats).
ALLOWS = {'Allow Eating': 0x1, 'Allow Sleeping': 0x2, 'Allow Conversation': 0x4, 'Allow Idle Markers': 0x8,
          'Allow Sitting': 0x10, 'Allow Special Furniture': 0x10, 'Allow Wandering': 0x20}
#: FNV PLDT location types near a reference and near the actor's linked reference, as the export writes them.
NEAR_LOCATION, NEAR_LINKED = '0', '6'
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
#: ForceGreet's Forcegreet Distance (the NPC must get within it to greet): its third location input.
GREET_INPUT = 2
#: FO4 PLDT location type Near Self (xEdit), and FNV's loaded area: uGridsToLoad 5, two 4,096-unit cells each side.
NEAR_SELF, FNV_LOADED_REACH = 12, 8192
#: FNV's standard Activate Distance, iActivatePickLength (GECK Dialogue Package), where PTDT's count is 0.
ACTIVATE_DISTANCE = 150
#: The farthest a force greeter stops: 122 of vanilla's 217 use 225, inside fAIInDialogueModeWithPlayerDistance 250.
TALK_REACH = 225
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

    def __init__(self, builder, export_dir, furniture: set, cell_beds: dict, refs: list, helper_index: int):
        """Index FNV packages and read the vanilla instances; `furniture` holds the FNV references that are seats,
        `cell_beds` each cell's beds (beds()), `refs` the build's references (in-cell places, _in_cell),
        `helper_index` the helper plugin's master index (GreetOnce)."""
        self.builder, self.furniture, self.beds, self.made = builder, furniture, cell_beds, {}
        self.once = GreetOnce(builder, helper_index)
        self.greets = self.once.greets
        self.topics, self.cell_refs, self.navmeshes, self.combat, self.combat_lists = {}, {}, {}, {}, {}
        for ref in refs:
            self.cell_refs.setdefault(ref.get('ParentCELL'), []).append(ref)
        self.boxes = {int(r['FormID'], 16): min(float(r['XPRM.BoundX']), float(r['XPRM.BoundY'])) for r in refs
                      if 'XPRM.BoundX' in r}
        for rec in export_records(export_dir, 'NAVM'):
            self.navmeshes.setdefault(rec.get('DATA.Cell'), []).append(rec)
        self.why, self.pending, self.scripted = {}, set(), set()
        self.packs = {r['FormID']: r for r in export_records(export_dir, 'PACK')}
        self.topic_names = {r['FormID'].upper(): r.get('EditorID') for r in export_records(export_dir, 'DIAL')}
        self.by_name = {r['EditorID'].lower(): fid for fid, r in self.packs.items() if r.get('EditorID')}
        self.links = linked_by_package(export_dir)
        packs ={r.form_id: r.body for r, _ in walk(builder.fo4, b'PACK')}
        self.vanilla = {name: packs[fid] for name, fid in INSTANCES.items()}
        self.slots = {name: value_slots(self.vanilla[name], packs)
                      for name in ('Sandbox', 'FollowNPC', 'UseWeapon', 'EscortPlayer')}

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

    def named_by_quests(self, scripts, quests: list) -> None:
        """Make now the Dialogue packages the scripts and stage fragments of FNV `quests` name, whose properties
        fill with the quest record, after the greeting takes the force greets' topics (self.topics).
        See: docs/fork/fo4_pipeline.md#greeting-scene
        """
        names = [scripts.name(int(q['SCRI'], 16)) for q in quests if q.get('SCRI')]
        names += [f'{prefix(QUEST)}{q["EditorID"]}' for q in quests]
        for path in (scripts.dir / f'{n}.psc' for n in names if n and scripts.dir):
            props = declared_properties(path.read_text(encoding='utf-8')) if path.exists() else []
            for prop in (p for _, p in props if self.packs.get(self.by_name.get(p.lower()), {}).get('PKDT.Type')
                         == FNV_DIALOGUE):
                self.named(prop)

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
            out += [fid, self.once.parked[fnv]] if fnv in self.once.parked else [fid] if fid else []
            lost += [] if fid else [fnv]
        for fnv in lost:
            detail = f'{self.packs[fnv].get("EditorID")} ({self.why[fnv]}; keeps {len(out)} of {total})'
            self.builder.counts[f'package left out for {npc.get("EditorID")}: {detail}'] += 1
            self.builder.readiness.add(PACKAGE_LEFT_OUT, npc['FormID'], detail)
        return out

    def package(self, fnv: str, form_map: dict, npc: int = 0) -> int:
        """The FO4 package for FNV package `fnv` (made once, for the first NPC `npc` that runs it), 0 when it
        does not convert, then counted and recorded in the readiness report by why. Items its conditions test
        are made and added to `form_map`. Its id is taken before it is written, so a fragment script naming it
        (or a package naming it back) resolves to it instead of writing it again."""
        if fnv not in self.made:
            rec = self.packs[fnv]
            plan = self._plan(rec, form_map, npc)
            form_map.update({} if isinstance(plan, str) else condition_items(self.builder, [rec], form_map))
            conditions = conditions_of(rec, form_map, self.builder.script_vars)
            if isinstance(plan, str) or conditions is None:
                why = plan if isinstance(plan, str) else f'condition {blocker(rec, form_map, self.builder.script_vars)}'
                self.builder.counts[f'package left out ({why})'] += 1
                self.builder.readiness.add(PACKAGE_LEFT_OUT, fnv, f'{rec.get("EditorID", fnv)} ({why})')
                self.made[fnv], self.why[fnv] = 0, why
            else:
                self.made[fnv] = self.builder.fnv_id(fnv)
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
        (CONTINUE_DURING_COMBAT) also gets a combat override copy, without fragments; a ForceGreet is numbered and
        parked (GreetOnce). The copy's FormID."""
        template, fid = plan[0], self.builder.fnv_id(fnv)
        number = self.once.number(fid) if template == 'ForceGreet' else 0
        values = {0: plan[2]} if len(plan) > 2 else self._values(rec, template)
        inputs = {'ForceGreet': self._trigger, 'UseWeapon': self._weapon, 'EscortPlayer': self._escorted}.get(
            template, lambda *_: {})(rec, form_map)
        args = (self.vanilla[template], plan[1], conditions + (self.once.unspoken(number) if number else b''))
        self.builder.writer.add_record('PACK', pack_package(fid, rec, *args, self._fragments(rec, form_map), values,
                                                            inputs))
        self.builder.counts[f'PACK {template}'] += 1
        if rec.get('PKDT.Type') == FNV_GUARD and fnv_flags(rec) & CONTINUE_DURING_COMBAT:
            self.combat[fnv] = held = self.builder.writer.derive_formid(COMBAT_SITE, int(fnv, 16))
            self.builder.writer.add_record('PACK', pack_package(held, {**rec, 'EditorID': rec['EditorID'] + 'Combat'},
                                                                *args, b'', values, inputs, COMBAT_OVERRIDE))
            self.builder.counts['PACK HoldPosition (combat override)'] += 1
        if number:
            self._park(fnv, rec, number, conditions)
        topic = int(rec.get('PKDD.Topic', '0'), 16)
        self.topics.update({f'{topic:08X}': fid} if template == 'ForceGreet' and topic != GREETING else {})
        return fid

    def _park(self, fnv: str, rec: dict, number: int, conditions: bytes) -> None:
        """Write ForceGreet `number`'s parked copy (GreetOnce.park): FNV package `rec`'s schedule and `conditions`."""
        def copy(fid, suffix, template, first, extra, vmad):
            """Write copy `fid` of vanilla `template`, from `first`, with `extra` conditions."""
            self.builder.writer.add_record('PACK', pack_package(fid, {**rec, 'EditorID': rec['EditorID'] + suffix},
                                                                self.vanilla[template], first, conditions + extra, vmad))
        self.once.park(fnv, number, copy)

    def _values(self, rec: dict, template: str) -> dict:
        """{value slot: CNAM} of `rec`'s `template` copy (Allows, radii, firing)."""
        return {'Sandbox': self._allows, 'FollowNPC': self._radii, 'UseWeapon': self._firing,
                'EscortPlayer': self._escort_wait}.get(template, lambda _: {})(rec)

    def _firing(self, rec: dict) -> dict:
        """{value slot: CNAM} of FNV Use Weapon `rec`'s firing (PKW3): its flags, volley fire, the pause between
        volleys, how many (Repeat Fire: 0, without end) and the shots in each.
        See: docs/fork/fo4_pipeline.md#use-weapon
        """
        slots, flags = self.slots['UseWeapon'], int(rec.get('PKW3.Flags', 0) or 0)
        repeat = rec.get('PKW3.FireCount') == '1'
        values = {name: bytes([bool(flags & bit)]) for name, bit in WEAPON_FLAGS.items()}
        values.update({'Volley Fire?': bytes([rec.get('PKW3.FireRate') == '1']),
                       'Volley Wait Min': struct.pack('<f', float(rec.get('PKW3.PauseMin', 0) or 0)),
                       'Volley Wait Max': struct.pack('<f', float(rec.get('PKW3.PauseMax', 0) or 0)),
                       'Volleys To Fire': struct.pack('<i', 0 if repeat else int(rec.get('PKW3.Bursts', 0) or 0)),
                       'Volley Shots Min': struct.pack('<i', int(rec.get('PKW3.ShotsMin', 0) or 0)),
                       'Volley Shots Max': struct.pack('<i', int(rec.get('PKW3.ShotsMax', 0) or 0))})
        return {slots[name]: value for name, value in values.items() if name in slots}

    def _weapon(self, rec: dict, form_map: dict) -> dict:
        """{input: PTDA} of FNV Use Weapon `rec`: the weapon by form or type (unconverted: the template's ranged
        weapon) and the reference or linked reference it shoots at (_plan checked it is built)."""
        kind, weapon = rec.get('PTDT.Type'), int(rec.get('PTDT.Target', '0') or '0', 16)
        fo4 = self.builder.items.item(weapon) if kind == str(TARGET_OBJECT) else None
        out = {WEAPON_INPUT: struct.pack('<iIi', TARGET_OBJECT, fo4, 0)} if fo4 else {}
        if kind == str(TARGET_TYPE) and rec['PTDT.Target'].lstrip('0') in WEAPON_TYPES:
            out[WEAPON_INPUT] = struct.pack('<iIi', TARGET_TYPE, WEAPON_TYPES[rec['PTDT.Target'].lstrip('0')], 0)
        shot = int(rec.get('PTD2.Target', '0') or '0', 16)
        out[SHOT_INPUT] = struct.pack('<iIi', int(rec['PTD2.Type']), form_map.get(shot, 0), 0)
        return out

    def _escorted(self, rec: dict, form_map: dict) -> dict:
        """{input: PTDA} of FNV Escort `rec`'s Target to Escort, its built target."""
        return {ESCORTED_INPUT: struct.pack('<iIi', TARGET_REFERENCE, form_map[int(rec['PTDT.Target'], 16)], 0)}

    def _escort_wait(self, rec: dict) -> dict:
        """{value slot: Float} of FNV Escort `rec`'s distance (PTDT count) as FO4's Distance to Wait for Followers;
        none at 0, where the template's stays.
        See: docs/fork/fo4_pipeline.md#escort
        """
        distance = int(rec.get('PTDT.Count', 0) or 0)
        slot = self.slots['EscortPlayer']['Distance to Wait for Followers']
        return {slot: struct.pack('<f', distance)} if distance else {}

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
        """{location input: PLDT} of FNV Dialogue `rec`'s ForceGreet copy: its Trigger Location (PLD2), else near the
        actor within FNV's loaded area (FNV_LOADED_REACH), and its Forcegreet Distance, near the player within FNV's
        Activate Distance (PTDT count, else ACTIVATE_DISTANCE) but no farther than TALK_REACH, as FO4 talks only
        within its dialogue range. A PLD2 that does not convert keeps the template's
        trigger. A trigger box (XPRM) with radius 0 reaches its smaller half extent.
        See: docs/fork/fo4_pipeline.md#greet-trigger
        """
        reach = min(int(rec.get('PTDT.Count', 0) or 0) or ACTIVATE_DISTANCE, TALK_REACH)
        greet = {GREET_INPUT: struct.pack('<iIi', NEAR_REFERENCE, int(PLAYER_TARGET, 16), reach)}
        place, ref = rec.get('PLD2.Type'), int(rec.get('PLD2.Location', '0') or '0', 16)
        if place is None:
            return {TRIGGER_INPUT: struct.pack('<iIi', NEAR_SELF, 0, FNV_LOADED_REACH), **greet}
        if place not in SHARED_LOCATIONS or place in NAMED_LOCATIONS and ref not in form_map:
            return greet
        radius = int(rec.get('PLD2.Radius', 0) or 0) or round(self.boxes.get(ref, 0))
        return {TRIGGER_INPUT: struct.pack('<iIi', int(place), form_map.get(ref, 0), radius), **greet}

    def _fragments(self, rec: dict, form_map: dict) -> bytes:
        """VMAD binding FNV package `rec`'s converted PF_ script, filled; a cower's (cowers()) COWER_SCRIPT; a
        Dialogue with an NPC's DIALOGUE_SCRIPT, its topic's chat scene and target; b'' without any."""
        flags, name, scripts = package_flags(rec), prefix(PACKAGE) + rec['FormID'].upper(), self.builder.scripts
        if cowers(rec) and not flags:
            self.builder.counts['cower package'] += 1
            return pack_subrecord('VMAD', package_fragments(COWER_SCRIPT, COWER_FRAGMENTS,
                                                            {'Confidence': FALLOUT4_ACTOR_VALUE_IDS['Confidence']}))
        if talks_to_npc(rec) and not flags:
            self.builder.counts['dialogue package with an NPC'] += 1
            chat = scripts.talk(FALLOUT4_CHAT_PREFIX + self.topic_names[rec['PKDD.Topic'].upper()])
            target = form_map[int(rec['PTDT.Target'], 16)]
            return pack_subrecord('VMAD', package_fragments(DIALOGUE_SCRIPT, DIALOGUE_FRAGMENTS,
                                                            {'Chat': chat, 'Target': target}))
        if not flags or not scripts.dir or not (scripts.dir / f'{name}.psc').exists():
            return b''
        scripts.used.append(name)
        self.builder.counts['package fragments'] += 1
        return pack_subrecord('VMAD', package_fragments(name, flags, scripts.properties(name)))

    def _plan(self, rec: dict, form_map: dict, npc: int) -> 'tuple | str':
        """(template, first input payload[, second input payload]) for FNV package `rec` run by NPC `npc`; why it
        does not convert otherwise. A Travel to the linked reference sits in it when every placed actor running
        it links to a seat (self.links).
        See: docs/fork/fo4_pipeline.md#packages
        """
        kind = rec.get('PKDT.Type')
        if kind == FNV_FLEE:
            return self._flee(rec, form_map)
        if kind == FNV_AMBUSH:
            template = 'HoldPosition' if not int(rec.get('PLDT.Radius', 0) or 0) else 'Sandbox'
            return self._at(rec, kind, template, form_map)
        if kind == FNV_USE_WEAPON:
            return self._use_weapon(rec, form_map)
        if kind == FNV_ESCORT:
            return self._escort(rec, form_map)
        if kind not in PLANS:
            return f'type {FNV_TYPES.get(kind, kind)}'
        if talks_to_npc(rec):
            return self._talk_to(rec, form_map)
        template, first = PLANS[kind]
        if first == PLACE:
            bed = self._bed(rec, npc) if kind == FNV_SLEEP else None
            if bed in form_map:
                return 'Sleep', struct.pack('<iIi', NEAR_REFERENCE, form_map[bed], 0)
            return ('Sit', struct.pack('<iIi', TARGET_LINKED, 0, 0)) if kind == FNV_TRAVEL and rec.get('PLDT.Type') == NEAR_LINKED \
                and self.links.get(rec['FormID'], {0}) <= self.furniture else self._at(rec, kind, template, form_map)
        if first == START:
            return self._start(rec, template, form_map)
        return self._aimed(rec, template, form_map) if first == TARGET else (template, b'')

    def _use_weapon(self, rec: dict, form_map: dict) -> 'tuple | str':
        """(UseWeapon, PLDT payload) at FNV Use Weapon `rec`'s location, shooting at its built target reference
        or linked reference (_weapon); why not, otherwise.
        See: docs/fork/fo4_pipeline.md#use-weapon
        """
        shot = int(rec.get('PTD2.Target', '0') or '0', 16)
        if rec.get('PTD2.Type') not in (str(TARGET_REFERENCE), str(TARGET_LINKED)):
            return 'no weapon target'
        if rec['PTD2.Type'] == str(TARGET_REFERENCE) and shot not in form_map:
            return 'weapon target not built'
        return self._at(rec, FNV_USE_WEAPON, 'UseWeapon', form_map)

    def _escort(self, rec: dict, form_map: dict) -> 'tuple | str':
        """(EscortPlayer, PLDT payload) leading FNV Escort `rec`'s built target reference to its location; why not,
        otherwise.
        See: docs/fork/fo4_pipeline.md#escort
        """
        if rec.get('PTDT.Type') != str(TARGET_REFERENCE) or int(rec.get('PTDT.Target', '0') or '0', 16) not in form_map:
            return 'escort target not built'
        return self._at(rec, FNV_ESCORT, 'EscortPlayer', form_map)

    def _talk_to(self, rec: dict, form_map: dict) -> 'tuple | str':
        """(Travel, PLDT payload) near the reference FNV Dialogue `rec` talks to, within its distance (PTDT count;
        0 keeps the template's radius); its arrival plays the topic (_fragments). Why not, otherwise.
        See: docs/fork/fo4_pipeline.md#packages
        """
        ref, distance = int(rec.get('PTDT.Target', '0') or '0', 16), int(rec.get('PTDT.Count', 0) or 0)
        if rec.get('PTDT.Type') != str(TARGET_REFERENCE) or ref not in form_map:
            return 'dialogue target not built'
        if not self.topic_names.get(rec.get('PKDD.Topic', '').upper()):
            return 'dialogue topic not named'
        near = struct.pack('<iI', NEAR_REFERENCE, form_map[ref])
        return 'Travel', near + (struct.pack('<i', distance) if distance else b'')

    def _start(self, rec: dict, template: str, form_map: dict) -> tuple:
        """(template, PTDA payload) of a Patrol starting at FNV package `rec`'s location reference; the actor's
        linked reference (the template's) when it names none."""
        ref = int(rec.get('PLDT.Location', '0') or '0', 16)
        if rec.get('PLDT.Type') != NEAR_LOCATION or ref not in form_map:
            return template, b''
        return template, struct.pack('<iIi', TARGET_REFERENCE, form_map[ref], 0)

    def _at(self, rec: dict, kind: str, template: str, form_map: dict) -> 'tuple | str':
        """(template, PLDT payload) at FNV package `rec`'s location (none: where it starts, as FNV runs it, but a
        Dialogue's waits where the actor is, as FNV sends it for its target at once); a Travel to a seat sits in it.
        See: docs/fork/fo4_pipeline.md#greet-wait
        """
        if kind == FNV_DIALOGUE and 'PLDT.Type' not in rec:
            return template, struct.pack('<iIi', NEAR_SELF, 0, 0)
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


def linked_by_package(export_dir) -> dict:
    """{FNV package: the linked references (0: none) of every placed actor whose base lists it}."""
    bases = {r['FormID']: listed(r) for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}
    out = {}
    for actor in (r for sig in ('ACHR', 'ACRE') for r in export_records(export_dir, sig)):
        for pack in bases.get(actor['NAME'], ()):
            out.setdefault(pack, set()).add(int(actor.get('XLKR.LinkedRef', '0') or '0', 16))
    return out


def listed(npc: dict) -> list:
    """The FNV packages actor record `npc` lists, in its order."""
    return [npc[f'AIPackage[{i}]'] for i in range(int(npc.get('AIPackageCount', 0) or 0))]


def talks_to_npc(rec: dict) -> bool:
    """True for a Dialogue package aimed at a reference other than the player."""
    return rec.get('PKDT.Type') == FNV_DIALOGUE and rec.get('PTDT.Target') != PLAYER_TARGET


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
