"""Spike 1b dialogue rules confirmed in game: Random piles, [Leave], walking away.

See: docs/fork/fo4_spikes.md#spike-1b
"""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.nif import file as nf
from fo4_import.spike import dialogue as D
from fo4_import.spike import imods as I
from fo4_import.spike import poses as P
from fo4_import.spike import records as R
from fo4_import.spike import skeleton as S
from fo4_import.spike import voice as V
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def _flags(value: int) -> dict:
    """An export INFO record with only DATA.Flags."""
    return {'DATA.Flags': str(value)}


def test_random_pile_gets_an_even_chain():
    """Three Random lines: the first two pass with 1/3 and 1/2, the last always."""
    pile = [(_flags(D.RANDOM), []), (_flags(D.RANDOM), []), (_flags(D.RANDOM | D.RANDOM_END), [])]
    extra = D.random_chain(pile)
    assert [g[0][0]['value'] for g in extra[:2]] == [100.0 / 3, 50.0]
    assert extra[2] == []


def test_random_pile_chains_each_condition_set_alone():
    """Sir/madame lines alternate in one pile; each set keeps a last line with no roll."""
    sir, madame = [[{'func': 'GetIsSex', 'p1': 0}]], [[{'func': 'GetIsSex', 'p1': 1}]]
    pile = [(_flags(D.RANDOM), sir), (_flags(D.RANDOM), madame), (_flags(D.RANDOM), sir),
            (_flags(D.RANDOM | D.RANDOM_END), madame)]
    extra = D.random_chain(pile)
    assert [g[0][0]['value'] for g in extra[:2]] == [50.0, 50.0]
    assert extra[2:] == [[], []]


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


def test_imad_moves_fnv_contrast_to_fo4_and_resets_hdr_slots():
    """FNV contrast (pair 18) is FO4's pair 19 with its key count; FNV's skin dimmer (pair 2) becomes FO4's identity."""
    keys = struct.pack('<6f', 0.0, 1.0, 0.5, 2.0, 1.0, 1.0)
    counts = [2] * 42
    counts[18 * 2] = counts[2 * 2] = 3
    dnam = struct.pack('<If42I', 1, 3.0, *counts) + bytes(244 - 176)
    body = pack_subrecord('EDID', b'T\0') + pack_subrecord('DNAM', dnam)
    body += pack_subrecord('\x12IAD', keys) + pack_subrecord('\x02IAD', keys)
    subs = dict(subrecords(I.convert(body)))
    ints = struct.unpack('<63I', subs[b'DNAM'])
    assert subs[b'\x13IAD'] == keys and ints[2 + 19 * 2] == 3
    assert subs[b'\x02IAD'] == I.MULT_KEYS and ints[2 + 2 * 2] == 2
    assert ints[61:] == (2, 2) and subs[b'NAM5'] == I.ZERO_KEYS


def test_seat_moves_from_the_start_marker_onto_docs_bed():
    """VCG01's start marker stands 13 units outside the twin bed; the seat goes 18 inside its mesh edge, facing out."""
    bed = Path('export/FalloutNV.esm/meshes/furniture/nv_bedtwin01.nif')
    if not bed.exists():
        pytest.skip('needs the FalloutNV.esm export')
    marker = ((2257.0427, 2318.2153, 7360.0), (0.0, 0.0, 3.1415987))
    (x, y, z), rot = P.seat_place(marker, [(((2281.6326, 2377.5889, 7392.0), (0.0, 0.0, 1.685404)), str(bed))])
    assert (round(x), round(y), z, rot) == (2257, 2352, 7360.0, marker[1])


def test_skeleton_box_top_lowered_and_bottom_kept():
    """Vanilla skeleton.nif's BSBound (top 128) goes to a top of 115 with z 0 still its bottom; nothing else moves."""
    if not (FALLOUT4_DIR / 'Data' / 'Fallout4 - Meshes.ba2').exists():
        pytest.skip('needs Fallout 4')
    source = chr(92).join(p.lower() for p in S.FOLDER + ('skeleton.nif',))
    raw = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2').read(source)
    out = S.lowered(raw, S.BOX_TOP)
    block = next(b for kind, b in nf.read(out).blocks if kind == 'BSBound')
    cz, hz = struct.unpack_from('<6f', block, len(block) - S.BOX_SIZE)[2::3]
    assert (round(cz + hz, 3), round(cz - hz, 3)) == (S.BOX_TOP, 0.0)
    assert len(out) == len(raw) and sum(a != b for a, b in zip(out, raw)) <= 8
