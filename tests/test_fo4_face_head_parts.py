"""A face fit reads an NPC's FNV head parts from the newest plugin of the export's master chain holding it, so a
DLC build fitting a FalloutNV.esm NPC sees the same brows and beards the base game's build does.

See: docs/fork/fo4_pipeline.md#face-fit-head-parts
"""

from pathlib import Path

from fo4_import.pipeline import export_index
from fo4_import.spike import fnv_npc

BROW, BEARD, DLC_BROW = 0x100, 0x101, 0x01000900
#: {plugin: ({NPC FormID: [PNAM]}, {HDPT FormID: (EditorID, model)})} the stubbed ESMs hold.
ESMS = {
    'FalloutNV.esm': ({0x801: [BROW, BEARD]},
                      {BROW: ('EyebrowM', 'brow.nif'), BEARD: ('Beard', 'beard.nif')}),
    'DLC.esm': ({0x01000800: [DLC_BROW, BEARD], 0x802: [BEARD]}, {DLC_BROW: ('DlcBrow', 'dlcbrow.nif')}),
}


def _exports(tmp_path, monkeypatch) -> tuple:
    """(base export, DLC export on it) with their ESMs stubbed."""
    base, dlc = tmp_path / 'FalloutNV.esm', tmp_path / 'DLC.esm'
    base.mkdir()
    dlc.mkdir()
    (dlc / '_HEADER.txt').write_text('Master[0]=FalloutNV.esm\n', encoding='utf-8')
    export_index.export_masters.cache_clear()
    monkeypatch.setattr(fnv_npc.source_registry, 'directory_for', lambda _parent, name: 'data')
    monkeypatch.setattr(fnv_npc, '_esm_records', lambda path: ESMS[Path(path).name])
    return base, dlc


def test_dlc_build_reads_its_masters_npc(tmp_path, monkeypatch):
    """A DLC export finds a FalloutNV.esm NPC's parts as the base export does."""
    base, dlc = _exports(tmp_path, monkeypatch)
    want = [('Beard', 'beard.nif'), ('EyebrowM', 'brow.nif')]
    assert fnv_npc.head_parts(base, 0x801) == want
    assert fnv_npc.head_parts(dlc, 0x801) == want


def test_override_and_master_parts(tmp_path, monkeypatch):
    """The DLC's override of a master NPC wins; a DLC NPC's master-owned parts resolve."""
    _, dlc = _exports(tmp_path, monkeypatch)
    assert fnv_npc.head_parts(dlc, 0x802) == [('Beard', 'beard.nif')]
    assert fnv_npc.head_parts(dlc, 0x01000800) == [('Beard', 'beard.nif'), ('DlcBrow', 'dlcbrow.nif')]


def test_pnam_order_changes_nothing(tmp_path, monkeypatch):
    """Two NPCs listing the same parts in another order get the same head parts."""
    base, _ = _exports(tmp_path, monkeypatch)
    monkeypatch.setitem(ESMS['FalloutNV.esm'][0], 0x803, [BEARD, BROW])
    assert fnv_npc.head_parts(base, 0x803) == fnv_npc.head_parts(base, 0x801)
