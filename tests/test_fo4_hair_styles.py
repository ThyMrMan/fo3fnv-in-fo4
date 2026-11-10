"""An FNV hair narrows the FO4 hairs coverage picks from: its name's match of the NPC's sex, else its style group.

See: docs/fork/fo4_spikes.md#hair-styles
"""

import json

import pytest

from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face import hair, hair_styles
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.npcs import head_assets

EXPORT = 'export/FalloutNV.esm'
#: {FormID: (EditorID, name, female)} of the stubbed FO4 hairs.
PARTS = {1: ('HairMale17', 'Shaved', False), 2: ('HairMale37', 'Crop', False),
         3: ('HairMale22', 'Blast Back', False), 4: ('HairFemale05', 'Blast-Back', True),
         5: ('HairFemale19', 'Shaved F', True)}


class _Assets:
    """Fo4Assets' name, EditorID and candidate lookups over PARTS."""

    def __init__(self):
        self.parts = {f: {b'FULL': [f.to_bytes(4, 'little')]} for f in PARTS}

    def edid(self, form_id):
        return PARTS[form_id][0]

    def candidates(self, _kind, female):
        return [f for f, (_, _, sex) in PARTS.items() if sex == female]


@pytest.fixture
def assets(monkeypatch):
    """Stubbed assets, their names in the Fallout4.esm string table."""
    monkeypatch.setattr(hair_styles.strings, 'fallout4', lambda: {f: n.encode() for f, (_, n, _) in PARTS.items()})
    return _Assets()


def test_name_match_keeps_sex(assets):
    """A name shared across sexes gives each sex its own hair, punctuation ignored."""
    record = {'EditorID': 'HairRaiderMid', 'FULL': 'Blast Back'}
    assert hair_styles.candidates(assets, record, False) == ([3], 'name')
    assert hair_styles.candidates(assets, record, True) == ([4], 'name')


def test_style_group_without_name(assets):
    """Kilborn's crop, named in FNV only, keeps to the crop group."""
    record = {'EditorID': 'HairAfricanAmericanBase', 'FULL': 'Short'}
    assert hair_styles.candidates(assets, record, False) == ([2], 'style')


def test_coverage_when_neither(assets):
    """A hair in neither rule leaves every hair of its sex to coverage."""
    assert hair_styles.candidates(assets, {'EditorID': 'Unknown', 'FULL': 'Odd'}, True) == ([4, 5], 'coverage')


def test_best_part_keeps_to_among(monkeypatch):
    """best_part picks the nearest of `among`, even when another part is nearer."""
    drawn = [(hair.np.zeros(4), 1), (hair.np.ones(4), 2)]
    monkeypatch.setattr(hair, 'part_coverages', lambda *_: drawn)
    assert hair.best_part(None, hair.HAIR, False, hair.np.zeros(4), [])[0] == 1
    assert hair.best_part(None, hair.HAIR, False, hair.np.zeros(4), [], among=[2])[0] == 2


@pytest.mark.skipif(not (FALLOUT4_DIR / 'Data' / 'Fallout4.esm').exists(), reason='no Fallout 4 install')
def test_table_names_real_hairs():
    """Every group member is an FO4 playable hair; every styled FNV hair exists."""
    real = head_assets((FALLOUT4_DIR / 'Data' / 'Fallout4.esm').read_bytes())
    playable = {real.edid(f) for sex in (False, True) for f in real.candidates(hair.HAIR, sex)}
    data = json.loads(hair_styles.TABLE.read_text(encoding='utf-8'))
    assert {e for ids in data['groups'].values() for e in ids} <= playable
    assert set(data['styles'].values()) <= set(data['groups'])
    fnv = {h['EditorID']: h for h in export_records(EXPORT, 'HAIR')}
    assert set(data['styles']) <= set(fnv)
