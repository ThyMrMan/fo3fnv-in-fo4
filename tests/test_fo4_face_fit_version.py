"""The face fits' version is honest: six reference faces, fitted as a build's worker process fits them, give what
is recorded under FIT_VERSION; and a face warm_faces keeps is the one the serial pass reads.

See: docs/fork/fo4_build_speed.md#faces
"""

import functools

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import tint
from fo4_import.pipeline import work_cache
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import face_fits as F
from fo4_import.spike import npcs as N
from tests import fo4_versions as V
from tests.test_fo4_faces_audit import EXPORT, _fail, _npcs

#: The reference faces by FNV EditorID: three men, three women, with and without brows, beards and hair.
REFERENCES = ('DocMitchell', 'GSEasyPete', 'GSChet', 'GSSunnySmiles', 'NellisPearl', 'Veronica')
needs_game = pytest.mark.skipif(
    not (EXPORT / 'NPC_.txt').exists() or not FALLOUT4_ESM.exists() or not tint.basis_path(True).exists()
    or not tint.basis_path(False).exists(), reason='needs the FNV export, Fallout4.esm and the bases')


def written(fits: tuple, female: bool) -> tuple:
    """What a record takes from a face's three fits (FIT_SITES' order): the sculpt controls as stored, the tint
    layers as packed, the skin tone scale to six places, the head parts chosen. Two fits that write the same
    record are one result, whatever rounding in their last places the BLAS build or thread count left."""
    (morphs, _), (values, tone, _), chosen = fits
    _, options, _, brows = tint.load_basis(female)
    parts = {name: getattr(chosen, name) for name in F.HEAD_FORMS}
    return morphs, tint.pack_layers(options, values, b'', brows), [round(float(t), 6) for t in tone], parts


@pytest.fixture(scope='module')
def pooled(tmp_path_factory):
    """(Npcs over the export, {EditorID: (NPC record, female, fit_key, its three fits)}) of REFERENCES, fitted by
    warm_faces in a worker process into an empty work cache, which stays the work cache for the module."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(work_cache, 'CACHE', tmp_path_factory.mktemp('faces') / 'work')
        npcs = _npcs({int(r['FormID'], 16): r for r in export_records(EXPORT, 'NPC_')})
        records = {r['EditorID']: r for r in npcs.records.values() if r.get('EditorID') in REFERENCES}
        assert npcs.warm_faces([int(records[edid]['FormID'], 16) for edid in REFERENCES], workers=1) == len(REFERENCES)
        faces = {}
        for edid in REFERENCES:
            female = bool(int(records[edid].get('ACBS.Flags', 0)) & N.FEMALE)
            key = F.fit_key(EXPORT, records[edid], female)
            faces[edid] = (records[edid], female, key, tuple(F.kept(i, key) for i in range(len(F.FIT_SITES))))
        yield npcs, faces


@needs_game
def test_the_fit_version_is_bumped_when_a_reference_face_changes(pooled):
    """REFERENCES' fits, as records take them, are those recorded under FIT_VERSION."""
    V.check('face_fits', F.FIT_VERSION, {edid: (key, functools.partial(written, fits, female))
                                         for edid, (_, female, key, fits) in pooled[1].items()})


@needs_game
def test_warm_faces_keeps_what_the_serial_fit_makes(pooled, monkeypatch, tmp_path):
    """A face fitted in a worker process (one BLAS thread) is kept under the key the serial pass reads, which then
    fits nothing; fitted here instead (any thread count), it writes the same record."""
    npcs, faces = pooled
    npc, female, _, fits = faces['DocMitchell']
    assert npcs.warm_faces([int(npc['FormID'], 16)], workers=1) == 0
    with monkeypatch.context() as patch:
        for name in ('sculpt_fit', 'tint_fit', 'choose'):
            patch.setattr(N, name, _fail)
        assert F.same(N.fit_face(EXPORT, npc, female, None), fits)
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'serial')
    npcs.builder.fo4 = FALLOUT4_ESM.read_bytes()
    assert V.digest(written(N.fit_face(EXPORT, npc, female, npcs._head_assets()), female)) == V.digest(
        written(fits, female))
