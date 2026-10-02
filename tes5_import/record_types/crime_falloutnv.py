"""FO3/FNV crime: a major crime makes each Track Crime faction of the victim the player's enemy.

FO3 and FNV keep no bounty (GECK Category:Crime). Assault and murder make
the victim and every faction of it flagged Track Crime (FACT `DATA.Flags2`
bit 0) enemies of the player; theft, pickpocketing and trespass make only the
victim one. Skyrim notices a crime only against an actor with a crime
faction, so an NPC's `CRIF` is its first listed Track Crime faction, kept as
the detector: no FO3/FNV class is a guard, and these factions neither arrest
nor attack on sight, so the bounty Skyrim keeps there moves no one.
TES4_FalloutCrime, started by the Story Manager's kill and assault events,
marks every Track Crime faction the victim is in as the player's enemy.

See: docs/commentary/tes5_import_actors.md#fallout-crime-factions
"""

from ..base.master_export import records_of
from ..base.story_nodes import story_node, story_quest
from ..base.text_reader import remap_formid
from ..base.writer import pack_formid_subrecord, pack_record, pack_string_subrecord
from .common import get_formid, get_int

#: FO3/FNV FACT DATA.Flags2 Track Crime.
_TRACK_CRIME = 0x01

#: The FormList of every Track Crime faction, which TES4_FalloutCrime walks.
CRIME_LIST_EDID = 'TES4TrackCrimeFactions'

#: The static script the crime event quests run.
CRIME_SCRIPT = 'TES4_FalloutCrime'

#: (name, Story Manager event, Skyrim.esm event node, the node's last vanilla child) per crime event.
_EVENTS = (('Kill', b'KILL', 0x00013010, 0x0001E491), ('Assault', b'ASSU', 0x0002C494, 0x00037FBE))

#: Quests per node, so crimes close together each find one not already running.
_POOL = 4

#: The FormList of the factions whose player-enemy flag is set, which converted reads test.
ENEMY_LIST_EDID = 'TES4PlayerEnemyFactions'

#: The two lists' FormIDs by EditorID, once written.
_LISTS: dict = {}

#: Raw FormIDs of the Track Crime factions, this run's and its masters', in record order.
_TRACKING: list = []


def tracks_crime(rec: dict) -> bool:
    """Whether an FO3/FNV FACT authors Track Crime (TES4 has no such flag)."""
    return bool(get_int(rec, 'DATA.Flags2') & _TRACK_CRIME)


def load_tracking_factions(by_type: dict, master_export: dict = None) -> None:
    """Index every Track Crime faction, this plugin's and its masters'."""
    facts = [(r.get('FormID', ''), r) for r in by_type.get('FACT', [])]
    facts += records_of(master_export, 'FACT')
    _TRACKING[:] = [int(key, 16) for key, rec in facts if tracks_crime(rec)]


def authored_crime_faction(rec: dict) -> 'int | None':
    """The (remapped) first listed Track Crime faction an actor is in, 0 for none; None when the source has none."""
    if not _TRACKING:
        return None
    tracking = set(_TRACKING)
    for i in range(get_int(rec, 'FactionCount')):
        if int(rec.get(f'Faction[{i}].FormID') or '0', 16) in tracking:
            return get_formid(rec, f'Faction[{i}].FormID')
    return 0


def _flst(writer, edid: str, raws: list) -> int:
    """Write one FormList of the (raw) `raws`; its FormID."""
    fid = writer.derive_formid('SYNTH_FLST', edid)
    subs = pack_string_subrecord('EDID', edid)
    subs += b''.join(pack_formid_subrecord('LNAM', remap_formid(raw)) for raw in raws)
    writer.add_record('FLST', pack_record('FLST', fid, 0, subs))
    return fid


def create_crime_list(writer) -> dict:
    """Write TES4TrackCrimeFactions and the empty TES4PlayerEnemyFactions for a source with Track Crime
    factions; {EditorID: FormID}, else {}."""
    _LISTS.clear()
    if _TRACKING:
        _LISTS[CRIME_LIST_EDID] = _flst(writer, CRIME_LIST_EDID, _TRACKING)
        _LISTS[ENEMY_LIST_EDID] = _flst(writer, ENEMY_LIST_EDID, [])
    return dict(_LISTS)


def build_crime_events(writer) -> int:
    """Write the kill and assault event quests and their Story Manager nodes; how many quests, 0 without a list.

    script_convert.pipeline is imported here: it imports the importer's
    dialogue package, a cycle at load.
    """
    from script_convert.pipeline import build_vmad_quest_fragments
    if not _LISTS:
        return 0
    props = dict(_LISTS)
    count = 0
    for name, event, node, last_child in _EVENTS:
        quests = []
        for i in range(_POOL):
            edid = f'TES4FalloutCrime{name}{i}'
            fid = writer.derive_formid('SYNTH_QUST', edid)
            vmad = build_vmad_quest_fragments(edid, [], None, (CRIME_SCRIPT, props), quest_fid=fid)
            writer.add_record('QUST', story_quest(fid, edid, event, vmad))
            quests.append(fid)
        node_edid = f'TES4FalloutCrime{name}Node'
        writer.add_record('SMQN', story_node(writer.derive_formid('SYNTH_SMQN', node_edid), node_edid,
                                             (node, last_child), quests))
        count += len(quests)
    return count
