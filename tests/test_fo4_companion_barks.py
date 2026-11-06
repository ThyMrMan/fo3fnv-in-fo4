"""FNV's companion status barks on Fallout 4: which topics the watch says, and its quest.

See: docs/fork/fo4_pipeline.md#companion-barks
"""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fo4_import.spike import companion_barks as CB
from tes5_import.base.tes5_reader import sub_map

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'script_convert/static_scripts/fallout4'


class _Writer:
    """Records added records; FormIDs from a fixed base."""

    def __init__(self):
        """Nothing added yet."""
        self.added = []

    def derive_formid(self, site: str, key: str) -> int:
        """A fixed id for the watch quest."""
        return 0x0B00ABCD

    def add_record(self, sig: str, data: bytes) -> None:
        """Keep `data` of type `sig`."""
        self.added.append((sig, data))


def _builder(named: dict) -> SimpleNamespace:
    """A build whose quests built the topics `named` ({EditorID: FO4 topic})."""
    return SimpleNamespace(scripts=SimpleNamespace(named=named, used=[]), writer=_Writer(), counts=Counter(),
                           export_dir=Path('export/FalloutNV.esm'))


def test_the_status_topics_with_a_state_fo4_reads_are_said_by_script():
    """HealthHalf and NoAmmo are watched; WeaponBroke (no weapon condition on FO4) and KOed (BleedOut) are not."""
    dials = {'0015BCAF': {'EditorID': 'HealthHalf'}, '0015BCB4': {'EditorID': 'NoAmmo'},
             '0015BCB3': {'EditorID': 'WeaponBroke'}, '0015BCB7': {'EditorID': 'KOed'}}
    assert CB.status_barks(dials) == {'0015BCAF', '0015BCB4'}


def test_the_watch_quest_carries_the_built_topics_as_properties():
    """One start-game quest naming the script and each built topic's property; the script ships."""
    builder = _builder({'HealthHalf': 0x0B000101, 'Wake': 0x0B000102, 'Other': 0x0B000103})
    CB.write(builder)
    (sig, data), = builder.writer.added
    vmad = sub_map(data[24:])[b'VMAD']
    assert sig == 'QUST' and CB.SCRIPT.encode() in vmad and b'HealthHalf' in vmad and b'Wake' in vmad
    assert b'Other' not in vmad and builder.scripts.used == [CB.SCRIPT]


def test_no_status_topic_built_writes_no_quest():
    """A DLC build without the follower quest writes nothing."""
    builder = _builder({})
    CB.write(builder)
    assert builder.writer.added == [] and builder.scripts.used == []


def test_every_watched_topic_is_a_property_of_the_script():
    """The script declares a Topic property per STATUS_BARKS name, so the quest's properties bind."""
    source = (SCRIPT_DIR / f'{CB.SCRIPT}.psc').read_text()
    assert all(f'Topic Property {name} Auto Const' in source for name in CB.STATUS_BARKS)
