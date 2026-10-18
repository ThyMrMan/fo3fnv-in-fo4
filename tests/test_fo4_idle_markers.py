"""FNV idle markers as the vanilla FO4 marker playing what their idles play.

See: docs/fork/fo4_pipeline.md#audit-fixes
"""

import struct
from collections import Counter
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM, FALLOUTNV_ESM
from fo4_import.spike import idle_markers as IM
from fo4_import.spike.cell import CellBuilder
from tes5_import.base.tes5_reader import first_sub, walk, zstr
from tes5_import.base.writer import pack_group, pack_record, pack_string_subrecord, pack_subrecord

#: Earlier EditorID choices the idle rule now makes (FNV IDLM -> Fallout4.esm marker).
EARLIER = {'DefaultHumanPatrolIdleMarker': 'PatrolIdleMarker', 'PatrolScanAreaIdleMarker': 'PatrolIdleMarker',
           'DefaultGuardMarker': 'PatrolIdleMarker', 'DefaultHumanIdleMarker': 'NPCStandingExamineIdleMarker',
           'DefaultSmokingIdleMarker': 'NPCSmokeIdleMarker', 'DefaultFireBarrelIdleMarker': 'NPCHandWarmingStanding',
           'DefaultRakingMarker': 'NPCPushBroomSweep', 'MS17AgathaSweepsIdle': 'NPCPushBroomSweep',
           'GobSweep': 'NPCPushBroomSweep', 'DogIdleMarker': 'DogmeatIdleMarkerSniffScratch',
           'DogSitIdleMarker': 'DogmeatIdleMarkerSniffScratch'}
#: Export records of the test plugin's two idle markers.
ENGINEER = {'FormID': '00000020', 'EditorID': 'VHDPreBattleEngineerIdleMarker'}
ROBOT = {'FormID': '00000021', 'EditorID': 'DefaultRobotIdleMarker'}


def _plugin(*records: tuple) -> bytes:
    """A TES4 header, then each (signature, FormID, subrecords) record in a top group."""
    groups = b''.join(pack_group(0, sig.encode(), pack_record(sig, fid, 0, subs)) for sig, fid, subs in records)
    return pack_record('TES4', 0, 0, b'') + groups


def _idle(fid: int, model: str) -> tuple:
    """An FNV IDLE record playing `model`."""
    return 'IDLE', fid, pack_string_subrecord('EDID', f'I{fid:X}') + pack_string_subrecord('MODL', model)


def _marker(fid: int, edid: str, idles: tuple = ()) -> tuple:
    """An IDLM record listing `idles`."""
    idla = pack_subrecord('IDLA', struct.pack(f'<{len(idles)}I', *idles))
    return 'IDLM', fid, pack_string_subrecord('EDID', edid) + idla


def test_plays_names_a_human_idle_by_file_and_a_creature_idle_by_skeleton():
    """A human idle is its file name, a creature's its skeleton folder (FNV IDLE MODL)."""
    assert IM.plays('Characters\\_Male\\IdleAnims\\2hrCrouch.kf') == '2hrcrouch.kf'
    assert IM.plays('Creatures\\Protectron\\IdleAnims\\MTSpecialIdle_Halt.kf') == 'creatures\\protectron'


def test_marker_takes_the_fo4_marker_most_of_its_idles_play():
    """FNV picks an idle at random: weapon idles with one look around are a patrol, fidgets with one smoke a
    standing idle, ghoul idles FO4's patrol marker (its feral ghoul flavors); a tie goes to the first idle."""
    assert IM.stand_in('X', ['2hrcrouch.kf', 'lookingaround.kf', '2haalertscan.kf']) == 'PatrolIdleMarker'
    assert IM.stand_in('X', ['specialidle_swatting.kf', 'smokingstanding.kf', 'sirelaxed.kf']) == \
        'NPCStandingExamineIdleMarker'
    assert IM.stand_in('X', ['creatures\\ghoul'] * 5) == 'PatrolIdleMarker'
    assert IM.stand_in('X', ['drinkingstandinga.kf', 'sweeping.kf']) == 'NPCStandDrinkCoffee'


def test_idles_fo4_has_nothing_for_do_not_vote():
    """Talk and watering idles FO4 has no marker for leave a bartender a bartender; with nothing else, none."""
    idles = ['talk_toplayerrelaxedc.kf', '3rdp_specialidle_barkeeper01.kf', 'girlwateringflowers.kf']
    assert IM.stand_in('X', idles) == 'NPCBartender'
    assert IM.stand_in('X', ['girlwateringflowers.kf']) is None
    assert IM.stand_in('X', ['creatures\\protectron'] * 3) is None


def test_marker_without_idles_is_the_empty_marker_and_markers_keep_earlier_choices():
    """No idles: FO4's EmptyIdleMarker. The shopkeeper's one sweep among two fidgets keeps the push broom."""
    assert IM.stand_in('VStripFluffPortMarker', []) == IM.EMPTY
    idles = ['sweeping.kf', 'specialidle_swatting.kf', 'sleepyrubeyes.kf']
    assert IM.stand_in('X', idles) == 'NPCStandingExamineIdleMarker'
    assert IM.stand_in('DefaultShopkeeperIdleMarker', idles) == 'NPCPushBroomSweep'


def _engineer_and_robot() -> IM.IdleMarkers:
    """IdleMarkers over plugin bytes: an engineer's terminal and fidget idles, a protectron's turn-on idle."""
    fo4 = _plugin(('IDLM', 0x14B737, pack_string_subrecord('EDID', 'NPCStandingExamineIdleMarker')))
    fnv = _plugin(_idle(0x10, 'Characters\\_Male\\IdleAnims\\ScientistInspectTerminalA.kf'),
                  _idle(0x11, 'Characters\\_Male\\IdleAnims\\LookingAround.kf'),
                  _idle(0x12, 'Characters\\_Male\\IdleAnims\\SpecialIdle_Swatting.kf'),
                  _idle(0x13, 'Creatures\\Protectron\\IdleAnims\\MTSpecialIdle_Activate.kf'),
                  _marker(0x20, ENGINEER['EditorID'], (0x10, 0x11, 0x12)), _marker(0x21, ROBOT['EditorID'], (0x13,)))
    return IM.IdleMarkers(fo4, fnv)


def test_idle_markers_read_fnv_idle_lists_and_say_what_is_left_out():
    """IDLA read from plugin bytes: the engineer stands, the protectron is left out."""
    markers = _engineer_and_robot()
    assert markers.of(ENGINEER) == (0x14B737, 'NPCStandingExamineIdleMarker')
    assert markers.of(ROBOT) == (None, 'creatures\\protectron')


def test_cell_builder_counts_a_left_out_marker_by_what_it_plays():
    """The converter returns the stand-in and counts it placed; a marker without one by what it plays."""
    builder = SimpleNamespace(idle_markers=_engineer_and_robot(), counts=Counter())
    assert CellBuilder.idle(builder, 0x20, 'IDLM', ENGINEER) == 0x14B737
    assert CellBuilder.idle(builder, 0x21, 'IDLM', ROBOT) is None
    assert builder.counts == {'idle marker placed': 1, 'idle marker left out: creatures\\protectron': 1}


@pytest.mark.skipif(not (FALLOUT4_ESM.exists() and FALLOUTNV_ESM.exists()), reason='needs both game masters')
def test_vanilla_stand_ins_exist_and_earlier_choices_hold():
    """Every stand-in is in Fallout4.esm, a furniture one standing the actor at the reference (SNAM offset and
    heading 0), and the rule gives each earlier EditorID choice its earlier marker."""
    fo4, fnv = FALLOUT4_ESM.read_bytes(), FALLOUTNV_ESM.read_bytes()
    markers = IM.IdleMarkers(fo4, fnv)
    assert set(markers.vanilla) == {*IM.PLAYS, *IM.MARKERS.values(), IM.EMPTY}
    snams = {rec.form_id: first_sub(rec.body, b'SNAM') for rec, _ in walk(fo4, b'FURN')}
    assert all(struct.unpack_from('<4f', snams[fid]) == (0.0,) * 4 for fid in markers.vanilla.values() if fid in snams)
    edids = {zstr(first_sub(rec.body, b'EDID')): rec.form_id for rec, _ in walk(fnv, b'IDLM')}
    assert {e: markers.of({'FormID': f'{edids[e]:08X}', 'EditorID': e})[1] for e in EARLIER} == EARLIER
