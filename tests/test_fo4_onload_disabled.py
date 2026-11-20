"""OnLoad skips a disabled reference except on a trigger box, and the xref knows which bases are trigger boxes.

See: docs/fork/fo4_pipeline.md#onload-disabled
"""
from script_convert import target
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph

SOURCE = 'scn T\nshort b\nbegin OnLoad\n  set b to 1\nend\n'


def placed(formid: str, base: str, trigger: bool = False) -> list:
    """Export lines of a placed reference of `base`, with a primitive when `trigger`."""
    return [f'FormID={formid}', f'NAME={base}'] + (['XPRM.BoundX=100.0'] if trigger else [])


def export_file(folder, sig: str, records: list) -> None:
    """Writes `records` (each its KEY=VALUE lines) as `folder`/`sig`.txt."""
    text = ''.join('---RECORD_BEGIN---\nSignature=%s\n%s\n---RECORD_END---\n' % (sig, '\n'.join(lines))
                   for lines in records)
    (folder / f'{sig}.txt').write_text(text, encoding='utf-8')


def graph(tmp_path, *refs: list) -> CrossRefGraph:
    """A graph of an export holding script T (00000800) on base 00000900, placed by `refs`."""
    export_file(tmp_path, 'SCPT', [['FormID=00000800', 'EditorID=T', 'SCHR.Type=0']])
    export_file(tmp_path, 'ACTI', [['FormID=00000900', 'EditorID=TBase', 'SCRI=00000800']])
    export_file(tmp_path, 'REFR', list(refs))
    xref = CrossRefGraph()
    xref.load_from_export(str(tmp_path), workers=1)
    return xref


def converted(monkeypatch, xref: CrossRefGraph) -> str:
    """SOURCE converted for Fallout 4 against `xref`."""
    monkeypatch.setenv(target.TARGET_ENV, target.FALLOUT4)
    return ScriptConverter(xref).convert_standalone('T', SOURCE, 'ObjectReference', 'T')


def test_a_placed_primitive_marks_its_base_a_trigger_box(tmp_path):
    """Only a reference with XPRM makes its base a trigger base."""
    xref = graph(tmp_path, placed('00000A00', '00000900'), placed('00000A01', '00000A99', trigger=True))
    assert xref.trigger_bases == {'00000A99'}


def test_onload_runs_only_on_an_enabled_reference(monkeypatch, tmp_path):
    """The source's OnLoad body waits for the enable."""
    out = converted(monkeypatch, graph(tmp_path, placed('00000A00', '00000900')))
    assert 'If !IsDisabled()' in out


def test_a_trigger_boxs_onload_runs_disabled_too(monkeypatch, tmp_path):
    """A disabled trigger box runs its OnLoad in the source, so it keeps no guard."""
    out = converted(monkeypatch, graph(tmp_path, placed('00000A00', '00000900', trigger=True)))
    assert 'IsDisabled()' not in out
