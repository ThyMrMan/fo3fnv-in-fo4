"""FNV idle markers as the vanilla FO4 marker playing what their idles play.

See: docs/fork/fo4_pipeline.md#audit-fixes
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import idle_markers as IM
from fo4_import.spike.cell import CellBuilder
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_group, pack_record, pack_string_subrecord

#: The FalloutNV.esm export (a junction in the main checkout).
FNV_EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'

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


def _export(folder: Path, sig: str, records: list) -> None:
    """Write `records` (dicts) as export file `sig`.txt in `folder`."""
    blocks = ['---RECORD_BEGIN---\nSignature=%s\n%s\n---RECORD_END---\n'
              % (sig, '\n'.join(f'{k}={v}' for k, v in r.items())) for r in records]
    (folder / f'{sig}.txt').write_text('\n'.join(blocks), encoding='utf-8')


def _idle(fid: int, model: str) -> dict:
    """An FNV IDLE export record playing `model` (backslashes doubled)."""
    return {'FormID': f'{fid:08X}', 'EditorID': f'I{fid:X}', 'Model.MODL': model.replace('\\', '\\\\')}


def _marker(rec: dict, idles: tuple = ()) -> dict:
    """IDLM export record `rec` listing `idles` (IDLA.Idle[i])."""
    return {**rec, **{f'IDLA.Idle[{i}]': f'{fid:08X}' for i, fid in enumerate(idles)}}


def test_listed_idles_reads_the_export_list_in_order():
    """IDLA.Idle[0], [1]... in order; none without them."""
    assert IM.listed_idles({'IDLA.Idle[0]': '00000012', 'IDLA.Idle[1]': '0000000A'}) == [0x12, 0x0A]
    assert IM.listed_idles({'EditorID': 'X'}) == []


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


def _engineer_and_robot(folder: Path) -> IM.IdleMarkers:
    """IdleMarkers over an export in `folder`: an engineer's terminal and fidget idles, a protectron's turn-on
    idle."""
    fo4 = _plugin(('IDLM', 0x14B737, pack_string_subrecord('EDID', 'NPCStandingExamineIdleMarker')),
                  ('IDLM', 0x01E1B0, pack_string_subrecord('EDID', IM.EMPTY)))
    _export(folder, 'IDLE', [_idle(0x10, 'Characters\\_Male\\IdleAnims\\ScientistInspectTerminalA.kf'),
                             _idle(0x11, 'Characters\\_Male\\IdleAnims\\LookingAround.kf'),
                             _idle(0x12, 'Characters\\_Male\\IdleAnims\\SpecialIdle_Swatting.kf'),
                             _idle(0x13, 'Creatures\\Protectron\\IdleAnims\\MTSpecialIdle_Activate.kf')])
    _export(folder, 'IDLM', [_marker(ENGINEER, (0x10, 0x11, 0x12)), _marker(ROBOT, (0x13,))])
    return IM.IdleMarkers(fo4, folder)


def test_idle_markers_read_fnv_idle_lists_and_say_what_is_left_out(tmp_path):
    """IDLA read from the export: the engineer stands, the protectron is left out."""
    markers = _engineer_and_robot(tmp_path)
    assert markers.of(ENGINEER) == (0x14B737, 'NPCStandingExamineIdleMarker')
    assert markers.of(ROBOT) == (None, 'creatures\\protectron')


def _builder(markers: IM.IdleMarkers, converted: dict) -> SimpleNamespace:
    """A cell builder whose idles convert `converted` {FNV idle: FO4 idle}, writing into `records`."""
    records = []
    return SimpleNamespace(idle_markers=markers, counts=Counter(), records=records, fnv_id=lambda fid: 0x900 + fid,
                           idles=SimpleNamespace(idle=converted.get),
                           writer=SimpleNamespace(add_record=lambda sig, rec: records.append((sig, rec))))


def test_a_marker_fo4_plays_nothing_like_is_the_empty_marker_counted_by_what_it_plays(tmp_path):
    """The converter returns the stand-in, else (none of its idles converting) the empty marker, as packages,
    patrol routes and scripts name the spot."""
    builder = _builder(_engineer_and_robot(tmp_path), {})
    assert CellBuilder.idle(builder, 0x20, 'IDLM', ENGINEER) == 0x14B737
    assert CellBuilder.idle(builder, 0x21, 'IDLM', _marker(ROBOT, (0x13,))) == 0x01E1B0
    assert builder.counts == {'idle marker placed': 1, 'idle marker placed empty: creatures\\protectron': 1}
    assert builder.records == []


def test_a_marker_fo4_plays_nothing_like_is_written_on_its_converted_idles(tmp_path):
    """The protectron's marker, its one idle converting, is FO4's IDLM on its FNV FormID: FNV's bounds, flags
    with Loose Only, timer and the converted idle; written once however often placed."""
    builder = _builder(_engineer_and_robot(tmp_path), {0x13: 0x800})
    robot = {**_marker(ROBOT, (0x13, 0x14)), 'OBND.X1': '-54', 'OBND.Y2': '89', 'IDLF.Flags': '1',
             'IDLT.Timer': '12.0'}
    assert CellBuilder.idle(builder, 0x21, 'IDLM', robot) == CellBuilder.idle(builder, 0x21, 'IDLM', robot) == 0x921
    assert builder.counts == {'idle marker placed on its own idles': 2, 'IDLM (own idles)': 1}
    (sig, record), = builder.records
    subs = dict(subrecords(record[24:]))
    assert sig == 'IDLM' and struct.unpack('<6h', subs[b'OBND']) == (-54, 0, 0, 0, 89, 0)
    assert (subs[b'IDLF'], subs[b'IDLC'], subs[b'IDLT'], subs[b'IDLA']) == (
        b'\x09', b'\x01', struct.pack('<f', 12.0), struct.pack('<I', 0x800))


@pytest.mark.skipif(not (FALLOUT4_ESM.exists() and (FNV_EXPORT / 'IDLM.txt').exists()),
                    reason='needs Fallout4.esm and the FalloutNV.esm export')
def test_vanilla_stand_ins_exist_and_earlier_choices_hold():
    """Every stand-in is in Fallout4.esm, a furniture one standing the actor at the reference (SNAM offset and
    heading 0), and the rule gives each earlier EditorID choice its earlier marker."""
    fo4 = FALLOUT4_ESM.read_bytes()
    markers = IM.IdleMarkers(fo4, FNV_EXPORT)
    assert set(markers.vanilla) == {*IM.PLAYS, *IM.MARKERS.values(), IM.EMPTY}
    snams = {rec.form_id: first_sub(rec.body, b'SNAM') for rec, _ in walk(fo4, b'FURN')}
    assert all(struct.unpack_from('<4f', snams[fid]) == (0.0,) * 4 for fid in markers.vanilla.values() if fid in snams)
    by_edid = {rec.get('EditorID'): rec for rec in export_records(FNV_EXPORT, 'IDLM')}
    assert {e: markers.of(by_edid[e])[1] for e in EARLIER} == EARLIER
