"""FNV karma and infamy from the player's kills and crimes, on Fallout 4, for the cell spike.

FNV's engine scores these itself (read from FalloutNV.exe for the Skyrim
build's character rules, character_rules.md#fallout-karma-and-infamy): a
kill's karma by the victim's alignment when a crime-tracking faction claims
it, a theft's unless the owner is evil, and infamy with a reputation for a
reported murder (major) or a kill in a fight or reported theft (minor). The
same lists and amounts come from the character data (`character_data`,
`amount_table`): the actors of each alignment and the evil and
crime-tracking factions (as built here: FNV's NPCs, creatures and factions
on their FO4 records), each reputation's FormList (reputation.py) and the
crime-tracking factions answering to it, and the settings' amounts.

A start-game quest runs F3NV_FalloutStandings with them, its player alias
F3NV_FalloutStandingsPlayer (every item taken). Two event quests hear the
Story Manager's kill (KILL) and crime-gold (ADCR) events, from quest nodes
added after the last child of Fallout4.esm's own event nodes, sharing the
event, so vanilla's still run.

See: docs/fork/fo4_pipeline.md#standings
"""

import struct
from pathlib import Path

from fo4_import.base.support_records import pack_event_quest, pack_story_node
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.reputation import KARMA_KEY
from tes5_import.base.tes5_reader import first_sub, walk
from tes5_import.character_data_falloutnv import character_data, game_of
from tools.release.character_rules_standings import ALIGNMENT_LISTS, amount_table

#: derive_formid site of this module's records (key: what each is).
SITE = 'FNV standings'
#: The scripts: the rules on the start-game quest, its player alias's, and the two event quests'.
SCRIPT, PLAYER_SCRIPT, KILL_SCRIPT, CRIME_SCRIPT = ('F3NV_FalloutStandings', 'F3NV_FalloutStandingsPlayer',
                                                    'F3NV_FalloutKillEvent', 'F3NV_FalloutCrimeEvent')
#: Fallout4.esm's Story Manager event nodes: Kill Actor (00034A37) and CrimeGoldEvent (00245FD3), by event.
EVENT_NODES = {b'KILL': 0x034A37, b'ADCR': 0x245FD3}
#: The player reference (alias forced to it).
PLAYER = 0x14
#: Fallout4.esm's keyword a person carries (a murder reads the NPC amount).
NPC_KEYWORD = 'ActorTypeNPC'
#: The export types the character data needs here.
DATA_TYPES = ('NPC_', 'CREA', 'LVLN', 'LVLC', 'FACT', 'REPU', 'GMST')


def last_child(fo4: bytes, parent: int) -> int:
    """The last of Fallout4.esm Story Manager node `parent`'s children (none naming it as its previous); 0 if none."""
    children = {rec.form_id: struct.unpack('<I', first_sub(rec.body, b'SNAM') or bytes(4))[0]
                for rec, _ in walk(fo4, b'SMQN', b'SMBN', b'SMEN')
                if struct.unpack('<I', first_sub(rec.body, b'PNAM') or bytes(4))[0] == parent}
    previous = set(children.values())
    return next((fid for fid in sorted(children) if fid not in previous), 0)


def keyword(fo4: bytes, edid: str) -> int:
    """The FormID of Fallout4.esm's keyword `edid`."""
    return next(r.form_id for r, _ in walk(fo4, b'KYWD') if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == edid)


class Standings:
    """The records of FNV's karma and infamy rules, written through a cell builder."""

    def __init__(self, builder, export_dir: Path):
        """The character data of `export_dir`'s game, for `builder`."""
        self.builder, self.game = builder, game_of(str(export_dir))
        by_type = {sig: list(export_records(export_dir, sig)) for sig in DATA_TYPES}
        self.doc = character_data(by_type, [], export_dir.name, self.game)

    def build(self) -> None:
        """Write the lists, the rules quest and its player alias, the event quests and their Story Manager nodes."""
        writer = self.builder.writer
        quest = writer.derive_formid(SITE, 'quest')
        objects, values = self._lists(), self._amounts()
        objects.update(Karma=self.builder.reputation_slots[KARMA_KEY], ActorTypeNPC=keyword(self.builder.fo4, NPC_KEYWORD))
        vmad = quest_fragments('', [], aliases=[(0, quest, [(PLAYER_SCRIPT, {}, {})])], scripts=[(SCRIPT, objects, values)])
        writer.add_record('QUST', R.pack_qust(quest, 'FNV_Standings', '', 0, [], 'Player', PLAYER, vmad))
        for event, script in ((b'KILL', KILL_SCRIPT), (b'ADCR', CRIME_SCRIPT)):
            name = event.decode().title()
            fid, node = writer.derive_formid(SITE, f'{name} quest'), writer.derive_formid(SITE, f'{name} node')
            writer.add_record('QUST', pack_event_quest(fid, f'FNV_Standings{name}', event,
                                                       object_scripts([(script, {'Standings': quest}, {})])))
            parent = EVENT_NODES[event]
            writer.add_record('SMQN', pack_story_node(node, f'FNV_Standings{name}Node', parent,
                                                      last_child(self.builder.fo4, parent), fid))
        self.builder.scripts.used += [s for s in (SCRIPT, PLAYER_SCRIPT, KILL_SCRIPT, CRIME_SCRIPT)
                                      if s not in self.builder.scripts.used]
        self.builder.counts['standings quests'] = 3

    def _actor(self, fnv: int) -> 'int | None':
        """FNV actor base `fnv`'s FO4 record when the build made it."""
        return self.builder.npc_ids.get(fnv) or self.builder.creatures.made.get(fnv)

    def _lists(self) -> dict:
        """{property: FormList} of the alignment, crime and evil faction lists, and Reputations/ReputationFactions."""
        out, alignments, factions = {}, self.doc.get('alignments', {}), self.doc.get('factions', [])
        for prop, name in ALIGNMENT_LISTS:
            out[prop] = self._list(prop, [f for _, fnv in alignments.get(name, []) for f in [self._actor(fnv)] if f])
        out['CrimeFactions'] = self._list('CrimeFactions', [self.builder.fnv_id(r['form'][1]) for r in factions if r['crime']])
        out['EvilFactions'] = self._list('EvilFactions', [self.builder.fnv_id(r['form'][1]) for r in factions if r['evil']])
        answering = {}
        for row in factions:
            if row['crime'] and row['reputation']:
                answering.setdefault(row['reputation'][1], []).append(self.builder.fnv_id(row['form'][1]))
        reputations = sorted(answering)
        self.reputations = ([self.builder.fnv_id(r) for r in reputations],
                            [self._list(f'ReputationFactions{r:08X}', answering[r]) for r in reputations])
        return out

    def _list(self, name: str, forms: list) -> int:
        """Write form list FNV_Standings`name` of `forms`; its FormID."""
        fid = self.builder.writer.derive_formid(SITE, name)
        self.builder.writer.add_record('FLST', R.pack_flst(fid, f'FNV_Standings{name}', forms))
        return fid

    def _amounts(self) -> dict:
        """The script's value properties: the amounts (amount_table) and the reputation lists."""
        table, out = amount_table(self.doc.get('settings', {}), self.game), {}
        for prop, value in table.items():
            out[prop] = ('floats', value) if prop.startswith('KillKarma') else ('ints', value) if isinstance(value, list) \
                else ('float', value)
        reputations, answering = self.reputations
        out.update(Reputations=('objects', reputations), ReputationFactions=('objects', answering))
        return out
