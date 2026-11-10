"""Worn outfits on a hand-bumped version (outfit.OUTFIT_VERSION): the key follows the FNV body files, and two
reference outfits made cold keep their recorded results while the version stays.

See: docs/fork/fo4_build_speed.md#keys
"""

import functools

import pytest

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.nif import outfit
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import work_cache as WC
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.elric_cache import mesh_bytes
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike.statics import write_assets
from tests.fo4_versions import check

#: The FNV export the reference outfits come from, and those outfits (leather armor; a vault jumpsuit).
EXPORT = ROOT / 'export' / 'FalloutNV.esm'
REFERENCE_OUTFITS = ('ArmorLeatherReinforced', 'VaultSuit21')
SEXES = ('male', 'female')


def test_body_reads_follow_the_files_body_fit_reads(tmp_path, monkeypatch):
    """A body or head .egm replaced in the export changes body_reads; a file it does not read leaves it."""
    meshes = tmp_path / 'meshes'
    for model in (outfit.FNV_SKELETON, outfit.FNV_BODIES['male'], outfit.FNV_HEADS['male'],
                  outfit.FNV_HEADS['male'][:-4] + '.egm', 'characters\\_male\\other.nif'):
        path = meshes / model.replace('\\', '/').lower()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(model.encode())
    monkeypatch.setattr(outfit, 'asset_root', lambda export_dir, *parts: export_dir.joinpath(*parts))
    monkeypatch.setattr(outfit, 'export_file', lambda export_dir, *parts: export_dir.joinpath(*parts))
    before = outfit.body_reads(tmp_path, 'male')
    assert None not in dict(before).values()
    (meshes / 'characters' / '_male' / 'other.nif').write_bytes(b'changed')
    assert outfit.body_reads(tmp_path, 'male') == before
    (meshes / outfit.FNV_HEADS['male'][:-4].replace('\\', '/').lower()).with_suffix('.egm').write_bytes(b'new')
    assert outfit.body_reads(tmp_path, 'male') != before


@functools.cache
def _fit(sex: str):
    """outfit.body_fit() of `sex` from EXPORT, once."""
    return outfit.body_fit(EXPORT, sex)


def _worn(static: bytes, fnv_path, sex: str, first: bool) -> bytes:
    """outfit.worn() of one reference mesh on `sex`'s body fit."""
    return outfit.worn(static, fnv_path, _fit(sex), first)


def _references(rec: dict, data_dir) -> dict:
    """{name: (WORN_SITE key, maker)} of FNV outfit `rec`'s four worn meshes (each sex, each view)."""
    out = {}
    for sex in SEXES:
        model = rec.get(f'{sex.title()}.BipedModel.MODL') or rec['Male.BipedModel.MODL']
        path, _ = write_assets(EXPORT, model, data_dir, animated=False)
        static = mesh_bytes(data_dir / 'Meshes' / path)
        fnv_path = export_file(EXPORT, 'meshes', model.replace('\\', '/').lower())
        for first in (False, True):
            key = outfit.worn_key(static, fnv_path, sex, first, outfit.body_reads(EXPORT, sex))
            out[f'{rec["EditorID"]} {sex}{" 1st person" if first else ""}'] = (
                key, functools.partial(_worn, static, fnv_path, sex, first))
    return out


@pytest.mark.skipif(not (EXPORT / 'ARMO.txt').is_file() or not FALLOUT4_ESM.is_file(),
                    reason='needs the FNV export and Fallout 4')
def test_outfit_version_is_honest(tmp_path, monkeypatch):
    """REFERENCE_OUTFITS' worn meshes made cold (work and mesh caches under tmp_path) match their digests recorded
    under OUTFIT_VERSION (tests/fo4_versions.py)."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'meshes')
    recs = {r['EditorID']: r for r in export_records(EXPORT, 'ARMO') if r['EditorID'] in REFERENCE_OUTFITS}
    refs = {name: ref for edid in REFERENCE_OUTFITS for name, ref in _references(recs[edid], tmp_path).items()}
    check(outfit.WORN_SITE, outfit.OUTFIT_VERSION, refs)
