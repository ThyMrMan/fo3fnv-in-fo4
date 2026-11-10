"""FNV furniture as FO4 FURN: standing furniture, stools and side-entry chairs.

See: docs/fork/fo4_spikes.md#spike-2-furniture
"""

import collections
import math
import struct
from types import SimpleNamespace

from fo4_import.spike import furniture as F
from tes5_import.base.tes5_reader import subrecords


def _furn(marks: list, idles: tuple = (), motions: dict = None) -> dict:
    """The subrecords of the FURN furniture() writes for one-marker-active FNV furniture with `marks`."""
    record = F.furniture(1, {'EditorID': 'T', 'MNAM.Flags': '1'}, 'm.nif', (-20, -20, 0, 20, 20, 40), marks,
                         collections.defaultdict(int), idles, motions)
    return dict(subrecords(record[24:]))


def test_bar_and_wall_markers_take_vanilla_standing_keywords():
    """Trudy's BarKeep (slot 22, idle BarKeeping) tends bar, Joe's WallMarker (slot 19) leans; a special idle FO4
    lacks (CookingStove) keeps a marker without keywords; a seat is not standing furniture."""
    assert F.standing([(0, 0, 0, 0, F.SPECIAL)], ('BarKeeping',)) == F.IDLE_KEYWORDS['BarKeeping']
    assert F.standing([(0, 0, 0, 0, F.WALL_LEAN)], ()) == F.SLOT_KEYWORDS[F.WALL_LEAN]
    assert F.standing([(0, 0, 0, 0, F.SPECIAL)], ('CookingStove',)) == ()
    assert F.standing([(0, 0, 0, 0, F.SIT_FRONT)], ()) is None


def test_scripted_furniture_keeps_its_script():
    """Nero's couch adds Big Sal's force greet when sat on: its VMAD comes right after the EDID, as vanilla's does."""
    record = F.furniture(1, {'EditorID': 'T', 'MNAM.Flags': '1'}, 'm.nif', (-20, -20, 0, 20, 20, 40),
                         [(0.0, 0.0, 0.0, 0.0, F.SPECIAL)], collections.defaultdict(int), vmad=b'script')
    assert [tag for tag, _ in subrecords(record[24:])][:3] == [b'EDID', b'VMAD', b'OBND']
    assert b'VMAD' not in _furn([(0.0, 0.0, 0.0, 0.0, F.SPECIAL)])


def test_standing_furniture_keeps_fnv_marker_as_vanilla_lays_it_out():
    """One SNAM marker where FNV has it, entered from every side, MNAM sit | marker 0 (vanilla NPCBartender)."""
    subs = _furn([(0.0, 0.0, 0.0, 0.0, F.SPECIAL)], ('BarKeeping',))
    assert struct.unpack('<I', subs[b'MNAM'])[0] == F.SIT | 1
    assert struct.unpack('<4fIB3x', subs[b'SNAM']) == (0.0, 0.0, 0.0, 0.0, 0, F.ANY_ENTRY)


def test_furniture_idles_name_the_furniture_their_condition_tests():
    """An IDLE whose IsCurrentFurnitureObj names a FURN is listed under that FURN."""
    raw = struct.pack('<B3xfIIIII', 0, 1.0, 163, 0x000B24DB, 0, 0, 0).hex()
    idles = [{'EditorID': 'BarKeeping', 'ConditionCount': '1', 'Condition[0].Raw': raw}]
    assert F.furniture_idles(idles) == {'000B24DB': ('BarKeeping',)}


def test_stool_seat_is_where_the_enter_animation_leaves_the_actor():
    """A stool marker moves by its enter motion (right, forward, turn) and takes the bar stool keywords."""
    seats, words, marker = F.slot_seats([(10.0, 0.0, 0.0, 0.0, F.SIT_STOOL)], 1, {F.SIT_STOOL: (0.0, 5.0, math.pi)})
    assert [tuple(round(v, 3) for v in s[:4]) + s[4:] for s in seats] == [(10.0, 5.0, 0.0, 3.142, F.ANY_ENTRY)]
    assert (words, marker) == F.SLOT_SEATS[F.SIT_STOOL]


def test_lone_front_seat_is_also_left_from_both_sides():
    """A one-seat chair FNV enters from the front only gets vanilla's usual 0xFD; a two-seat couch keeps 0xF1."""
    front = lambda x: (x, 40.0, 0.0, math.pi, F.SIT_FRONT)
    assert [s[4] for s in F.seats([front(0.0)], 1, (-20, -20, 0, 20, 20, 40))] == [0xFD]
    assert [s[4] for s in F.seats([front(-20.0), front(20.0)], 3, (-40, -20, 0, 40, 20, 40))] == [0xF1, 0xF1]


def test_side_entry_chair_gets_a_seat_between_its_side_markers():
    """A chair entered only from the left (-30, facing +X) and right (+30, facing -X) seats once, midway."""
    marks = [(-30.0, 0.0, 0.0, math.pi / 2, F.SIT_LEFT), (30.0, 0.0, 0.0, 3 * math.pi / 2, F.SIT_RIGHT)]
    seats = F.seats(marks, 3, (-20, -20, 0, 20, 20, 40))
    assert [(round(x, 3), round(y, 3), round(h, 3)) for x, y, _, h, _ in seats] == [(0.0, 2.0, 0.0)]


def test_a_wall_lean_marker_moves_to_where_fnvs_enter_animation_ends():
    """The enter motion moves the marker 31.2 forward and turns it."""
    placed = F.entered([(0.0, 0.0, 0.0, 0.0, F.WALL_LEAN)], 1, (0.0, 31.2, math.pi))
    assert [tuple(round(v, 3) for v in p[:4]) for p in placed] == [(0.0, 31.2, 0.0, round(math.pi, 3))]


def test_floor_beds_take_vanilla_sides_from_where_the_marker_lies():
    """Left of the middle: Right; right of it: Left; middle: both (vanilla's ground beds). FNV's bare floor sleep,
    at heading 270, keeps its Left; other bits stay."""
    turn = math.pi / 2
    bed = [(-20.0, 0.0, -6.0, turn, F.UNUSED_ENTRY | F.LEFT), (20.0, -4.0, -6.0, turn, F.UNUSED_ENTRY | F.RIGHT),
           (1.0, 0.0, 0.0, turn + 3 * math.pi / 2, F.UNUSED_ENTRY | F.LEFT),
           (0.0, 36.0, 0.0, turn + 3 * math.pi / 2, F.UNUSED_ENTRY | F.LEFT)]
    out = F.floor_beds(bed)
    assert [e & (F.RIGHT | F.LEFT) for *_, e in out] == [F.RIGHT, F.LEFT, F.RIGHT | F.LEFT, F.LEFT]
    assert all(e & F.UNUSED_ENTRY == F.UNUSED_ENTRY for *_, e in out) and abs(out[0][3]) < 1e-9


def test_a_held_pose_without_bip01_leaves_the_actor_at_its_marker():
    """The crucifix pose moves only the body; the actor stays at its marker."""
    pose = SimpleNamespace(translation=SimpleNamespace(x=3.6, y=59.4, z=179.4),
                           rotation=SimpleNamespace(w=0.0, x=0.0, y=0.0, z=1.0))
    assert F.motion({'Bip01 NonAccum': pose}) == (0.0, 0.0, 0.0)


def test_the_crucifix_is_a_restrained_sit_at_fnvs_marker():
    """Slot 10: a prisoner floor sit at FNV's marker, entered from every side."""
    seats, words, marker = F.slot_seats([(0.0, 0.0, 0.0, 0.0, F.CRUCIFIED)], 1, {F.CRUCIFIED: (0.0, 0.0, 0.0)})
    assert seats == [(0.0, 0.0, 0.0, 0.0, F.ANY_ENTRY)]
    assert (words, marker) == (('AnimFurnPrisonerFloorSit',), 'Markers' + chr(92) + 'MarkerPrisonerFloorSit.nif')
