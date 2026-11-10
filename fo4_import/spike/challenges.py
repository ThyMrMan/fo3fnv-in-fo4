"""FNV challenges (CHAL) on Fallout 4: counted by F3NV_Challenges, rewarded, and shown on the Pip-Boy's CHALLENGES tab.

FNV's engine counts a challenge by its type (DATA.Type) and the type's
values: kills with a weapon skill (Value2, an actor value), weapon type
(Value3, FNV animation type + 1) or weapon list (XNAM), kills of a creature
type (Value2, type + 1) or of one actor (SNAM), critical hits, uses of an
item (SNAM, an item or list), a discovered map marker (SNAM) or a misc stat
(Value1, an index into FNV_STATS). Each becomes one event F3NV_Challenges
hears: the player's kills, uses and crippled limbs (its player alias),
FO4's tracked stats, or another challenge completing. The types FO4 has no
event for are left out, counted (LEFT_OUT, and misc stats FO4 lacks).

A challenge kept is an actor value on the player holding its progress (on
the CHAL's FormID, named and described as FNV's: the tab's row) and a state
global (FNV_<EditorID>: the tab's shown global, and what converted scripts'
UnlockChallenge / RemoveRecurringFromChallenge name). Its reward is its
script (SCRI, an effect script) cast on the player as a spell, one per script.

See: docs/fork/fo4_pipeline.md#challenges
"""


from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_avif, pack_global, pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.pipboy_tabs import tab_quest
from tes5_import.base.tes5_reader import first_sub, walk

#: derive_formid site of this module's records (key: the challenge's EditorID and what the record is).
SITE = 'FNV challenge'
#: The counting quest's script and its player alias's.
SCRIPT, PLAYER_SCRIPT = 'F3NV_Challenges', 'F3NV_ChallengesPlayer'
#: Each plugin's challenges (the game's on its counting quest, a DLC's on a quest of its own); see Challenges.write.
SOURCE_SCRIPT = 'F3NV_ChallengeSource'
#: The player reference (alias forced to it).
PLAYER = 0x14
#: The events F3NV_Challenges counts (its Events property).
KILL, STAT, USE, MARKER, CRIPPLED, COMPLETED = range(6)
#: FNV CHAL types (xEdit wbDefinitionsFNV, JIP TESChallenge).
KILL_LIST, KILL_FORM, KILL_TYPE, HIT, DISCOVER, USE_ITEM = range(6)
USE_LIST, MISC_STAT = 9, 11
#: The types left out: Fallout 4 has no event for them.
LEFT_OUT = {6: 'acquire an item', 7: 'use a skill', 8: 'do damage', 10: 'acquire an item from a list',
            12: 'craft using an item', 13: 'scripted'}
#: A hit challenge's Value2 kinds: damage, critical, knockdown, cripple; only critical (any body part) is counted.
HIT_KINDS, CRITICAL = ('damage', 'critical', 'knockdown', 'cripple'), 1
#: FNV's misc stats by index (FalloutNV.exe's table).
FNV_STATS = ('Quests Completed', 'Locations Discovered', 'People Killed', 'Creatures Killed', 'Locks Picked',
             'Computers Hacked', 'Stimpaks Taken', 'Rad-X Taken', 'RadAway Taken', 'Chems Taken', 'Times Addicted',
             'Mines Disarmed', 'Speech Successes', 'Pockets Picked', 'Pants Exploded', 'Books Read',
             'Health From Stimpaks', 'Weapons Created', 'Health From Food', 'Water Consumed', 'Sandman Kills',
             'Paralyzing Punches', 'Robots Disabled', 'Times Slept', 'Corpses Eaten', 'Mysterious Stranger Visits',
             'Doctor Bags Used', 'Challenges Completed', 'Miss Fortunate Occurrences', 'Disintegrations',
             'Have Limbs Crippled', 'Speech Failures', 'Items Crafted', 'Weapon Modifications', 'Items Repaired',
             'Total Things Killed', 'Dismembered Limbs', 'Caravan Games Won', 'Caravan Games Lost',
             'Barter Amount Traded', 'Roulette Games Played', 'Blackjack Games Played', 'Slots Games Played')
#: FNV stats FO4 tracks under the same name.
SAME_STATS = ('Quests Completed', 'Locations Discovered', 'People Killed', 'Creatures Killed', 'Locks Picked',
              'Computers Hacked', 'Stimpaks Taken', 'Rad-X Taken', 'RadAway Taken', 'Chems Taken', 'Times Addicted',
              'Mines Disarmed', 'Speech Successes', 'Pockets Picked', 'Pants Exploded', 'Sandman Kills',
              'Paralyzing Punches', 'Robots Disabled', 'Corpses Eaten', 'Mysterious Stranger Visits')
#: FNV stat -> the FO4 tracked stats counting it.
FO4_STATS = {**{name: (name,) for name in SAME_STATS}, 'Books Read': ('Skill Books Read',),
             'Items Crafted': ('Chems Crafted', 'Food Cooked'), 'Weapon Modifications': ('Weapons Improved',)}
#: FNV stats counted by an event instead.
STAT_EVENTS = {'Total Things Killed': KILL, 'Have Limbs Crippled': CRIPPLED, 'Challenges Completed': COMPLETED}
#: The FO4 stat a critical hit raises, and the one a map marker's discovery does.
CRITICALS, DISCOVERIES = ('Critical Strikes',), ('Locations Discovered',)
#: Every stat group a challenge can count, in one fixed order: the group numbers every plugin's rows share.
STAT_GROUPS = tuple(sorted({*FO4_STATS.values(), CRITICALS, DISCOVERIES}))
#: CHAL DATA.Flags.
START_DISABLED, RECURRING, SHOW_ZERO = 1, 2, 4
#: FNV's Unarmed skill (actor value) and the hand-to-hand weapon type (Value3: animation type 0 + 1).
UNARMED, HAND_TO_HAND = 45, 1
#: Fallout4.esm's player fists: the weapon an unarmed player holds.
FISTS = 'UnarmedHuman'
#: FNV's engine strings for a completed challenge and progress (FalloutNV.exe sChallengeComplete, sChallengeProgress).
COMPLETE_TEXT, PROGRESS_TEXT = 'Challenge Completed', 'Challenge Progress'
#: F3NV_Challenges' Int[] properties; its other per-challenge properties are form arrays.
INT_COLUMNS = ('Events', 'Thresholds', 'Intervals', 'Recurring', 'Groups')
FORM_COLUMNS = ('Weapons', 'Victims', 'Items', 'Markers', 'Rewards')


def _int(rec: dict, key: str) -> int:
    """Export integer `key` of `rec`; 0 when absent."""
    return int(rec.get(key) or 0)


def _hex(rec: dict, key: str) -> int:
    """Export FormID `key` of `rec`; 0 when absent."""
    return int(rec.get(key) or '0', 16)


def counting(rec: dict) -> 'tuple | str':
    """(event, FO4 stats) counting FNV challenge `rec`, or why it is left out."""
    kind, value1, value2 = (_int(rec, f'DATA.{k}') for k in ('Type', 'Value1', 'Value2'))
    if kind in (KILL_LIST, KILL_FORM, KILL_TYPE):
        return KILL, ()
    if kind == HIT:
        return (STAT, CRITICALS) if value2 == CRITICAL and not value1 else \
            f'hit ({HIT_KINDS[value2] if value2 < len(HIT_KINDS) else value2}{", body part" if value1 else ""})'
    if kind in (USE_ITEM, USE_LIST):
        return USE, ()
    if kind == DISCOVER:
        return MARKER, DISCOVERIES
    if kind == MISC_STAT:
        name = FNV_STATS[value1] if value1 < len(FNV_STATS) else str(value1)
        return (STAT_EVENTS[name], ()) if name in STAT_EVENTS else (STAT, FO4_STATS[name]) if name in FO4_STATS \
            else f'misc stat {name}'
    return LEFT_OUT.get(kind, f'type {kind}')


def creature_types(export_dir: Path) -> dict:
    """{FNV creature FormID: its creature type}, a template's when the creature uses its traits (ACBS bit 0)."""
    recs = {int(r['FormID'], 16): r for r in export_records(export_dir, 'CREA')}

    def of(fid: int, seen: tuple = ()) -> int:
        """Creature `fid`'s type, following Use Traits templates."""
        rec, template = recs[fid], _hex(recs[fid], 'TPLT.Template')
        if _int(rec, 'ACBS.TemplateFlags') & 1 and template in recs and template not in seen:
            return of(template, seen + (fid,))
        return _int(rec, 'DATA.CreatureType')
    return {fid: of(fid) for fid in recs}


def form_list(builder, key: str, edid: str, forms: list) -> int:
    """Write FLST `edid` of `forms` (FormID hashed at SITE from `key`); its FormID."""
    fid = builder.writer.derive_formid(SITE, key)
    builder.writer.add_record('FLST', R.pack_flst(fid, edid, forms))
    return fid


def fo4_weapon(fo4: bytes, edid: str) -> int:
    """The FormID of Fallout4.esm's weapon `edid`."""
    return next(r.form_id for r, _ in walk(fo4, b'WEAP') if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == edid)


class Filters:
    """What a challenge's event must match, as the build made it: a form list of weapons, victims or items (0: any),
    or its map marker."""

    def __init__(self, builder, export_dir: Path):
        """FNV's weapons, form lists and creature types, for `builder`'s made forms."""
        self.builder, self.weapon_recs = builder, export_records(export_dir, 'WEAP')
        self.lists = {int(r['FormID'], 16): [int(r[k], 16) for k in r if k.startswith('LNAM[')]
                      for r in export_records(export_dir, 'FLST')}
        self.types, self.fists = creature_types(export_dir), fo4_weapon(builder.fo4, FISTS)

    def made(self, fnv: int) -> 'int | None':
        """The FO4 form made for FNV item `fnv` (stand-in or its own), else None."""
        return self.builder.items.shared.get(fnv) or self.builder.items.made.get(fnv)

    def weapons(self, rec: dict) -> int:
        """Kill and hit challenges: the weapons of the skill (Value2, kills only), type (Value3) and list (XNAM) set,
        the fists too for Unarmed or hand-to-hand."""
        kind = _int(rec, 'DATA.Type')
        skill, anim = _int(rec, 'DATA.Value2') if kind == KILL_LIST else 0, _int(rec, 'DATA.Value3')
        listed = set(self.lists.get(_hex(rec, 'XNAM'), [])) if 'XNAM' in rec else None
        if kind not in (KILL_LIST, HIT) or not (skill or anim or listed is not None):
            return 0
        forms = {self.made(int(w['FormID'], 16)) for w in self.weapon_recs
                 if (not skill or _int(w, 'DNAM.Skill') == skill) and (not anim or _int(w, 'DNAM.FalloutAnimType') + 1 == anim)
                 and (listed is None or int(w['FormID'], 16) in listed)} - {None}
        forms |= {self.fists} if skill == UNARMED or anim == HAND_TO_HAND else set()
        return form_list(self.builder, f'{rec["EditorID"]} weapons', f'FNV_{rec["EditorID"]}Weapons', sorted(forms))

    def victims(self, rec: dict) -> int:
        """Kill challenges of one actor (SNAM) or a creature type (Value2 - 1): the FO4 actor bases made for them."""
        kind, made = _int(rec, 'DATA.Type'), self.builder.creatures.made
        if kind == KILL_FORM:
            forms = [self.builder.npc_ids.get(_hex(rec, 'SNAM')) or made.get(_hex(rec, 'SNAM'))]
        elif kind == KILL_TYPE:
            forms = [fo4 for fnv, fo4 in sorted(made.items()) if self.types.get(fnv) == _int(rec, 'DATA.Value2') - 1]
        else:
            return 0
        return form_list(self.builder, f'{rec["EditorID"]} victims', f'FNV_{rec["EditorID"]}Victims',
                         [f for f in forms if f])

    def items(self, rec: dict) -> int:
        """Use challenges: the item (SNAM) or the members of its list, as made."""
        kind, snam = _int(rec, 'DATA.Type'), _hex(rec, 'SNAM')
        if kind not in (USE_ITEM, USE_LIST):
            return 0
        forms = [self.made(f) for f in ([snam] if kind == USE_ITEM else self.lists.get(snam, []))]
        return form_list(self.builder, f'{rec["EditorID"]} items', f'FNV_{rec["EditorID"]}Items', [f for f in forms if f])

    def marker(self, rec: dict) -> int:
        """Discovery challenges: the placed map marker (SNAM), else 0."""
        return self.builder.ref_ids.get(rec.get('SNAM'), 0) if _int(rec, 'DATA.Type') == DISCOVER else 0


class Challenges:
    """FNV's challenges, written through a cell builder: `named()` before scripts are filled, `write()` at the end."""

    def __init__(self, builder, export_dir: Path):
        """Read `export_dir`'s challenges; those counted are kept, the others counted as left out."""
        self.builder, self.export_dir, self.kept = builder, export_dir, []
        for rec in sorted(export_records(export_dir, 'CHAL'), key=lambda r: (r.get('FULL', ''), r['EditorID'])):
            how = counting(rec)
            if isinstance(how, str):
                builder.counts[f'CHAL left out: {how}'] += 1
            else:
                self.kept.append((rec, *how))

    def state(self, rec: dict) -> int:
        """The FormID of challenge `rec`'s state global."""
        return self.builder.writer.derive_formid(SITE, f'{rec["EditorID"]} state')

    def named(self) -> dict:
        """{challenge EditorID: its state global}, for the converted scripts' properties."""
        return {rec['EditorID']: self.state(rec) for rec, _, _ in self.kept}

    def write(self) -> 'int | None':
        """Write the kept challenges, their quest and the CHALLENGES tab; the tab quest's FormID. A plugin whose
        master holds the counting quest writes only its own challenges, on a quest of its own adding them to the
        master's quest and tab as it starts; None (no tab of its own).
        See: docs/fork/fo4_pipeline.md#challenges
        """
        writer = self.builder.writer
        quest, sources, tab_rows, tab_shown = (writer.derive_formid(SITE, key)
                                               for key in ('quest', 'sources', 'rows', 'states'))
        mine = quest >> 24 == writer.own_index
        own_quest = quest if mine else writer.derive_formid(SITE, 'plugin quest')
        kept = [k for k in self.kept if mine or self.builder.ids.is_own(int(k[0]['FormID'], 16))]
        columns = {k: [] for k in ('Rows', 'States', 'Names', *INT_COLUMNS, *FORM_COLUMNS)}
        filters = Filters(self.builder, self.export_dir)
        for rec, event, stats in kept:
            for key, value in self._columns(rec, event, STAT_GROUPS.index(stats) if stats else -1, filters).items():
                columns[key].append(value)
        links = {'Sources': sources, 'Hub': quest, 'TabRows': tab_rows, 'TabShown': tab_shown}
        rows = (SOURCE_SCRIPT, links, self._values(columns))
        self.builder.scripts.used += [s for s in (SOURCE_SCRIPT, SCRIPT) if s not in self.builder.scripts.used]
        self.builder.counts['CHAL kept'] = len(kept)
        if not mine:
            writer.add_record('QUST', pack_script_quest(
                own_quest, f'FNV_Challenges_{plugin_stem(self.export_dir)}',
                quest_fragments('', [], scripts=[rows])))
            return None
        self._quest(quest, sources, rows)
        return tab_quest(self.builder, 'CHALLENGES', form_list(self.builder, 'rows', 'FNV_ChallengesRows',
                                                                 columns['Rows']),
                         shown=form_list(self.builder, 'states', 'FNV_ChallengesStates', columns['States']))

    def _columns(self, rec: dict, event: int, group: int, filters: Filters) -> dict:
        """Write challenge `rec`'s progress actor value, state global and reward; its entry in each F3NV_Challenges
        array property."""
        edid, scpt = rec['EditorID'], _hex(rec, 'SCRI')
        script = self.builder.scripts.names.get(scpt)
        reward = self.builder.scripts.effects.script_spell(scpt, f'FNV_{script}Reward') if script else None
        return {'Rows': self._row(rec), 'States': self._state(rec), 'Names': rec.get('FULL') or edid, 'Events': event,
                'Thresholds': _int(rec, 'DATA.Threshold'), 'Intervals': _int(rec, 'DATA.Interval'),
                'Recurring': int(bool(_int(rec, 'DATA.Flags') & RECURRING)), 'Groups': group,
                'Weapons': filters.weapons(rec), 'Victims': filters.victims(rec), 'Items': filters.items(rec),
                'Markers': filters.marker(rec), 'Rewards': reward or 0}

    def _row(self, rec: dict) -> int:
        """Write challenge `rec`'s actor value (its progress) on the CHAL's FormID: FNV's name, description and goal."""
        fid = self.builder.fnv_id(rec['FormID'])
        desc = f'{rec.get("DESC", "")}\n\nGoal: {_int(rec, "DATA.Threshold")}'.strip()
        self.builder.writer.add_record('AVIF', pack_avif(fid, f'FNV_{rec["EditorID"]}Progress',
                                                         rec.get('FULL') or rec['EditorID'], desc))
        return fid

    def _state(self, rec: dict) -> int:
        """Write challenge `rec`'s state global: -2/-1 locked (hidden/shown when unlocked), 0 hidden, 1 shown."""
        flags = _int(rec, 'DATA.Flags')
        value = (1 if flags & SHOW_ZERO else 0) - (2 if flags & START_DISABLED else 0)
        fid = self.state(rec)
        self.builder.writer.add_record('GLOB', pack_global(fid, f'FNV_{rec["EditorID"]}', 'f', float(value)))
        return fid

    @staticmethod
    def _values(columns: dict) -> dict:
        """F3NV_ChallengeSource's value properties for `columns` (one entry per challenge)."""
        values = {key: ('ints', columns[key]) for key in INT_COLUMNS}
        values.update({key: ('objects', columns[key]) for key in ('Rows', 'States', *FORM_COLUMNS)})
        values['Names'] = ('strings', columns['Names'])
        return values

    def _quest(self, quest: int, sources: int, rows: tuple) -> None:
        """Write the game's start-game counting quest: F3NV_Challenges over every STAT_GROUPS stat and registry
        `sources`, the game's challenges (`rows`, F3NV_ChallengeSource), its player alias running
        F3NV_ChallengesPlayer."""
        self.builder.writer.add_record('FLST', R.pack_flst(sources, 'FNV_ChallengeSources', []))
        stat_names = [(name, i) for i, stats in enumerate(STAT_GROUPS) for name in stats]
        values = {'StatNames': ('strings', [n for n, _ in stat_names]), 'StatGroups': ('ints', [g for _, g in stat_names]),
                  'CompletedText': ('string', COMPLETE_TEXT), 'ProgressText': ('string', PROGRESS_TEXT)}
        hub = (SCRIPT, {'Fists': fo4_weapon(self.builder.fo4, FISTS), 'Sources': sources}, values)
        vmad = quest_fragments('', [], aliases=[(0, quest, [(PLAYER_SCRIPT, {}, {})])], scripts=[hub, rows])
        self.builder.writer.add_record('QUST', R.pack_qust(quest, 'FNV_Challenges', '', 0, [], 'Player', PLAYER, vmad))
        self.builder.scripts.used += [PLAYER_SCRIPT] if PLAYER_SCRIPT not in self.builder.scripts.used else []
