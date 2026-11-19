"""Our copy of Fallout4.esm's ForceGreet package template, greeting only once the player is in the trigger.

Vanilla's tree greets three ways: the player detected inside the Target Trigger
Location, the same without detection, or the NPC already within the
Forcegreet Distance of the player, with no trigger test. FO3/FNV Dialogue
packages greet only once the target is inside their Trigger Location, so a
copy whose third branch also tests the trigger is written, and every
converted ForceGreet uses it. A package without an FO3/FNV trigger has one
near the player (always met), so it greets as vanilla's does.

See: docs/fork/fo4_pipeline.md#greet-in-trigger
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import conditions as C
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: derive_formid site and EditorID of the template copy.
SITE, EDID = 'F3NV ForceGreet template', 'F3NV_ForceGreetInTrigger'
#: GetWithinPackageLocation, and the template's data ids of the Target Trigger Location and Forcegreet Distance.
WITHIN, TRIGGER_DATA, GREET_DATA = C.FO4.index('GetWithinPackageLocation'), 0x2, 0x5


def template_of(instance: bytes) -> int:
    """The template FormID package `instance` names (PKCU)."""
    return struct.unpack_from('<I', dict(subrecords(instance))[b'PKCU'], 4)[0]


def with_template(instance: bytes, template: int) -> bytes:
    """Package subrecords `instance` naming `template` in its PKCU."""
    subs = [(tag, data[:4] + struct.pack('<I', template) + data[8:] if tag == b'PKCU' else data)
            for tag, data in subrecords(instance)]
    return b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs)


def _within(data: bytes, location: int) -> bool:
    """Whether CTDA `data` tests GetWithinPackageLocation of template data `location`."""
    return struct.unpack_from('<H', data, 8)[0] == WITHIN and struct.unpack_from('<I', data, 12)[0] == location


def in_trigger(template: bytes) -> bytes:
    """ForceGreet template subrecords `template` with the trigger test (its first) added to the branch greeting
    because the NPC is within the Forcegreet Distance; raise ValueError when the template has no such branch."""
    subs = list(subrecords(template))
    trigger = next(data for tag, data in subs if tag == b'CTDA' and _within(data, TRIGGER_DATA))
    at = next(i for i, (tag, data) in enumerate(subs) if tag == b'CTDA' and _within(data, GREET_DATA))
    if subs[at - 1][0] != b'CITC':
        raise ValueError('ForceGreet template: the greet-distance branch does not open with its condition count')
    count = struct.unpack('<I', subs[at - 1][1])[0]
    subs[at - 1] = (b'CITC', struct.pack('<I', count + 1))
    subs.insert(at, (b'CTDA', subs[at][1][:4] + trigger[4:]))
    subs = [(tag, EDID.encode() + b'\0' if tag == b'EDID' else data) for tag, data in subs]
    return b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs)


def write(builder, instance: bytes, packs: dict) -> bytes:
    """Write the template copy of vanilla ForceGreet `instance`'s template (from `packs`, {FormID: body});
    `instance` naming it."""
    fid = builder.writer.derive_formid(SITE, EDID)
    builder.writer.add_record('PACK', pack_fo4_record('PACK', fid, 0, in_trigger(packs[template_of(instance)])))
    builder.counts['PACK template (ForceGreet in trigger)'] += 1
    return with_template(instance, fid)
