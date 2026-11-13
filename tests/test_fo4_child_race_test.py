"""fo4_import.spike.child_race_test: the child race test plugin read back.

See: docs/fork/fo4_fo3_child_player.md#spike-test
"""

import struct

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.spike import child_race_test as T
from tes5_import.base.tes5_reader import subrecords, walk

#: Fallout4.esm's vanilla Pip-Boy armor.
PIPBOY = 0x21B3B


def test_object_ids_come_from_editor_ids_in_the_light_range():
    """Each record's object id is its EditorID's, distinct and inside 0x800-0xFFF."""
    ids = [T.object_id(e) for e in [T.RACE, T.TINTED, *T.COPIES.values()]]
    assert len(set(ids)) == len(ids) and all(0x800 <= i < 0x1000 for i in ids)
    assert T.own(T.RACE) == 0x01000000 | T.object_id(T.RACE)


def test_sections_cut_the_head_data_at_each_nam0():
    """Top, male and female head data, then the rest (SRAC)."""
    subs = [(b'EDID', b''), (b'NAM0', b''), (b'TETI', b''), (b'NAM0', b''), (b'MPGN', b''), (b'SRAC', b'')]
    assert [[t for t, _ in part] for part in T.sections(subs)] == [
        [b'EDID'], [b'NAM0', b'TETI'], [b'NAM0', b'MPGN'], [b'SRAC']]


def test_the_untinted_race_drops_tints_and_takes_the_morph_regions():
    """No tint subrecords or TINL; HumanRace's regions at each sex's end; the skin is ours."""
    child = [(b'EDID', b'x\0'), (b'WNAM', bytes(4)), (b'TINL', bytes(2)), (b'NAM0', b''), (b'TETI', b'1'),
             (b'MPGN', b'm\0'), (b'NAM0', b''), (b'TTGP', b'1'), (b'SRAC', b'')]
    human = [(b'NAM0', b''), (b'FMRI', b'a'), (b'NAM0', b''), (b'FMRI', b'b'), (b'SRAC', b'')]
    subs = T.child_race(child, human, T.RACE, False)
    assert [t for t, _ in subs] == [b'EDID', b'WNAM', b'NAM0', b'MPGN', b'FMRI', b'NAM0', b'FMRI', b'SRAC']
    assert subs[1][1] == struct.pack('<I', T.own(T.SKIN))
    assert [t for t, _ in T.child_race(child, human, T.TINTED, True)].count(b'TETI') == 1


def _read(path) -> dict:
    """{EditorID: (FormID, {tag: [data]})} of a written plugin."""
    out = {}
    for rec, _ in walk(path.read_bytes(), b'RACE', b'ARMA', b'ARMO'):
        subs = {}
        for tag, data in subrecords(rec.body):
            subs.setdefault(tag, []).append(data)
        out[subs[b'EDID'][0].rstrip(b'\0').decode()] = (rec.form_id, subs)
    return out


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout4.esm')
def test_the_written_plugin(tmp_path):
    """Two races (46 tint templates or none plus 64 morph regions), the body and suit drawing on both, the Pip-Boy."""
    recs = _read(T.build(tmp_path))
    races = {struct.pack('<I', T.own(T.RACE)), struct.pack('<I', T.own(T.TINTED))}
    race, tinted = recs[T.RACE][1], recs[T.TINTED][1]
    assert (len(race.get(b'TETI', [])), len(race[b'FMRI']), b'TINL' in race) == (0, 64, False)
    assert (len(tinted[b'TETI']), b'FMRI' in tinted) == (46, False)
    assert race[b'WNAM'] == tinted[b'WNAM'] == [struct.pack('<I', T.own(T.SKIN))]
    assert (race[b'FULL'], tinted[b'FULL']) == ([b'Player Child (no tints)\0'], [b'Player Child (tints)\0'])
    for edid in ('F3NV_NakedChildTorso', 'F3NV_NakedChildHands', 'F3NV_Vault81SuitChildAA'):
        assert races <= set(recs[edid][1][b'MODL'])
    assert set(recs[T.SKIN][1][b'MODL']) == {struct.pack('<I', T.own('F3NV_NakedChildTorso')),
                                             struct.pack('<I', T.own('F3NV_NakedChildHands'))}
    assert recs[T.SUIT][1][b'MODL'] == [struct.pack('<I', T.own('F3NV_Vault81SuitChildAA'))]
    aa = recs[T.PIPBOY_AA][1]
    assert aa[b'RNAM'] + aa[b'MODL'] == [struct.pack('<I', T.own(T.RACE)), struct.pack('<I', T.own(T.TINTED))]
    fid, pipboy = recs['Pipboy']
    assert fid == PIPBOY and pipboy[b'MODL'] == [struct.pack('<I', 0x1ED3D), struct.pack('<I', T.own(T.PIPBOY_AA))]
