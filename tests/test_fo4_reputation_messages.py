"""What a Fallout 4 reputation change shows (FNV's HUD text and title box): the build hands the REPUTATION tab's
quest FalloutNV.esm's texts and title sounds, and each reputation's list names that quest.

See: docs/fork/fo4_pipeline.md#reputation-messages
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import reputation
from fo4_import.spike.pipboy_tabs import tab_formid
from tes5_import.base.tes5_reader import subrecords

GMST = ('---RECORD_BEGIN---\nSignature=GMST\nFormID=00000001\nEditorID=sRepPositiveGain\nDATA.Value=Fame Gained!\n'
        '---RECORD_END---\n\n---RECORD_BEGIN---\nSignature=GMST\nFormID=00000002\nEditorID=sRepNegativeGain\n'
        'DATA.Value=Infamy Gained!\n---RECORD_END---\n')
REPU = ('---RECORD_BEGIN---\nSignature=REPU\nFormID=00104C22\nEditorID=RepNVGoodsprings\nFULL=Goodsprings\n'
        'DATA.Value=40.0\n---RECORD_END---\n')


class _Writer:
    """Records by FormID; FormIDs hashed from the site and key."""

    def __init__(self):
        """No records yet."""
        self.records = {}

    def derive_formid(self, site: str, key: str) -> int:
        """A stable fake FormID."""
        return 0x01000000 | (hash((site, key)) & 0xFFFFFF)

    def add_record(self, sig: str, data: bytes) -> None:
        """Keep `data` by its FormID."""
        self.records[struct.unpack_from('<I', data, 12)[0]] = (sig, data)


def _builder():
    """A builder with FNV's UIRepGood sound (UIRepBad missing) and nothing else."""
    sounds = SimpleNamespace(named=lambda edid: 0x0ABC if edid == 'UIRepGood' else 0)
    return SimpleNamespace(writer=_Writer(), sounds=sounds, counts=Counter(), fnv_id=lambda fid: int(fid, 16),
                           scripts=SimpleNamespace(used=[]))


def test_each_list_names_the_tab_and_the_tab_holds_fnvs_texts(tmp_path):
    """Slot 8 of a reputation's list is the tab's quest; the tab runs F3NV_ReputationTab with the texts FNV has
    and the sounds that converted."""
    (tmp_path / 'GMST.txt').write_text(GMST)
    (tmp_path / 'REPU.txt').write_text(REPU)
    builder = _builder()
    names, _ = reputation.write_reputations(builder, tmp_path)
    _, body = builder.writer.records[names['RepNVGoodsprings']]
    forms = [struct.unpack('<I', v)[0] for k, v in subrecords(body[24:]) if k == b'LNAM']
    assert len(forms) == 9 and forms[8] == tab_formid(builder, 'REPUTATION')
    sounds, texts = builder.reputation_page[2]
    assert sounds == {'TitleUp': 0x0ABC}
    assert texts == {'FameGained': ('string', 'Fame Gained!'), 'InfamyGained': ('string', 'Infamy Gained!')}
    assert reputation.write_page(builder) == forms[8]
    assert reputation.TAB_SCRIPT in builder.scripts.used
