"""Super mutants' additive subgraph race for FNV weapons (fo4_import.spike.mutant_subgraphs)."""

import struct

import pytest

from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.gun_clips import HUMAN_SUBGRAPHS, ROLE_WEAPON, subgraph_entries
from fo4_import.spike import mutant_subgraphs as M
from tes5_import.base.tes5_reader import first_sub, subrecords, walk

FALLOUT4_ESM = FALLOUT4_DIR / 'Data' / 'Fallout4.esm'
WEAPON = struct.pack('<HH', ROLE_WEAPON, 0)


def _entry(target: list, actor: list = ()) -> dict:
    return {'actor': list(actor), 'graph': 'Actors\\Character\\Behaviors\\WeaponBehavior.hkx',
            'paths': ['Actors\\SuperMutant\\Animations\\Rifle'], 'target': target, 'flags': WEAPON}


def test_an_own_keyword_takes_its_class_entries_with_their_crippled_variants_aimed_at_it_alone():
    """Keyword 0x99 holding like class 1 copies both of class 1's entries (one a crippled-arm variant), each
    targeting 0x99 only; class 2's entry and an unmapped class add nothing."""
    entries = [_entry([1]), _entry([1, 5], actor=[7]), _entry([2])]
    out = M.mutant_entries(entries, {0x99: 1, 0x98: 3})
    assert [(e['actor'], e['target']) for e in out] == [([], [0x99]), ([7], [0x99])]
    assert out[0]['paths'] == entries[0]['paths'] and entries[0]['target'] == [1]


def test_a_flamer_on_fnvs_clips_holds_like_the_minigun_and_vanillas_bat_keyword_only_in_the_base_game():
    """A gun's own keyword over AnimsFlamer maps to AnimsMinigun, one over AnimsHuntingRifle to itself; the
    vanilla AnimsFlamer and Anims2hmWeapon are mapped only when `vanilla` (a DLC build maps its own keywords)."""
    kw = {'AnimsFlamer': 1, 'AnimsMinigun': 2, 'AnimsHuntingRifle': 3, 'Anims2hmWeapon': 4, 'Anims2hmWideWeapon': 5}
    replaced = {0x100: 1, 0x101: 3}
    assert M.keyword_classes(replaced, kw, False) == {0x100: 2, 0x101: 3}
    assert M.keyword_classes(replaced, kw, True) == {0x100: 2, 0x101: 3, 1: 2, 4: 5}


@pytest.mark.skipif(not FALLOUT4_ESM.exists(), reason='needs Fallout 4')
def test_fnvs_sledges_and_flamers_get_super_mutant_entries_in_a_race_added_to_supermutantrace():
    """Every NEAREST keyword is Fallout4.esm's and its class keys SuperMutantRace entries (else the table names a
    keyword the engine never matches); the written race reads back with SADD on SuperMutantRace and every copy."""
    fo4 = FALLOUT4_ESM.read_bytes()
    keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id for r, _ in walk(fo4, b'KYWD')}
    races = {r.form_id: list(subrecords(r.body)) for r, _ in walk(fo4, b'RACE')
             if r.form_id in (M.SUPER_MUTANT, HUMAN_SUBGRAPHS)}
    entries = M.weapon_entries(races[M.SUPER_MUTANT])
    classes = M.keyword_classes({}, keywords, True)
    assert set(classes) == {keywords[k] for k in M.NEAREST}
    for name, cls in M.NEAREST.items():
        copies = M.mutant_entries(entries, {keywords[name]: keywords[cls]})
        assert copies and all(e['target'] == [keywords[name]] for e in copies), name
    added = M.mutant_entries(entries, classes)
    subs = M.additive_race('Test', races[HUMAN_SUBGRAPHS], added)
    assert [struct.unpack('<I', b)[0] for s, b in subs if s == b'SADD'] == [M.SUPER_MUTANT]
    assert [e['target'] for e in subgraph_entries(subs)] == [e['target'] for e in added]
    assert next(b for s, b in subs if s == b'EDID') == b'Test\0'
