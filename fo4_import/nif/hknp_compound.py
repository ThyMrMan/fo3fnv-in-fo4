"""Lists as Elric writes them: an hknpDynamicCompoundShape with one instance per child, and its Mass.

A child under a convex transform keeps its own frame and the instance carries the
transform; every other child sits in place. Instance and tree-node w words carry
packed integers (PACKED or'd with a value). The compound's Mass is a solid box over
its bounds, with no rotation, whatever the children.

See: docs/fork/fo4_hknp_writer.md#compound
"""

import struct

import numpy as np

from fo4_import.havok.packfile import classes
from fo4_import.nif.hknp_convex import INERTIA_SCALE, Mass
from fo4_import.nif.hknp_mesh import DISPATCH_COMPOSITE

#: The tag or'd into a packed w word.
PACKED = 0x3F000000
#: Shape flags Elric writes on a compound, and the w word of every instance's first column.
COMPOUND_FLAGS, INSTANCE_WORD = 4, PACKED | 0x40
#: A compressed mesh's memory size as an instance records it.
MESH_SIZE = 0x90
#: An instance's shape and destruction tags: none.
NO_TAG = 0xFFFF
EDGE_WELDING = {'secondaryKeyMask': 0xFFFFFFFF, 'sencondaryKeyBits': 0, 'primaryKeyToIndex': [],
                'valueAndSecondaryKeys': []}


# ---------------------------------------------------------------------------
# Packed words and child bounds
# ---------------------------------------------------------------------------

def word(bits: int) -> float:
    """The float whose bits are `bits`."""
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def _size(shape: dict) -> int:
    """Shape object `shape`'s memory size as an instance records it: class and tail, in 16-byte steps."""
    if shape['class'] == 'hknpCompressedMeshShape':
        return MESH_SIZE
    size = classes().size(shape['class']) + len(shape['fields'].get('__tail__', b''))
    return -(-size // 16) * 16


def _corners(objects: list) -> tuple:
    """(points, padding) bounding child `objects`: a mesh's domain corners, or a convex shape's vertices and
    its convex radius."""
    shape = objects[0]['fields']
    if objects[0]['class'] == 'hknpCompressedMeshShape':
        domain = objects[-1]['fields']['meshTree']['domain']
        lo, hi = domain['min'][:3], domain['max'][:3]
        return np.array([(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]), 0.0
    count = shape['vertices'][0]
    points = np.array(struct.unpack_from(f'<{4 * count}f', shape['__tail__'])).reshape(-1, 4)[:, :3]
    return points, shape['convexRadius']


def bounds(objects: list, matrix: np.ndarray) -> tuple:
    """(min, max) float32 of child `objects` placed by 4×4 `matrix`."""
    points, pad = _corners(objects)
    placed = (points @ matrix[:3, :3].T + matrix[:3, 3]).astype(np.float32)
    return placed.min(0) - np.float32(pad), placed.max(0) + np.float32(pad)


# ---------------------------------------------------------------------------
# The bounding tree
# ---------------------------------------------------------------------------

def _node(lo, hi, parent: int, children: int) -> dict:
    """A tree node: its box, packed `parent`, `children` (first | second << 16)."""
    return {'aabb': {'min': (*map(float, lo), word(PACKED | parent)), 'max': (*map(float, hi), word(children))}}


def _grow(nodes: list, boxes: list, members: list, parent: int, leaf: list) -> int:
    """Append the subtree over `members` (instance indices) to `nodes` top-down, parent before children, split
    at the median center on the longest axis; its root's index. `leaf[i]` gets instance i's node."""
    at = len(nodes)
    lo = np.min([boxes[i][0] for i in members], 0)
    hi = np.max([boxes[i][1] for i in members], 0)
    nodes.append(None)
    if len(members) == 1:
        leaf[members[0]] = at
        nodes[at] = _node(lo, hi, parent, members[0] << 16)
        return at
    axis = int(np.argmax(hi - lo))
    order = sorted(members, key=lambda i: (boxes[i][0][axis] + boxes[i][1][axis], i))
    first = _grow(nodes, boxes, order[:len(order) // 2], at, leaf)
    second = _grow(nodes, boxes, order[len(order) // 2:], at, leaf)
    nodes[at] = _node(lo, hi, parent, first | second << 16)
    return at


def tree(boxes: list) -> tuple:
    """(hknpDynamicCompoundShapeTree fields, each instance's leaf node) over instance `boxes`: node 0 unused,
    the root at 1, one free node last."""
    empty = {'aabb': {'min': (0.0,) * 4, 'max': (0.0,) * 4}}
    nodes, leaf = [empty], [0] * len(boxes)
    _grow(nodes, boxes, list(range(len(boxes))), 0, leaf)
    fields = {'nodes': nodes + [empty], 'firstFree': len(nodes), 'numLeaves': len(boxes), 'path': 0, 'root': 1}
    return fields, leaf


# ---------------------------------------------------------------------------
# The compound
# ---------------------------------------------------------------------------

def box_mass(lo: np.ndarray, hi: np.ndarray) -> Mass:
    """The Mass of a solid box from `lo` to `hi`, inertia scaled by INERTIA_SCALE."""
    d = (hi - lo).astype(float)
    volume = float(np.prod(d))
    inertia = INERTIA_SCALE * volume / 12 * np.array([d[1] ** 2 + d[2] ** 2, d[0] ** 2 + d[2] ** 2,
                                                      d[0] ** 2 + d[1] ** 2])
    return Mass(volume, (lo + hi) / 2, inertia, (0.0, 0.0, 0.0, 1.0))


def _instance(shape: dict, matrix: np.ndarray, leaf: int) -> dict:
    """The instance of child `shape` placed by `matrix`, its tree leaf `leaf`, w words packed."""
    cells = [float(x) for x in matrix.T.flatten()]
    cells[3], cells[7], cells[11], cells[15] = word(INSTANCE_WORD), 0.0, word(PACKED | _size(shape)), \
        word(PACKED | leaf)
    return {'transform': cells, 'scale': (1.0,) * 4, 'shape': shape['#'], 'shapeTag': NO_TAG,
            'destructionTag': NO_TAG, 'padding': [0] * 30}


def compound(name: str, children: list, material: int) -> tuple:
    """([the shape, its children's objects, its tree] as packfile objects named from `name`, Mass) over
    `children` [(maker, 4×4 matrix)], material CRC `material`."""
    made = [(maker(f'{name}c{i}')[0], matrix) for i, (maker, matrix) in enumerate(children)]
    boxes = [bounds(objects, matrix) for objects, matrix in made]
    fields, leaf = tree(boxes)
    lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)
    corner = min(fields['nodes'][k]['aabb']['min'][3] for k in leaf)
    shape = {'flags': COMPOUND_FLAGS, 'numShapeKeyBits': len(children).bit_length(),
             'dispatchType': DISPATCH_COMPOSITE, 'convexRadius': 0.0, 'userData': material, 'properties': None,
             'edgeWeldingMap': dict(EDGE_WELDING), 'shapeTagCodecInfo': 0xFFFFFFFF,
             'instances': {'elements': [_instance(o[0], m, k) for (o, m), k in zip(made, leaf)], 'firstFree': -1},
             'aabb': {'min': (*map(float, lo), corner), 'max': (*map(float, hi), 0.0)}, 'isMutable': 1,
             'boundingVolumeData': f'{name}t'}
    objects = [{'#': name, 'class': 'hknpDynamicCompoundShape', 'fields': shape}]
    objects += [o for objs, _ in made for o in objs]
    objects.append({'#': f'{name}t', 'class': 'hknpDynamicCompoundShapeData', 'fields': {'aabbTree': fields}})
    return objects, box_mass(lo, hi)
