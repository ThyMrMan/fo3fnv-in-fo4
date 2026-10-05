"""Spike 1b dialogue rules confirmed in game: Random piles, [Leave], walking away.

See: docs/fork/fo4_spikes.md#spike-1b
"""

import struct
from types import SimpleNamespace

from fo4_import.spike import dialogue as D
from fo4_import.spike import records as R
from fo4_import.spike import voice as V


def _flags(value: int) -> dict:
    """An export INFO record with only DATA.Flags."""
    return {'DATA.Flags': str(value)}


def test_random_pile_gets_an_even_chain():
    """Three Random lines: the first two pass with 1/3 and 1/2, the last always."""
    pile = [(_flags(D.RANDOM), []), (_flags(D.RANDOM), []), (_flags(D.RANDOM | D.RANDOM_END), [])]
    extra = D.random_chain(pile)
    assert [g[0][0]['value'] for g in extra[:2]] == [100.0 / 3, 50.0]
    assert extra[2] == []


def test_negate_or_group_becomes_and_of_negations():
    """NOT(a OR b) is NOT a AND NOT b; NOT(a AND b) is NOT a OR NOT b."""
    a = {'op_flags': 0x00, 'value': 1.0, 'func': 'GetIsID', 'p1': 1, 'p2': 0, 'run_on': 0, 'ref': 0}
    b = dict(a, func='GetInFaction', p1=2)
    spike = SimpleNamespace(report=[])
    assert D.Spike.negate(spike, [[a, b]], 'x') == [[dict(a, op_flags=0x20)], [dict(b, op_flags=0x20)]]
    assert D.Spike.negate(spike, [[a], [b]], 'x') == [[dict(a, op_flags=0x20), dict(b, op_flags=0x20)]]
    assert not spike.report


def test_menu_scene_ends_when_the_speaker_is_out_of_dialogue_range():
    """The Menu phase's completion condition is GetDistance(Player) > ACTV, run on the alias."""
    scene = R.pack_scen(0x01000800, 'Test', 0x01000801, 0, b'', 0x01000802)
    ctda = scene[scene.index(b'CTDA') + 6:][:32]
    op, value, func, p1, _, run_on, _, alias = struct.unpack('<B3xfH2xIIIIi', ctda)
    assert (op, value, func, p1, run_on, alias) == (R.OP_GREATER, R.DIALOGUE_DISTANCE, R.FUNC_GET_DISTANCE,
                                                    R.PLAYER, R.RUN_QUEST_ALIAS, 0)


def test_voice_job_names_the_fuz_by_plugin_voice_type_and_info(tmp_path):
    """An FNV recording of a line goes to Sound/Voice/<plugin>/<voice type>/<INFO id 00xxxxxx>_<n>.fuz."""
    folder = tmp_path / 'maleuniquedocmitchell'
    folder.mkdir()
    (folder / 'vfreeformg_vfreeformgoodsp_00107495_1.ogg').write_bytes(b'')
    rec = {'FormID': '00107495', 'ResponseCount': '1', 'Response[0].ResponseNumber': '1',
           'Response[0].ResponseText': '[SUCCEEDED] Of course.'}
    jobs = V.jobs([(0x02000869, rec)], [(folder, 'NPCMDocWeathers')], tmp_path / 'Data', 'Spike.esp')
    assert [(j[1].relative_to(tmp_path).as_posix(), j[2]) for j in jobs] == [
        ('Data/Sound/Voice/Spike.esp/NPCMDocWeathers/00000869_1.fuz', ' Of course.')]
