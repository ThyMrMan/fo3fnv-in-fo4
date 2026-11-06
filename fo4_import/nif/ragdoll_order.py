"""An Elric skeleton.nif's ragdoll in one fixed order, so the same input gives the same bytes.

Elric numbers a ragdoll's bodies in a different order on every run (three
runs of one rat skeleton, three orders), and the ragdoll's skeleton, motions,
constraints and object layout follow it. `in_node_order` renumbers the
bodies in the skeleton.nif's own node order (ours, parents first): the
hknpRagdollData's bodies, their motions, the constraints' body pairs (sorted
by them), its ragdoll skeleton's bones (parents, pose and boneToBodyMap with
them), its referenced shapes, and each node's bhkNPCollisionObject body id.
The packfile is written again depth first (packfile_write), which reproduces
Elric's own blob byte for byte when nothing moves.

See: docs/fork/fo4_own_rig.md#ragdoll-order
"""

import struct

from fo4_import.havok import packfile, packfile_write

#: A body id's offset in a bhkNPCollisionObject (target ref, flags, system ref, body id).
BODY_ID = 10
LAST = 1 << 30


def in_node_order(nif):
    """`nif` (Elric's skeleton.nif) with its bhkRagdollSystem's bodies numbered in node order; as is without one, or
    when the ragdoll holds a class the layout table does not describe (byte for byte as Elric wrote it)."""
    system = next((i for i, (k, _) in enumerate(nif.blocks) if k == 'bhkRagdollSystem'), None)
    if system is None:
        return nif
    blob = nif.blocks[system][1][4:]
    if not described(blob):
        return nif
    held = _held(nif, system)
    pf = packfile.read(blob)
    data = next(o['fields'] for o in pf.objects if o['class'] == 'hknpRagdollData')
    order = sorted(range(len(data['bodyCinfos'])), key=lambda b: (held.get(b, LAST), b))
    new = {old: i for i, old in enumerate(order)}
    _bodies(data, order, new)
    _skeleton(next(o['fields'] for o in pf.objects if o['#'] == data['skeleton']), data, new)
    blob = packfile_write.write(pf.objects, pf.objects[0]['#'], extension=pf.extension)
    nif.blocks[system] = (nif.blocks[system][0], struct.pack('<I', len(blob)) + blob)
    for body, node in held.items():
        at = nif.blocks[node][1]['collision']
        raw = bytearray(nif.blocks[at][1])
        struct.pack_into('<I', raw, BODY_ID, new[body])
        nif.blocks[at] = (nif.blocks[at][0], bytes(raw))
    return nif


def described(blob: bytes) -> bool:
    """Whether the layout table describes every object class in packfile `blob`."""
    known = packfile.classes().raw
    return all(cls in known for _, cls in packfile.read(blob, only=frozenset()).virtual)


def _held(nif, system: int) -> dict:
    """{ragdoll body id: index of the node whose collision object holds it}."""
    out = {}
    for i, (kind, block) in enumerate(nif.blocks):
        if kind == 'NiNode' and block['collision'] >= 0:
            _target, _flags, owner, body = struct.unpack_from('<iHiI', nif.blocks[block['collision']][1])
            out.update({body: i} if owner == system else {})
    return out


def _bodies(data: dict, order: list, new: dict) -> None:
    """Put hknpRagdollData `data`'s bodies in `order` (new -> old), their motions in first use, constraints on
    the renumbered bodies (`new`: old -> new) sorted by them, and its referenced shapes in body order."""
    data['bodyCinfos'] = [data['bodyCinfos'][old] for old in order]
    used = list(dict.fromkeys(b['motionId'] for b in data['bodyCinfos']))
    motions = used + [m for m in range(len(data['motionCinfos'])) if m not in used]
    moved = {old: i for i, old in enumerate(motions)}
    data['motionCinfos'] = [data['motionCinfos'][m] for m in motions]
    for body in data['bodyCinfos']:
        body['motionId'] = moved[body['motionId']]
    for c in data['constraintCinfos']:
        c['bodyA'], c['bodyB'] = new[c['bodyA']], new[c['bodyB']]
    data['constraintCinfos'].sort(key=lambda c: (c['bodyA'], c['bodyB']))
    shapes = [b['shape'] for b in data['bodyCinfos']]
    data['referencedObjects'] = ([s for s in dict.fromkeys(shapes) if s in data['referencedObjects']]
                                 + [r for r in data['referencedObjects'] if r not in shapes])


def _skeleton(skeleton: dict, data: dict, new: dict) -> None:
    """Put ragdoll skeleton `skeleton`'s bones in their bodies' new order (`new`: old -> new), parents first,
    with their parents, pose and `data`'s boneToBodyMap."""
    body_of = data['boneToBodyMap']
    bones = sorted(range(len(skeleton['bones'])), key=lambda b: (new.get(body_of[b], LAST), b))
    moved = {old: i for i, old in enumerate(bones)}
    parents = [moved[skeleton['parentIndices'][b]] if skeleton['parentIndices'][b] >= 0 else -1 for b in bones]
    if any(p >= i for i, p in enumerate(parents)):
        raise ValueError('ragdoll node order puts a bone before its parent')
    skeleton['bones'] = [skeleton['bones'][b] for b in bones]
    skeleton['referencePose'] = [skeleton['referencePose'][b] for b in bones]
    skeleton['parentIndices'] = parents
    data['boneToBodyMap'] = [new.get(body_of[b], body_of[b]) for b in bones]
