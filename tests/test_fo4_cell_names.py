"""The EditorID map filling Cell and WorldSpace script properties (cell._cell_names).

See: docs/fork/fo4_pipeline.md#worldspace-properties
"""

from types import SimpleNamespace

from fo4_import.base.source_ids import SourceIds
from fo4_import.base.ledger import LedgerWriter
from fo4_import.spike import cell as CB
from fo4_import.spike.cell import CellBuilder

FO4_MASTERS = ['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'FalloutNV.esm']
MASTER_RECORDS = {
    'WRLD': [{'FormID': '00000A00', 'EditorID': 'Lucky38World'}, {'FormID': '00000A01', 'EditorID': 'NotBuilt'},
             {'FormID': '01000900', 'EditorID': 'NVDLC04DivideWorld'}],
    'CELL': [{'FormID': '00000B00', 'EditorID': 'Lucky38Cell'}, {'FormID': '00000B01'}],
}


def _builder(in_masters):
    """A CellBuilder stand-in for a DLC build over FalloutNV.esm, its built master holding `in_masters`."""
    writer = LedgerWriter(masters=FO4_MASTERS, is_esm=True)
    builder = SimpleNamespace(ids=SourceIds(['FalloutNV.esm'], FO4_MASTERS, writer.own_index), writer=writer, top=0,
                              in_masters=in_masters, master_held=None)
    builder.fnv_id = lambda fid: CellBuilder.fnv_id(builder, fid)
    return builder


def _world(edid: str, fid: str):
    """A built worldspace stand-in: its WRLD record, no grid cells, persistent cell `fid` + 1."""
    return SimpleNamespace(world={'FormID': fid, 'EditorID': edid}, cells={},
                           persistent_cell=f'{int(fid, 16) + 1:08X}')


def test_a_built_worldspace_is_named_for_its_script_properties(monkeypatch):
    """A built worldspace's EditorID names its FO4 form, and it and its persistent cell are in `cell_ids`."""
    monkeypatch.setattr(CB, 'export_records', lambda export_dir, sig: ())
    builder = _builder(None)
    names = CB._cell_names(builder, 'OldWorldBlues', [], [_world('NVDLC03BigMT', '01000E81')])
    assert names == {'NVDLC03BigMT': builder.fnv_id('01000E81')}
    assert set(builder.cell_ids) == {0x01000E81, 0x01000E82}


def test_a_dlc_names_the_masters_worldspaces_and_cells_its_built_master_holds(monkeypatch):
    """A DLC build names the master's worldspace and cell the built master holds, under the master's FO4 FormID;
    one the master left out, a nameless cell and the DLC's own unbuilt worldspace are not named."""
    monkeypatch.setattr(CB, 'export_records', lambda export_dir, sig: MASTER_RECORDS.get(sig, ()))
    builder = _builder(frozenset({0x03000A00, 0x03000B00}))
    names = CB._cell_names(builder, 'LonesomeRoad', [], [])
    assert names == {'Lucky38World': 0x03000A00, 'Lucky38Cell': 0x03000B00}
    assert CB._master_places(_builder(None), 'FalloutNV') == {}


def test_a_dlcs_own_built_place_wins_over_a_masters_of_the_same_name(monkeypatch):
    """When the DLC builds a place whose EditorID a master record also has, the property names the DLC's."""
    monkeypatch.setattr(CB, 'export_records', lambda export_dir, sig: MASTER_RECORDS.get(sig, ()))
    builder = _builder(frozenset({0x03000A00}))
    names = CB._cell_names(builder, 'LonesomeRoad', [], [_world('Lucky38World', '01000800')])
    assert names['Lucky38World'] == builder.fnv_id('01000800') != 0x03000A00


def test_a_mod_names_the_masters_references_its_built_master_holds(monkeypatch):
    """A master reference in a cell the mod does not build (JSawyer's SecretSalesMarkerREF) is named under the
    master's FO4 FormID; one the built master left out is not.
    See: docs/fork/fo4_pipeline.md#master-references
    """
    refs = {'REFR': [{'FormID': '0016CCA1', 'EditorID': 'SecretSalesMarkerREF'},
                     {'FormID': '0016CCA2', 'EditorID': 'LeftOut'}]}
    monkeypatch.setattr(CB, 'export_records', lambda export_dir, sig: refs.get(sig, ()))
    names = CB._master_places(_builder(frozenset({0x0316CCA1})), 'JSawyer Ultimate Edition')
    assert names == {'SecretSalesMarkerREF': 0x0316CCA1}


def test_packages_and_conditions_reach_the_masters_cells_and_references(monkeypatch):
    """A DLC package's location in a master cell or at a master reference maps by FormID (no EditorID needed);
    the DLC's own placement of the same reference wins.
    See: docs/fork/fo4_pipeline.md#master-references
    """
    recs = {'CELL': [{'FormID': '00067488', 'Signature': 'CELL'}],
            'REFR': [{'FormID': '000288EC', 'Signature': 'REFR'}, {'FormID': '000288ED', 'Signature': 'REFR'}]}
    monkeypatch.setattr(CB, 'export_records', lambda export_dir, sig: recs.get(sig, ()))
    builder = _builder(frozenset({0x03067488, 0x030288EC, 0x030288ED}))
    builder.__dict__.update(globals={}, factions={}, actor_refs={}, objectives={}, quest_vars={}, reputation_slots={},
                            hardcore=SimpleNamespace(form_map=dict), casino=SimpleNamespace(form_map=dict),
                            packages=None)
    CB._master_held(builder, 'BrokenSteel')
    form_map = CB._form_map(builder, {'000288ED': 0x01000001}, [], {})
    assert form_map[0x00067488] == 0x03067488 and form_map[0x000288EC] == 0x030288EC
    assert form_map[0x000288ED] == 0x01000001
