"""Published face fits: the file carries only numbers and FormIDs, round-trips each fit byte for byte, and a build
takes a face from it only when the fit code and its sex's basis match.

See: docs/fork/fo4_pipeline.md#published-face-fits
"""

import collections
from types import SimpleNamespace

import numpy as np
import pytest

from fo4_import.face import sculpt
from fo4_import.pipeline import work_cache
from fo4_import.spike import face_fits as F
from fo4_import.spike import npcs as N
from fo4_import.spike.head_parts import HeadChoice
from tes5_import.base.writer import pack_subrecord

NPC = {'FormID': '00000801', 'EditorID': 'Npc801', 'RNAM.Race': '00000019', 'FGGS': 'ab cd', 'HCLR.R': '12'}
#: Work-cache keys of two faces as fit_key builds them: fields, head parts, the two basis files.
KEY, OTHER = ('ab cd', (('EyebrowM', 'brow.nif'),), b'sculpt', b'tint'), ('ef', (), b'sculpt', b'tint')


def _fits() -> tuple:
    """A face's three fits as the work cache holds them: sculpt (FMRI/FMRS, captured NaN), tint, head parts."""
    morphs = sculpt.face_morphs([0, 1, 7], np.array([[0.5, -0.25, 0, 0, 0, 0, 1 / 3]] * 3), all_regions=True)
    tinted = (np.array([0.1, 0.0, 2 / 3]), np.array([1.0, 0.9, 0.8]), 0.75)
    chosen = HeadChoice(hair=0x1411C7, facial_hair=None, eyes=0x2B2B6, colour=0x19EE67,
                        distances={'hair': 0.15677014877103143}, unmapped=['FNVHeadPartEdid'])
    return (morphs, -float('nan')), tinted, chosen


@pytest.fixture
def machine(monkeypatch, tmp_path):
    """This machine: an empty work cache, a fit code and both sexes' basis hashes, nothing installed."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(F, 'INSTALLED', tmp_path / 'face_fits.json.gz')
    monkeypatch.setattr(F, 'fit_code', lambda: 'code')
    monkeypatch.setattr(F, 'basis_hash', lambda female: f'basis {female}')
    F.installed.cache_clear()
    yield tmp_path
    F.installed.cache_clear()


def test_a_fit_survives_the_file_byte_for_byte_but_its_fnv_editor_ids():
    """Each fit decodes to what the work cache held (a NaN's sign aside); head parts lose only `unmapped`."""
    fits = _fits()
    decoded = F.decode(F.encode(fits))
    assert decoded[0][0] == fits[0][0] and np.isnan(decoded[0][1])
    assert F.same(decoded[1], fits[1])
    assert decoded[2] == HeadChoice(**{**fits[2].__dict__, 'unmapped': []})


def test_same_is_to_the_bit():
    """-0.0 != 0.0, NaN == -NaN, float32 != float64, key order counts."""
    assert not F.same(-0.0, 0.0) and F.same(float('nan'), -float('nan'))
    assert not F.same(np.zeros(2, np.float32), np.zeros(2))
    assert not F.same({'a': 1, 'b': 2}, {'b': 2, 'a': 1})


def test_a_sculpt_fit_holding_other_bytes_is_refused():
    """Only FMRI/FMRS pairs encode, so no other record bytes can reach the file."""
    morphs = pack_subrecord('FMRI', bytes(4)) + pack_subrecord('MODL', b'meshes\\head.nif\0')
    with pytest.raises(ValueError):
        F.encode_sculpt((morphs, 1.0))


@pytest.mark.parametrize('entry', [
    [[[0, ['x'] * 7], 1.0], None, None],
    [None, [[0.1], [1.0], '0.5'], None],
    [None, None, {'hair': 1, 'facial_hair': None, 'eyes': None, 'colour': None, 'distances': {}, 'unmapped': ['a']}],
    [None, None, {'hair': -1, 'facial_hair': None, 'eyes': None, 'colour': None, 'distances': {}}],
])
def test_a_file_with_anything_but_numbers_where_numbers_go_does_not_read(entry):
    """A string for a number, an unknown head part field, a negative FormID: no decode."""
    with pytest.raises((ValueError, TypeError)):
        F.decode(entry)


def test_the_file_is_the_same_bytes_every_time(machine):
    """Writing the same faces twice gives the same file (no gzip time), keyed by sex and face_id."""
    faces = {'male': {F.face_id(KEY): F.encode(_fits())}, 'female': {}}
    F.write(machine / 'a.gz', faces)
    F.write(machine / 'b.gz', faces)
    assert (machine / 'a.gz').read_bytes() == (machine / 'b.gz').read_bytes()
    assert F.read(machine / 'a.gz')['bases'] == {'male': 'basis False', 'female': 'basis True'}


def test_a_build_takes_a_face_only_with_the_same_code_and_basis(machine, monkeypatch):
    """take() stores the file's fits under the local key when code and basis match; else it says why not."""
    assert F.take(False, KEY, [0, 1, 2]) == (False, 'faces fitted locally (published fits: none installed)')
    F.write(F.INSTALLED, {'male': {F.face_id(KEY): F.encode(_fits())}, 'female': {}})
    F.installed.cache_clear()
    assert F.take(False, KEY, [1, 2]) == (True, F.TAKEN)
    assert work_cache.lookup(*F.FIT_SITES[0], KEY) is None
    assert F.same(work_cache.lookup(*F.FIT_SITES[1], KEY), _fits()[1])
    assert F.take(False, OTHER, [0])[1].endswith('face not in file)')
    monkeypatch.setattr(F, 'basis_hash', lambda female: 'recalibrated')
    assert F.take(False, KEY, [0])[1].endswith('male basis differs)')
    monkeypatch.setattr(F, 'fit_code', lambda: 'edited')
    assert F.take(False, KEY, [0])[1].endswith('fit code differs)')


def test_one_facegen_with_other_head_parts_is_another_face(monkeypatch):
    """Two NPCs sharing every FIT_FIELDS value but not their FNV head parts get their own keys and file ids."""
    parts = {0x801: [('EyebrowM', 'brow.nif')], 0x802: [('EyebrowM', 'brow.nif'), ('Beard', 'beard.nif')]}
    monkeypatch.setattr(F, 'bases', lambda female: (b'sculpt', b'tint'))
    monkeypatch.setattr(F, 'head_parts', lambda export_dir, form_id: parts[form_id])
    one, two = (F.fit_key(None, {**NPC, 'FormID': f}, False) for f in ('00000801', '00000802'))
    assert one[:-3] == two[:-3] and one != two and F.face_id(one) != F.face_id(two)
    assert one[-3] == (('EyebrowM', 'brow.nif'),) and one[-2:] == (b'sculpt', b'tint')


def test_warm_faces_fits_none_the_published_file_gives(monkeypatch):
    """A face the installed file gives is counted and never sent to a worker process."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.export_dir, npcs.builder = None, SimpleNamespace(counts=collections.Counter())
    monkeypatch.setattr(npcs, '_faces', lambda fnvs: {1: (NPC, False)}, raising=False)
    monkeypatch.setattr(N, 'fit_key', lambda export_dir, npc, female: KEY)
    monkeypatch.setattr(N, 'lookup', lambda site, module, key, default: default)
    monkeypatch.setattr(N, 'take', lambda female, key, wanted: (True, F.TAKEN))
    monkeypatch.setattr(N, 'ProcessPoolExecutor', None)
    assert npcs.warm_faces([1]) == 0
    assert npcs.builder.counts == {F.TAKEN: 1}
