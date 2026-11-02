"""A placed dead actor's ragdoll pose (XRGD), FNV's onto FO4's skeleton.

Both games store the pose alike (xEdit's wbRagdoll): one 28-byte entry per
ragdoll body, in the skeleton NIF's tree order, each a u8 body part number
(the body's collision filter part: FNV's bhkRigidBody filter, FO4's hknp
body collisionFilterInfo >> 8), 3 unused bytes, then a position and a
rotation. The first entry is the root body's node in the reference's space;
the others are each node's transform relative to its skeleton parent node
(nodes without a body, such as a clavicle, stay at rest). The rotation is
a reference's: Rx(-x) @ Ry(-y) @ Rz(-z) on column vectors (spike.scol).
Found from the games' own corpses: every entry's position is its node's
rest offset, and only this reading lays FNV's corpses flat on the floor.

A converted pose keeps each limb's direction: an FO4 body takes the turn
its FNV bone (by name through the actor's rig, else the same name) made
from rest, applied to FO4's rest orientation. A body without a source
stays at rest relative to its parent. XRGB (biped rotation) is copied.
See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import functools
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fo4_import.nif import file as nif_file
from fo4_import.pipeline.export_index import export_file
from fo4_import.spike.scol import angles, rotation
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

ENTRY = struct.Struct('<B3x6f')
#: FO4's feral ghoul skeleton names its biped bones its own way (no rig maps them): FNV's Bip01 bone -> its.
FERAL_GHOUL = {'Bip01 Spine': 'SpineRoot', 'Bip01 Spine1': 'SPINE1', 'Bip01 Spine2': 'SPINE2', 'Bip01 Neck': 'Neck',
               'Bip01 Head': 'HEAD'}
for _side in 'LR':
    FERAL_GHOUL.update({f'Bip01 {_side} Thigh': f'{_side}THIGH', f'Bip01 {_side} Calf': f'{_side}CALF',
                        f'Bip01 {_side} Foot': f'{_side}FOOT', f'Bip01 {_side} UpperArm': f'{_side}UPPERARM',
                        f'Bip01 {_side} Forearm': f'{_side}ForeArm1', f'Bip01 {_side} Hand': f'{_side}HAND'})
#: FO4 skeleton (lower case) -> the FNV-to-FO4 bone names for it that no rig holds.
SKELETON_BONES = {'actors\\feralghoul\\characterassets\\skeleton.nif': FERAL_GHOUL}
#: The share of FO4's ragdoll bodies that must have an FNV source for a pose to be written.
MAPPED_SHARE = 0.75
#: FO4 hknp collisionFilterInfo bits holding the body part number (FNV's filter keeps it in its low 5 bits).
PART_SHIFT, PART_MASK = 8, 0x1F


@dataclass
class Skeleton:
    """A skeleton's nodes {name: (parent or None, rest local rotation (column form), rest local translation)}
    and its ragdoll bodies [(node, part number)] in tree order."""
    nodes: dict
    bodies: list

    @functools.cached_property
    def rest(self) -> dict:
        """{node: (world rotation, world position)} at rest."""
        return chain(self.nodes, {})


def chain(nodes: dict, posed: dict, root: 'str | None' = None, root_pose: tuple = None) -> dict:
    """{node: (rotation, position)} of every node: `posed` {node: local rotation} replaces a node's rest
    rotation; `root` takes `root_pose` (rotation, position) outright."""
    out = {}

    def world(name):
        """Node `name`'s (rotation, position), its parents' first."""
        if name not in out:
            parent, rot, pos = nodes[name]
            rot = posed.get(name, rot)
            if name == root:
                out[name] = root_pose
            elif parent is None or parent not in nodes:
                out[name] = (rot, pos)
            else:
                prot, ppos = world(parent)
                out[name] = (prot @ rot, prot @ pos + ppos)
        return out[name]
    for name in nodes:
        world(name)
    return out


def fnv_skeleton(path: Path) -> Skeleton:
    """An FNV skeleton NIF's nodes and ragdoll bodies (pyffi; its row-major rotations transposed)."""
    from fo4_import.nif.outfit import NifFormat, fnv_nif
    root = fnv_nif(path)
    nodes, bodies = {root.name.decode('cp1252'): (None, np.eye(3), np.zeros(3))}, []
    for node in root.tree():
        if not isinstance(node, NifFormat.NiNode):
            continue
        name = node.name.decode('cp1252')
        body = node.collision_object.body if node.collision_object else None
        if body is not None and hasattr(body, 'havok_col_filter'):
            bodies.append((name, int(body.havok_col_filter.flags_and_part_number) & PART_MASK))
        for child in node.children:
            if isinstance(child, NifFormat.NiNode):
                m, t = child.rotation, child.translation
                rot = np.array([[m.m_11, m.m_12, m.m_13], [m.m_21, m.m_22, m.m_23], [m.m_31, m.m_32, m.m_33]]).T
                nodes[child.name.decode('cp1252')] = (name, rot, np.array([t.x, t.y, t.z]))
    return Skeleton(nodes, bodies)


def fo4_skeleton(raw: bytes) -> 'Skeleton | None':
    """An FO4 skeleton NIF's nodes and ragdoll bodies (its bhkRagdollSystem's, by their collision objects), the
    bodies in tree order; None without a ragdoll."""
    from fo4_import.rig.assets import RAGDOLL_DATA, packfile
    nif = nif_file.read(raw)
    system = next((i for i, (k, _) in enumerate(nif.blocks) if k == 'bhkRagdollSystem'), None)
    if system is None:
        return None
    data = next(o['fields'] for o in packfile.read(nif.blocks[system][1][4:], only=RAGDOLL_DATA).objects
                if o['class'] == 'hknpRagdollData')
    owned = {}
    for kind, block in nif.blocks:
        if kind == 'bhkNPCollisionObject':
            target, _flags, owner, body = struct.unpack_from('<iHiI', block)
            if owner == system:
                owned[target] = (data['bodyCinfos'][body]['collisionFilterInfo'] >> PART_SHIFT) & PART_MASK
    nodes, bodies = {}, []

    def visit(i, parent):
        """Record node block `i` (under `parent`) and its children, depth first."""
        block = nif.blocks[i][1]
        if not (isinstance(block, dict) and 'children' in block and 'rotation' in block):
            return
        name = nif.strings[block['name']]
        nodes[name] = (parent, np.array(block['rotation']).reshape(3, 3), np.array(block['translation']))
        if i in owned:
            bodies.append((name, owned[i]))
        for child in block['children']:
            if child >= 0:
                visit(child, name)
    visit(0, None)
    return Skeleton(nodes, bodies)


#: FO4 NPC_ template flag Traits (race from the template) and the TPTA slot naming that template.
USE_TRAITS, TRAITS_SLOT = 0x1, 0


def race_skeleton(lookup, fid: int, depth: int = 0) -> 'str | None':
    """The male skeleton model (meshes-relative) of FO4 actor base or leveled list `fid`: its race's first ANAM
    after MNAM, following a Traits template or a list's first entry; `lookup(fid)` gives (signature, subrecords)
    or None."""
    rec = lookup(fid) if depth < 12 else None
    if rec is None:
        return None
    sig, subs = rec
    tags = dict(subs)
    if sig == b'LVLN':
        first = next((b for t, b in subs if t == b'LVLO'), None)
        return race_skeleton(lookup, struct.unpack_from('<I', first, 4)[0], depth + 1) if first else None
    if sig == b'RACE':
        after = [b for t, b in subs[next((i for i, (t, _) in enumerate(subs) if t == b'MNAM'), len(subs)):]
                 if t == b'ANAM']
        return after[0].rstrip(b'\0').decode('cp1252') if after else None
    if sig != b'NPC_':
        return None
    flags = struct.unpack_from('<H', tags[b'ACBS'], 14)[0] if b'ACBS' in tags else 0
    if flags & USE_TRAITS:
        tpta = tags.get(b'TPTA')
        template = struct.unpack_from('<I', tpta, 4 * TRAITS_SLOT)[0] if tpta else 0
        template = template or (struct.unpack('<I', tags[b'TPLT'])[0] if b'TPLT' in tags else 0)
        if template:
            return race_skeleton(lookup, template, depth + 1)
    return race_skeleton(lookup, struct.unpack('<I', tags[b'RNAM'])[0], depth + 1) if b'RNAM' in tags else None


#: FNV actor template flag Model/Animation.
FNV_USE_MODEL = 0x40


def fnv_model(records: dict, fid: int, depth: int = 0) -> 'str | None':
    """The skeleton model (meshes-relative) of FNV NPC, creature or leveled list `fid` in `records` {FormID: export
    row}: its own, its Model/Animation template's, or a list's first entry's."""
    rec = records.get(fid) if depth < 12 else None
    if rec is None:
        return None
    if 'EntryCount' in rec:
        return fnv_model(records, int(rec['Entry[0].FormID'], 16), depth + 1) if int(rec['EntryCount'] or 0) else None
    if int(rec.get('ACBS.TemplateFlags', 0) or 0) & FNV_USE_MODEL and 'TPLT.Template' in rec:
        return fnv_model(records, int(rec['TPLT.Template'], 16), depth + 1)
    model = rec.get('Model.MODL')
    return model.replace('\\\\', '\\') if model and model.lower().endswith('skeleton.nif') else None


def decode(skeleton: Skeleton, xrgd: bytes) -> 'dict | None':
    """{node: (rotation, position)} in the reference's space of `skeleton` posed by `xrgd`; None when its entry
    count is not the skeleton's body count."""
    entries = [ENTRY.unpack_from(xrgd, o) for o in range(0, len(xrgd) - ENTRY.size + 1, ENTRY.size)]
    if len(entries) != len(skeleton.bodies) or not entries:
        return None
    root = skeleton.bodies[0][0]
    posed = {name: rotation(e[4:7]) for (name, _), e in zip(skeleton.bodies[1:], entries[1:])}
    return chain(skeleton.nodes, posed, root, (rotation(entries[0][4:7]), np.array(entries[0][1:4])))


def sources(fnv: Skeleton, fo4: Skeleton, bones: dict) -> dict:
    """{FO4 body node: its FNV source node}: the FNV ragdoll body mapping to it through `bones` {FNV: FO4}, else
    any FNV node so mapped, else an FNV node of the same name; FO4's root falls back on FNV's root."""
    fnv_bodies = [n for n, _ in fnv.bodies]
    out = {}
    for name, _ in fo4.bodies:
        named = [n for n in fnv.nodes if bones.get(n, n) == name]
        pick = next((n for n in fnv_bodies if n in named), named[0] if named else None)
        if pick is not None:
            out[name] = pick
    out.setdefault(fo4.bodies[0][0], fnv.bodies[0][0])
    return out


def convert(fnv: Skeleton, fo4: Skeleton, bones: dict, xrgd: bytes) -> 'bytes | None':
    """FO4's XRGD for `fo4` of FNV pose `xrgd` on `fnv` (bones mapped through `bones`); None when it does not
    decode."""
    posed = decode(fnv, xrgd)
    if posed is None:
        return None
    src = sources(fnv, fo4, bones)
    turn = {o: posed[f][0] @ fnv.rest[f][0].T for o, f in src.items()}
    root = fo4.bodies[0][0]
    f_root = src[root]
    root_rot = turn[root] @ fo4.rest[root][0]
    root_pos = posed[f_root][1] + turn[root] @ (fo4.rest[root][1] - fnv.rest[f_root][1])
    world = {root: root_rot}
    out = ENTRY.pack(fo4.bodies[0][1], *root_pos, *angles(root_rot))

    def world_rot(name):
        """FO4 node `name`'s posed rotation: its source's turn on its rest, else its rest under its parent."""
        if name not in world:
            parent, rest_rot, _ = fo4.nodes[name]
            world[name] = turn[name] @ fo4.rest[name][0] if name in turn else world_rot(parent) @ rest_rot
        return world[name]
    for name, part in fo4.bodies[1:]:
        parent, _, rest_pos = fo4.nodes[name]
        local = world_rot(parent).T @ world_rot(name)
        out += ENTRY.pack(part, *rest_pos, *angles(local))
    return out


class Poses:
    """Converted ragdoll poses for one build's placed dead actors: skeletons read once, each outcome counted."""

    def __init__(self, builder, fnv_records: dict, ragdolls: dict):
        """`fnv_records` {FormID: export row} holds FNV's NPCs, creatures and leveled lists; `ragdolls` {FNV
        reference: (XRGD, XRGB or None)}."""
        from fo4_import.base.ba2 import Archives
        from fo4_import.base.install import FALLOUT4_DIR
        self.builder, self.fnv_records, self.ragdolls = builder, fnv_records, ragdolls
        self.archives = Archives(FALLOUT4_DIR / 'Data')
        self.vanilla = {r.form_id: (sig, list(subrecords(r.body))) for sig in (b'NPC_', b'LVLN', b'RACE')
                        for r, _ in walk(builder.fo4, sig)}
        self.built, self.built_at, self.skeletons = {}, -1, {}

    def _lookup(self, fid: int) -> 'tuple | None':
        """(signature, subrecords) of FO4 record `fid`: Fallout4.esm's, else the plugin's own so far."""
        writer = self.builder.writer
        if fid >> 24 != writer.own_index:
            return self.vanilla.get(fid)
        if fid not in self.built and self.built_at != writer._record_count:
            self.built_at = writer._record_count
            for blob in writer.top_records():
                if blob[:4] in (b'NPC_', b'LVLN', b'RACE'):
                    flags, own = struct.unpack_from('<II', blob, 8)
                    body = blob[24:]
                    self.built[own] = (blob[:4], list(subrecords(zlib.decompress(body[4:]) if flags & 0x40000
                                                                  else body)))
        return self.built.get(fid)

    def _skeleton(self, key: tuple):
        """The FNV ('fnv', model) or FO4 ('fo4', model) skeleton, read once; None when missing or ragdoll-less."""
        if key not in self.skeletons:
            kind, model = key
            try:
                if kind == 'fnv':
                    path = export_file(self.builder.export_dir, 'meshes', model.replace('\\', '/').lower())
                    self.skeletons[key] = fnv_skeleton(path) if path.exists() else None
                else:
                    loose = self.builder.data_dir / 'Meshes' / model
                    raw = loose.read_bytes() if loose.exists() else self.archives.read('meshes\\' + model.lower())
                    self.skeletons[key] = fo4_skeleton(raw)
            except KeyError:
                self.skeletons[key] = None
        return self.skeletons[key]

    def subrecords(self, fnv_ref: int, fnv_base: int, base: int) -> bytes:
        """XRGD (and FNV's XRGB) for FNV reference `fnv_ref` of FNV base `fnv_base` placed on FO4 `base`; b''
        when FNV has no pose or it does not map (counted by reason)."""
        found = self.ragdolls.get(fnv_ref)
        model, target = fnv_model(self.fnv_records, fnv_base), race_skeleton(self._lookup, base)
        fnv = self._skeleton(('fnv', model)) if found and model else None
        fo4 = self._skeleton(('fo4', target)) if fnv and target else None
        why = ('no FNV pose' if not found else 'no FNV skeleton' if fnv is None else
               'no FO4 ragdoll' if fo4 is None else None)
        pose = None
        if why is None:
            bones = bone_map(model, target)
            mapped = len(sources(fnv, fo4, bones)) / len(fo4.bodies)
            pose = convert(fnv, fo4, bones, found[0]) if mapped >= MAPPED_SHARE else None
            why = 'bones not matched' if mapped < MAPPED_SHARE else 'entries not FNV bodies' if pose is None else None
        label = target or model or f'{fnv_base:08X}'
        self.builder.counts[f'ragdoll pose {"written" if why is None else "left out: " + why}: {label}'] += 1
        if why is not None:
            return b''
        return pack_subrecord('XRGD', pose) + (pack_subrecord('XRGB', found[1]) if found[1] else b'')


def bone_map(model: str, target: str) -> dict:
    """FNV bone -> FO4 bone for FNV skeleton `model` on FO4 skeleton `target`: a creature pair's rig, the FO4
    skeleton's own table (SKELETON_BONES), else the human rig."""
    from fo4_import.nif.creature import PAIRS
    from fo4_import.nif.outfit import BONES
    from fo4_import.spike.creatures import skeleton_folder
    pair = PAIRS.get(skeleton_folder(model))
    return pair.rig.bones if pair else SKELETON_BONES.get(target.lower(), BONES)


def ragdolls(refs) -> dict:
    """{FNV reference: (XRGD, XRGB or None)} of FNV `refs` (source_walk's (record, stack))."""
    out = {}
    for rec, _ in refs:
        tags = dict(subrecords(rec.body))
        if b'XRGD' in tags:
            out[rec.form_id] = (tags[b'XRGD'], tags.get(b'XRGB'))
    return out
