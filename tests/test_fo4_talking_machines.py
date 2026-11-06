"""FNV's talking machines as an unseen speaker beside their look (fo4_import.spike.talking_machines).

See: docs/fork/fo4_creature_audit.md#talking-machines
"""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import records as R
from fo4_import.spike import talking_machines as TM
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def test_the_look_is_each_part_placed_with_the_speaker_and_enable_parented_to_it():
    """Each part is placed with the speaker, enable-parented to it, its script naming it."""
    machines = TM.TalkingMachines.__new__(TM.TalkingMachines)
    ids = iter(range(0x0A00, 0x0A10))
    scripts = SimpleNamespace(used=[], vmad=lambda scpt, extra: repr(extra).encode())
    machines.builder = SimpleNamespace(new_id=lambda owner, key=None: next(ids), counts=Counter(), scripts=scripts)
    machines.statics = lambda rec: [0x0B01, 0x0B02]
    out = machines.look(0x0C01, {}, '00171B46', ((1.0, 2.0, 3.0), (0.0, 0.0, 1.5), 1.0, True, False))
    refs, at = [], 0
    while at < len(out):
        size, flags, fid = struct.unpack_from('<III', out, at + 4)
        refs.append((fid, flags, dict(subrecords(out[at + 24:at + 24 + size]))))
        at += 24 + size
    assert [struct.unpack('<I', d[b'NAME'])[0] for _, _, d in refs] == [0x0B01, 0x0B02]
    assert all(d[b'XESP'] == struct.pack('<IB3x', 0x0C01, 0) and flags & 0x400 for _, flags, d in refs)
    assert struct.unpack_from('<3f', refs[0][2][b'DATA']) == (1.0, 2.0, 3.0)
    assert all(TM.LOOK_SCRIPT.encode() in d[b'VMAD'] and str(0x0C01).encode() in d[b'VMAD'] for _, _, d in refs)


def test_a_part_with_no_triangles_is_still_an_activator_bounded_by_zeros(monkeypatch):
    """A particle spray part (OWB's brain tank) has no triangles, so no bounds: its activator's OBND is zeros."""
    machines = TM.TalkingMachines.__new__(TM.TalkingMachines)
    added = []
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x0D01, add_record=lambda sig, raw: added.append(raw))
    machines.builder, machines.parts = SimpleNamespace(writer=writer, counts=Counter()), {}
    machines.export_dir = machines.data_dir = None
    monkeypatch.setattr(TM, 'part_pose', lambda part, worlds: {})
    monkeypatch.setattr(TM, 'export_file', lambda *parts: None)
    monkeypatch.setattr(TM, 'write_assets', lambda *args, **kw: ('fnv\\spray_speaker.nif', None))
    assert machines._part('nvdlc03\\creatures\\braintank', 'spray01.nif', {}, 'Brain') == 0x0D01
    assert dict(subrecords(added[0][24:]))[b'OBND'] == bytes(12)


def test_without_object_templates_drops_the_whole_block():
    """A robot's object template block (OBTE ... STOP, its FULLs too) goes; the NPC's own FULL stays."""
    rows = [('EDID', b'X\0'), ('OBTE', bytes(4)), ('OBTF', b''), ('FULL', b'Arms\0'), ('OBTS', b'\0'), ('STOP', b''),
            ('FULL', b'Mr. House\0')]
    kept = subrecords(R.without_object_templates(b''.join(pack_subrecord(t, d) for t, d in rows)))
    assert list(kept) == [(b'EDID', b'X\0'), (b'FULL', b'Mr. House\0')]
