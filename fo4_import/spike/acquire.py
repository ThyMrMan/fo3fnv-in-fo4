"""The FO4 package an FNV Find of an item type or category becomes: find it near a place, then pick it up.

FO4 ships no such template, so the package is authored with its own procedure
tree, the way vanilla's SitFoundRef finds a chair and sits in it: a Find fills
an object list while the actor travels to the place and sandboxes there, then
an Acquire takes items from that list and completes the package. An FNV Follow
of an actor named by base, list, faction or type gets the same shape with a
Follow of the found list (find_follow).

See: docs/fork/fo4_pipeline.md#find-items
See: docs/fork/fo4_pipeline.md#follow-found
"""

import struct

from tes5_import.base.writer import pack_subrecord

#: FNV object type codes of carried things as FO4's (xEdit wbObjectTypeEnum of each game; the same in FO3 and FNV).
OBJECT_TYPES = {'2': 2, '3': 3, '4': 16, '7': 6, '8': 7, '9': 8, '12': 11, '13': 12, '16': 13, '17': 14, '18': 15,
                '20': 17, '21': 20, '22': 19, '23': 18}
#: FNV Find type-specific flags Allow Killing and Allow Stealing (xEdit wbDefinitionsFO3 PKDT).
ALLOW_KILLING, ALLOW_STEALING = 0x200, 0x400
#: The package's CNAM value slots: the count to acquire and Acquire's Allow Stealing, Pickpocket and Killing.
COUNT_SLOT, STEAL_SLOT, PICKPOCKET_SLOT, KILL_SLOT = 1, 2, 3, 4
#: PKDT of vanilla's self-contained Acquire, RR102DeaconGrabsPrototypePackage (000E9876): type 0x12, no flags.
PKDT = bytes.fromhex('0000000012000200fffe0000')
#: PSDT with no schedule, as vanilla's self-contained packages.
PSDT = bytes.fromhex('ffff00ffff00000000000000')
#: (input type, subrecord, default, name) of each data input, in order; its UNAM index is its position.
INPUTS = (('Location', 'PLDT', struct.pack('<iIiI', 2, 0, 500, 0), 'SearchLocation'),
          ('TargetSelector', 'PTDA', struct.pack('<iIi', 2, 0, 0), 'TargetSelector'),
          ('ObjectList', 'CNAM', bytes(4), 'FoundItems'), ('Int', 'CNAM', struct.pack('<i', 1), 'NumToAcquire'),
          ('Bool', 'CNAM', b'\0', 'AllowStealing'), ('Bool', 'CNAM', b'\0', 'AllowPickpocket'),
          ('Bool', 'CNAM', b'\0', 'AllowKilling'), ('Bool', 'CNAM', b'\1', 'bTrue'), ('Bool', 'CNAM', b'\0', 'bFalse'))
#: The procedure tree, depth first: (branch, children or (procedure, success completes, input indexes)).
TREE = ('Sequence', 2), ('Simultaneous', 2), ('Find', 0, (0, 1, 2, 8, 8)), ('Sequence', 2), \
    ('Travel', 0, (0, 255, 255, 255, 255)), ('Sandbox', 0, (0, 7, 7, 7, 7, 7, 7, *[255] * 7)), \
    ('Acquire', 1, (2, 3, 4, 5, 6))


#: FNV object types of actors (NPCs, creatures, actors: xEdit wbObjectTypeEnum) as FO4's Actors: Any.
ACTOR_TYPES = {'14': 25, '15': 25, '29': 25}
#: The Find-then-Follow package's inputs: where to look, whom, the found list, Follow's radii and Bools.
FOLLOW_INPUTS = (INPUTS[0], INPUTS[1], ('ObjectList', 'CNAM', bytes(4), 'FoundActors'),
                 ('Float', 'CNAM', struct.pack('<f', 300.0), 'Min Radius'),
                 ('Float', 'CNAM', struct.pack('<f', 600.0), 'Max Radius'),
                 ('Bool', 'CNAM', b'\1', 'bTrue'), ('Bool', 'CNAM', b'\0', 'bFalse'))
#: Its tree: find the actor while going to the place, then follow what was found (FollowNPC's Follow inputs).
FOLLOW_TREE = ('Sequence', 2), ('Simultaneous', 2), ('Find', 0, (0, 1, 2, 6, 6)), ('Sequence', 2), \
    ('Travel', 0, (0, 255, 255, 255, 255)), ('Sandbox', 0, (0, 5, 5, 5, 5, 5, 5, *[255] * 7)), \
    ('Follow', 0, (2, 3, 4, 6, 6, 6))
#: FIND_FOLLOW's value slots (CNAM order): Min Radius, Max Radius.
MIN_RADIUS_SLOT, MAX_RADIUS_SLOT = 1, 2
#: FNV PKDT type Find: its PTDT count is how many to find, not a distance.
FNV_FIND = '0'
#: Find-then-Escort inputs: destination (first), whom, search place, found list, RR201LiamEscortsToZ114Package's values.
ESCORT_INPUTS = (('Location', 'PLDT', struct.pack('<iIiI', 12, 0, 500, 0), 'Destination'), INPUTS[1],
                 ('Location', 'PLDT', struct.pack('<iIiI', 12, 0, 2048, 0), 'SearchLocation'),
                 ('ObjectList', 'CNAM', bytes(4), 'FoundActors'), ('Int', 'CNAM', struct.pack('<i', 1), 'NumberToEscort'),
                 *(('Float', 'CNAM', struct.pack('<f', v), n) for v, n in ((728.0, 'EscortWaitDist'),
                                                                          (128.0, 'FollowMinDist'),
                                                                          (728.0, 'FollowMaxDist'))),
                 ('Bool', 'CNAM', b'\1', 'bTrue'), ('Bool', 'CNAM', b'\0', 'bFalse'),
                 ('Float', 'CNAM', bytes(4), 'FloatZero'))
#: Its tree: find the escorted near the escort, then lead them (DNPrime_EscortPlayerMasterPackageTemplate's slots).
ESCORT_TREE = ('Sequence', 2), ('Simultaneous', 2), ('Find', 0, (2, 1, 3, 9, 9)), ('Sequence', 2), \
    ('Travel', 0, (2, 255, 255, 255, 255)), ('Sandbox', 0, (2, 8, 8, 8, 8, 8, 8, *[255] * 7)), \
    ('Escort', 1, (3, 4, 0, 5, 6, 7, 9, 8, 255, 9, 10, 10, 10, 10, 10, 255, 255))


def find_acquire() -> bytes:
    """The authored Find-then-Acquire template's subrecords.
    See: docs/fork/fo4_pipeline.md#find-items
    """
    return _authored('FindAcquire', INPUTS, TREE)


def find_follow() -> bytes:
    """The authored Find-then-Follow template's subrecords.
    See: docs/fork/fo4_pipeline.md#follow-found
    """
    return _authored('FindFollow', FOLLOW_INPUTS, FOLLOW_TREE)


def find_escort() -> bytes:
    """The authored Find-then-Escort template's subrecords.
    See: docs/fork/fo4_pipeline.md#escort-found
    """
    return _authored('FindEscort', ESCORT_INPUTS, ESCORT_TREE)


def _authored(edid: str, inputs: tuple, tree: tuple) -> bytes:
    """A self-contained package template `edid` of data `inputs` and procedure `tree`, an instance body for
    pack_package (EditorID replaced)."""
    out = _z('EDID', edid) + pack_subrecord('PKDT', PKDT) + pack_subrecord('PSDT', PSDT)
    out += pack_subrecord('PKCU', struct.pack('<3I', len(inputs), 0, 0))
    for kind, tag, default, _ in inputs:
        out += _z('ANAM', kind) + pack_subrecord(tag, default)
    out += b''.join(pack_subrecord('UNAM', bytes([i])) for i in range(len(inputs)))
    out += pack_subrecord('XNAM', bytes([len(inputs)])) + b''.join(_branch(b) for b in tree)
    for i, (*_, name) in enumerate(inputs):
        out += pack_subrecord('UNAM', bytes([i])) + _z('BNAM', name) + pack_subrecord('PNAM', struct.pack('<I', 1))
    return out + b''.join(pack_subrecord(t, b'') + pack_subrecord('INAM', bytes(4)) + pack_subrecord('PDTO', bytes(8))
                          for t in ('POBA', 'POEA', 'POCA'))


def _branch(branch: tuple) -> bytes:
    """One procedure tree branch: a Sequence or Simultaneous of `children`, or a procedure with its inputs."""
    head = pack_subrecord('CITC', bytes(4))
    if len(branch) == 2:
        return _z('ANAM', branch[0]) + head + pack_subrecord('PRCB', struct.pack('<2I', branch[1], 0))
    name, completes, indexes = branch
    return (_z('ANAM', 'Procedure') + head + _z('PNAM', name) + pack_subrecord('FNAM', struct.pack('<I', completes))
            + b''.join(pack_subrecord('PKC2', bytes([i])) for i in indexes))


def _z(tag: str, text: str) -> bytes:
    """A zero-terminated string subrecord."""
    return pack_subrecord(tag, text.encode() + b'\0')


def selector(rec: dict, item) -> 'bytes | None':
    """The PTDA payload of FNV Find `rec`'s item target: an item by form (`item`: its FO4 record or None) or a
    carried object type; None for any other target."""
    kind, target = rec.get('PTDT.Type'), (rec.get('PTDT.Target') or '').lstrip('0')
    if kind == '1':
        fo4 = item(int(rec['PTDT.Target'], 16))
        return struct.pack('<iIi', 1, fo4, 0) if fo4 else None
    return struct.pack('<iIi', 2, OBJECT_TYPES[target], 0) if kind == '2' and target in OBJECT_TYPES else None


def follow_values(rec: dict) -> dict:
    """{value slot: CNAM} of FNV Follow `rec`'s FindFollow copy: its distance (PTDT count) as Min Radius and, when
    farther than the template's, Max Radius; none at 0.
    See: docs/fork/fo4_pipeline.md#follow-found
    """
    distance = float(int(rec.get('PTDT.Count', 0) or 0))
    if not distance or rec.get('PKDT.Type') == FNV_FIND:
        return {}
    far = max(distance, struct.unpack('<f', FOLLOW_INPUTS[4][2])[0])
    return {MIN_RADIUS_SLOT: struct.pack('<f', distance), MAX_RADIUS_SLOT: struct.pack('<f', far)}


def acquire_values(rec: dict) -> dict:
    """{value slot: CNAM} of FNV Find `rec`: its count (at least 1) and Allow Stealing (pickpocketing too) and
    Allow Killing.
    See: docs/fork/fo4_pipeline.md#find-items
    """
    flags = int(rec.get('PKDT.TypeFlags', 0) or 0)
    steal = bytes([bool(flags & ALLOW_STEALING)])
    return {COUNT_SLOT: struct.pack('<i', max(int(rec.get('PTDT.Count', 0) or 0), 1)), STEAL_SLOT: steal,
            PICKPOCKET_SLOT: steal, KILL_SLOT: bytes([bool(flags & ALLOW_KILLING)])}
