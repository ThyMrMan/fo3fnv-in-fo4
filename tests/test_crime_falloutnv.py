"""FO3/FNV crime: the detector CRIF, factions that never arrest, and the kill/assault Story Manager hooks."""

import struct

import pytest

from tes5_import.base.writer import PluginWriter
from tes5_import.record_types import crime_falloutnv as crime
from tes5_import.record_types.actor_common import convert_FACT


def _subs(record: bytes) -> list:
    """(signature, payload) for each subrecord of one packed record."""
    body, pos, out = record[24:], 0, []
    while pos + 6 <= len(body):
        size = struct.unpack_from('<H', body, pos + 4)[0]
        out.append((body[pos:pos + 4], body[pos + 6:pos + 6 + size]))
        pos += 6 + size
    return out


@pytest.fixture
def tracking():
    """Two Track Crime factions (Crime, Settler) and one that tracks nothing."""
    by_type = {'FACT': [{'FormID': '00001000', 'DATA.Flags2': '1'}, {'FormID': '00002000', 'DATA.Flags2': '1'},
                        {'FormID': '00003000', 'DATA.Flags2': '0'}]}
    crime.load_tracking_factions(by_type)
    yield by_type
    crime.load_tracking_factions({})


def test_the_crime_faction_is_the_first_listed_track_crime_faction(tracking):
    """The authored list order decides; an NPC in no tracking faction gets none."""
    npc = {'FactionCount': '3', 'Faction[0].FormID': '00003000', 'Faction[1].FormID': '00002000',
           'Faction[2].FormID': '00001000'}
    assert crime.authored_crime_faction(npc) & 0xFFFFFF == 0x2000
    assert crime.authored_crime_faction({'FactionCount': '1', 'Faction[0].FormID': '00003000'}) == 0


def test_without_track_crime_factions_the_source_keeps_its_realm(tracking):
    """None (not 0) when the source has no Track Crime faction, as TES4 has none."""
    crime.load_tracking_factions({})
    assert crime.authored_crime_faction({'FactionCount': '0'}) is None


def test_a_track_crime_faction_neither_arrests_nor_attacks_on_sight(tracking):
    """CRVA Arrest and Attack On Sight are 0; the crime amounts stay."""
    crva = dict(_subs(convert_FACT(tracking['FACT'][0])))[b'CRVA']
    assert struct.unpack_from('<BBH', crva) == (0, 0, 1000)


def test_kill_and_assault_quests_hang_under_skyrims_event_nodes(tracking):
    """Both lists exist; each event gets a node after vanilla's last child, starting its pool of quests."""
    writer = PluginWriter(masters=['Skyrim.esm'])
    lists = crime.create_crime_list(writer)
    assert set(lists) == {crime.CRIME_LIST_EDID, crime.ENEMY_LIST_EDID}
    assert crime.build_crime_events(writer) == 8
    nodes = [dict(_subs(rec)) for rec in writer._top_groups['SMQN']]
    places = {(struct.unpack('<I', n[b'PNAM'])[0], struct.unpack('<I', n[b'SNAM'])[0]) for n in nodes}
    assert places == {(0x00013010, 0x0001E491), (0x0002C494, 0x00037FBE)}
    events = {dict(_subs(q)).get(b'ENAM') for q in writer._top_groups['QUST']}
    assert events == {b'KILL', b'ASSU'}
    flst = [dict(_subs(r)) for r in writer._top_groups['FLST']]
    assert sorted(len([s for s in _subs(r) if s[0] == b'LNAM']) for r in writer._top_groups['FLST']) == [0, 2]
    assert all(b'EDID' in f for f in flst)
