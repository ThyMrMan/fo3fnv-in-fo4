"""FalloutHelpers.esl: fixed ids in the light-plugin range, and the names converted scripts resolve through it.

See: docs/fork/fo4_spikes.md#spike-3-helper-plugin
"""

import struct
from pathlib import Path

from fo4_import import helpers_plugin as H
from script_convert import target
from script_convert.constants import (FALLOUT4_HELPER_AVS, FALLOUT4_HELPER_GLOBALS, FALLOUT4_HELPER_MESSAGES,
                                      FALLOUT4_HELPER_QUESTS, FALLOUT4_TRACE_PLUGIN)
from script_convert.helpers_fallout4 import av_function
from tes5_import.base.tes5_reader import walk


def test_ids_are_unique_and_fit_a_light_plugin():
    """Every object id is distinct and inside an ESL's 0x800-0xFFF."""
    ids = [*FALLOUT4_HELPER_AVS.values(), *FALLOUT4_HELPER_QUESTS.values(), *FALLOUT4_HELPER_GLOBALS.values()]
    assert len(ids) == len(set(ids))
    assert all(0x800 <= i <= 0xFFF for i in ids)


def test_plugin_is_a_light_master_with_every_record(tmp_path):
    """ESM and ESL flags set; one record per table entry at its fixed id."""
    out = tmp_path / 'FalloutHelpers.esl'
    H.build(out)
    raw = out.read_bytes()
    assert struct.unpack_from('<I', raw, 8)[0] & 0x201 == 0x201
    got = {(r.sig, r.form_id & 0xFFFFFF) for r, _ in walk(raw)}
    assert (b'AVIF', FALLOUT4_HELPER_AVS['Variable01']) in got
    assert (b'QUST', FALLOUT4_HELPER_QUESTS['F3NV_PlayerControls']) in got
    assert (b'GLOB', FALLOUT4_HELPER_GLOBALS['TES4ControlsDisabled']) in got
    assert (b'MESG', FALLOUT4_HELPER_MESSAGES['TES4ChooseSexMessage'][0]) in got
    assert len(got) == (len(FALLOUT4_HELPER_AVS) + len(FALLOUT4_HELPER_QUESTS) + len(FALLOUT4_HELPER_GLOBALS)
                        + len(FALLOUT4_HELPER_MESSAGES))


def test_the_trace_switch_is_an_empty_light_plugin_tracing_names(tmp_path):
    """F3NV_Trace.esl holds no record and no master, so enabling it costs no load-order slot; Tracing() checks
    for that file by name."""
    out = tmp_path / FALLOUT4_TRACE_PLUGIN
    H.build_trace_switch(out)
    raw = out.read_bytes()
    assert struct.unpack_from('<I', raw, 8)[0] & 0x201 == 0x201
    assert not list(walk(raw)) and b'MAST' not in raw
    polyfill = (Path(H.__file__).parents[1] / 'script_convert' / 'static_scripts' / 'fallout4' / 'overrides'
                / 'TES4Polyfill.psc').read_text(encoding='utf-8')
    assert f'Game.IsPluginInstalled("{FALLOUT4_TRACE_PLUGIN}")' in polyfill


def test_actor_values_resolve_in_any_case_and_by_skyrim_alias():
    """variable01 and Smithing find the helper records; Health stays Fallout4.esm's."""
    assert H.actor_value_form('variable01', 2) == 0x02000800
    assert H.actor_value_form('Smithing', 2) == 2 << 24 | FALLOUT4_HELPER_AVS['Repair']
    assert H.actor_value_form('Health', 2) == 0x2D4
    assert H.actor_value_form('NoSuchValue', 2) is None


def test_fallout4_target_keeps_fallout_skill_names(monkeypatch):
    """Only on Fallout 4, an FO3/FNV skill resolves to the helper plugin's own name."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    assert target.fallout4_av_name('energyweapons') == 'EnergyWeapons'
    assert target.fallout4_av_name('Health') is None
    monkeypatch.setenv(target.TARGET_ENV, target.SKYRIM)
    assert target.fallout4_av_name('energyweapons') is None


def test_av_function_reads_helper_values_from_the_helper_plugin():
    """Generated AV(): helper plugin by default, Fallout4.esm for vanilla."""
    text = '\n'.join(av_function())
    assert f'String file = "{H.FALLOUT4_HELPER_PLUGIN}"' in text
    assert 'asName == "variable01"' in text and 'file = "Fallout4.esm"' in text
