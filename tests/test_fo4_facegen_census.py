"""The FaceGen census tool: finding the CK's FaceGeom files, the worst part per NPC, and the summary.

See: docs/fork/fo4_facegen_plan.md#sculpt-census
"""

from tools.nif import facegen_census as FC


def test_ck_files_are_the_plugins_folder_with_local_ids(tmp_path):
    """The plugin's folder is found whatever its case; file names give local ids (load index dropped)."""
    folder = tmp_path / 'Meshes' / 'FaceGenData' / 'FaceGeom' / 'FALLOUTNV.ESM'
    folder.mkdir(parents=True)
    (folder / '0108C462D.nif').write_bytes(b'')
    (folder / '0000ABCD.nif').write_bytes(b'')
    assert [form for form, _ in FC.ck_files(tmp_path, 'FalloutNV.esm')] == [0xABCD, 0x8C462D]
    assert FC.ck_files(tmp_path, 'Other.esp') == []


def test_ck_files_finds_face_diffuses_by_their_id_prefix(tmp_path):
    """In --textures mode the FaceCustomization _d files are found, their id read from the name before '_'."""
    folder = tmp_path / 'Textures' / 'FaceCustomization' / 'FalloutNV.esm'
    folder.mkdir(parents=True)
    for name in ('0108C462D_d.dds', '0108C462D_msn.dds', '0000ABCD_d.dds'):
        (folder / name).write_bytes(b'')
    found = FC.ck_files(tmp_path, 'falloutnv.esm', 'FaceCustomization', '*_d.dds')
    assert [form for form, _ in found] == [0xABCD, 0x8C462D]


def test_texture_summary_prints_spread_worst_and_errors(capsys):
    """Per texture kind: the spread of per-NPC means and the worst first; then the errors."""
    lines = [{'form': '000001', 'edid': 'A', 'female': True, 'd': [2.0, 9.0], 'msn': [1.0, 4.0], 's': [5.0, 8.0]},
             {'form': '000002', 'edid': 'B', 'female': False, 'd': [3.0, 12.0], 'msn': [0.5, 2.0], 's': [1.0, 3.0]},
             {'form': '000003', 'error': 'KeyError: x'}]
    FC.texture_summary(lines)
    out = capsys.readouterr().out
    assert 'NPCs 3, errors 1' in out and '_d: measured 2' in out and 'worst 3.00' in out and 'worst 5.00' in out
    d, msn = out.index('_d:'), out.index('_msn:')
    assert d < out.index('000002 B M', d) < out.index('000001 A F', d) < msn and 'error 000003' in out


def test_worst_part_skips_status_rows_and_the_summary_prints(capsys):
    """A part whose row is a status text is not measured; the summary counts it and lists the worst NPC."""
    line = {'form': '000001', 'edid': 'A', 'race': 'R',
            'parts': {'Head': [10, 0.04, 0.01, 0.3, True], 'Hair': [5, 0.2, 0.05, 0.2, False],
                      'Beard': 'not in the CK file'}}
    assert FC.worst_part(line) == (0.2, 'Hair') and FC.worst_part({'form': '2', 'parts': {}}) == (-1.0, '')
    FC.summary([line, {'form': '000002', 'error': 'KeyError: x'}])
    out = capsys.readouterr().out
    assert "errors 1, measured 1; part statuses {'not in the CK file': 1}" in out and '000001 A (R) Hair' in out
