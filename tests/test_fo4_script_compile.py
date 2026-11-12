"""Converted FNV scripts that failed to compile (NVWillow.esp): each now converts to Papyrus that types its values.

See: docs/fork/fo4_script_compile.md
"""

import pytest

from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from script_convert.target import FALLOUT4, TARGET_ENV


@pytest.fixture
def fallout4(monkeypatch):
    """Emit Fallout 4 Papyrus for the test."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)


def _fallout_conv(records=()):
    """A converter whose graph reads as FO3/FNV and knows `records` [(FormID, EditorID, type)]."""
    xref = CrossRefGraph()
    xref.is_fallout = lambda: True
    for fid, edid, rtype in records:
        xref.edid_to_formid[edid.lower()] = fid
        xref.formid_to_edid[fid] = edid
        xref.record_type[fid] = rtype
    return ScriptConverter(xref)


def test_a_ref_set_to_an_item_count_is_an_int(fallout4):
    """`ref n` / `set n to Box.GetItemCount Caps001` declares n an Int, so the count fits.

    See: docs/fork/fo4_script_compile.md#ref-as-number
    """
    src = 'scn T\nref n\nbegin GameMode\n  set n to Box.GetItemCount Caps001\n  if n > 3\n    set n to 0\n  endif\nend\n'
    out = _fallout_conv().convert_standalone('T', src, 'ObjectReference', 'T')
    assert 'Int Property n Auto' in out and 'ObjectReference Property n ' not in out


def test_a_ref_another_script_sets_to_a_count_is_an_int(tmp_path):
    """A dialogue result script's `set Quest.n to Box.GetItemCount Caps001` types the quest's `ref n` Int.

    See: docs/fork/fo4_script_compile.md#ref-as-number
    """
    def record(sig, edid, field, text):
        """One export record whose `field` holds `text`."""
        return f'---RECORD_BEGIN---\nSignature={sig}\nFormID=01000001\nEditorID={edid}\n{field}={text}\n---RECORD_END---\n'

    (tmp_path / 'SCPT.txt').write_text(record('SCPT', 'QScript', 'SCTX', r'scn QScript\r\nref n\r\nref r\r\n'),
                                       encoding='utf-8')
    (tmp_path / 'INFO.txt').write_text(record('INFO', '', 'ResultScript',
                                              r'If 1\r\n\tSet QScript.n to Box.GetItemCount Caps001\r\nEndif'
                                              r'\r\nSet QScript.r to Box'),
                                       encoding='utf-8')
    xref = CrossRefGraph()
    xref.build_ref_as_int_map(str(tmp_path / 'SCPT.txt'))
    assert ('qscript', 'n') in xref.ref_as_int and ('qscript', 'r') not in xref.ref_as_int


def test_a_region_written_in_other_case_is_its_global(fallout4):
    """`IsPlayerInRegion vMapFooregion` declares the region's EditorID (vMapFooRegion) as one GlobalVariable."""
    src = 'scn T\nbegin GameMode\n  if IsPlayerInRegion vMapFooregion == 0\n    Disable\n  endif\nend\n'
    out = _fallout_conv([('01000002', 'vMapFooRegion', 'REGN')]).convert_standalone('T', src, 'ObjectReference', 'T')
    assert 'GlobalVariable Property vMapFooRegion' in out and 'ObjectReference Property vMapFoo' not in out
    assert 'TES4Polyfill.InRegion(vMapFooRegion)' in out


def test_nvse_version_reads_as_the_xnvse_the_build_stands_in_for(fallout4):
    """`GetNVSEVersion < 2` (a mod warning that NVSE is missing) reads xNVSE 6, never an undefined name.

    See: docs/fork/fo4_script_compile.md#nvse-version
    """
    src = 'scn T\nbegin GameMode\n  if GetNVSEVersion < 2\n    Disable\n  endif\nend\n'
    out = _fallout_conv().convert_standalone('T', src, 'ObjectReference', 'T')
    assert '6 < 2' in out and 'GetNVSEVersion' not in out.split('EndEvent')[0].split('Event OnUpdate')[-1]


def test_a_bare_cell_compared_to_zero_is_compared_to_none(fallout4):
    """`NovacRoom == 0` on a cell nothing registered yet compares the Cell property to None.

    See: docs/fork/fo4_script_compile.md#record-compared-to-zero
    """
    src = 'scn T\nshort n\nbegin GameMode\n  if NovacRoom == 0 && n == 0\n    Disable\n  endif\nend\n'
    out = _fallout_conv([('01000003', 'NovacRoom', 'CELL')]).convert_standalone('T', src, 'ObjectReference', 'T')
    assert 'If NovacRoom == None && n == 0' in out
