"""FNV add-ons map to Fallout4.esm's by EditorID; ambient smoke with no namesake takes its stand-in.

See: docs/fork/fo4_pipeline.md#addons
"""
from fo4_import.nif import addons as AD


def test_smoke_takes_its_stand_in_and_an_unmatched_addon_is_left_out(monkeypatch):
    """Fire by name, both smokes as MPSSmokeFireMed01, an add-on with neither left out."""
    fnv = [{'DATA.Index': '0', 'EditorID': 'MPSFireMed01'}, {'DATA.Index': '2', 'EditorID': 'MPSSmokeMed01'},
           {'DATA.Index': '35', 'EditorID': 'MPSSmokeSmall01'}, {'DATA.Index': '16', 'EditorID': 'NVFiregomorrah02'}]
    monkeypatch.setattr(AD, 'export_records', lambda _dir, _sig: fnv)
    monkeypatch.setattr(AD, '_fo4_by_name', lambda: {'MPSFireMed01': 5, 'MPSSmokeFireMed01': 6})
    AD.addon_map.cache_clear()
    assert AD.addon_map('x') == {0: 5, 2: 6, 35: 6}
    AD.addon_map.cache_clear()
