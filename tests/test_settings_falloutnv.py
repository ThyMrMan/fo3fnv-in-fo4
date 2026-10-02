"""FO3/FNV game settings: the exe's defaults, overridden by the plugin's GMSTs, read by NPC health."""

import pytest

from tes5_import.record_types import settings_falloutnv, world_falloutnv
from tes5_import.record_types.actors_falloutnv import npc_health


@pytest.fixture
def fallout3(tmp_path, monkeypatch):
    """An FO3 export header and the Fallout source flag, unset again afterwards."""
    (tmp_path / '_HEADER.txt').write_text('HEDR.Version=0.94\n', encoding='utf-8')
    monkeypatch.setattr(world_falloutnv, '_IS_FALLOUT_SOURCE', True)
    yield str(tmp_path)
    settings_falloutnv._SETTINGS.clear()


def test_a_plugin_setting_overrides_the_exe_default(fallout3):
    """Fallout3.exe's fAVDNPCHealthLevelMult is 20; Fallout3.esm's GMST makes it 5."""
    settings_falloutnv.load_fallout_settings({}, None, fallout3)
    assert settings_falloutnv.setting('fAVDNPCHealthLevelMult') == 20.0
    gmst = {'GMST': [{'EditorID': 'fAVDNPCHealthLevelMult', 'DATA.Value': '5.0'}]}
    settings_falloutnv.load_fallout_settings(gmst, None, fallout3)
    assert settings_falloutnv.setting('fAVDNPCHealthLevelMult') == 5.0
    assert settings_falloutnv.setting('iActivatePickLength') == 150


def test_npc_health_reads_the_settings(fallout3):
    """Base 50 + Endurance 6 x 5 + (level 3 - 1) x 5 under Fallout3.esm's settings."""
    gmst = {'GMST': [{'EditorID': 'fAVDNPCHealthLevelMult', 'DATA.Value': '5.0'}]}
    settings_falloutnv.load_fallout_settings(gmst, None, fallout3)
    npc = {'DATA.BaseHealth': '50', 'DATA.Endurance': '6', 'ACBS.Level': '3', 'ACBS.Flags': '0'}
    assert npc_health(npc) == 90
