"""An FNV terminal mesh made a Fallout 4 terminal: its screen becomes the shape FO4 draws the terminal menu on.

Fallout 4 draws a terminal's menu onto its shape named `Screen:0` (the name
the exe's terminal menu code looks up), lit by a lighting shader naming
Materials\\Interface\\PipScreenTerminals.BGSM, as vanilla TerminalOn.nif's
screen. FNV draws its terminal menu over the whole view, so its meshes mark no
screen: the screen is the largest unlit island FNV textures (the glass it
textures with its screen texture); an untextured glare pane, which the
conversion draws through WHITE, is not one. Of a shape holding several screens,
only that one island becomes Screen:0; the rest keep their shape. The menu fills UV 0 to 1, laid out as
vanilla's: u left to right and v top to bottom for a viewer facing it.

See: docs/fork/fo4_pipeline.md#terminals
"""

import copy
import math
import struct
from types import SimpleNamespace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from fo4_import.nif.blocks import NONE, sphere_bound
from fo4_import.nif.convert_static import DESC_PLAIN, IDENTITY, WHITE, lighting_shader, vertices
from fo4_import.pipeline.mesh_cache import mesh_bounds

SCREEN = 'Screen:0'
#: The child node a root's own collision moves to, so it turns with the rest of the mesh.
COLLISION_NODE = 'TerminalCollision'
SCREEN_MATERIAL = 'Materials\\Interface\\PipScreenTerminals.BGSM'
#: Vanilla TerminalOn.nif Screen:0's texture set.
SCREEN_TEXTURES = ['textures\\AnimObjects\\PipBoy\\PipBoyScreen_d.dds', 'textures\\shared\\flatflat_n.dds', '', '',
                   'textures\\Shared\\Cubemaps\\MetalChrome02Cube_e.dds', '', '',
                   'textures\\AnimObjects\\PipBoy\\PipBoyScreen_s.dds', '', '']
#: Its lighting shader's values: environment map type, flags, smoothness, greyscale scale, env map scale.
SCREEN_SHADER = {'shader_type': 1, 'flags1': 0x80400081, 'flags2': 0x21, 'smoothness': 0.92, 'grayscale_scale': 0.5,
                 'envmap': (3.0, 0, 0)}
UP = np.array([0.0, 0.0, 1.0])
#: The direction a terminal's screen faces in its mesh: FO4 offers a terminal only from its -Y side.
FACING = (0.0, -1.0, 0.0)


def _matrix(block: dict) -> np.ndarray:
    """A node's or shape's local transform as a 4x4 matrix (rotation rows, then translation and scale)."""
    out = np.eye(4)
    out[:3, :3] = np.array(block['rotation']).reshape(3, 3) * block['scale']
    out[:3, 3] = block['translation']
    return out


def _placements(nif) -> dict:
    """{block index: 4x4 transform into the root's space} of every node and shape under the root."""
    out, todo = {0: _matrix(nif.blocks[0][1])}, [0]
    while todo:
        parent = todo.pop()
        for child in nif.blocks[parent][1].get('children', []):
            if child >= 0 and child not in out:
                out[child] = out[parent] @ _matrix(nif.blocks[child][1])
                todo.append(child)
    return out


def _placed_points(block: dict, placement: np.ndarray) -> np.ndarray:
    """Shape `block`'s vertices moved by 4x4 `placement` (_placements)."""
    return np.array([v['position'] for v in block['vertices']], dtype=float) @ placement[:3, :3].T + placement[:3, 3]


def placed_bounds(nif) -> 'tuple | None':
    """mesh_bounds() of every shape where its nodes put it."""
    placed = _placements(nif)
    shapes = [('BSTriShape', {'vertices': [{'position': p} for p in _placed_points(b, placed[i])]})
              for i, (kind, b) in enumerate(nif.blocks) if kind == 'BSTriShape' and i in placed and b['vertices']]
    return mesh_bounds(SimpleNamespace(blocks=shapes))


def _unlit(nif, block: dict) -> bool:
    """Whether a shape has an unlit effect shader (no material file) with FNV's own texture, not WHITE."""
    if block['shader'] < 0:
        return False
    kind, shader = nif.blocks[block['shader']]
    return kind == 'BSEffectShaderProperty' and shader['name'] < 0 and shader['source_texture'] not in ('', WHITE)


def _area(points: np.ndarray, triangles: list) -> float:
    """Total area of `triangles` over `points`."""
    tris = np.array(triangles, dtype=int).reshape(-1, 3)
    return float(np.linalg.norm(np.cross(points[tris[:, 1]] - points[tris[:, 0]],
                                         points[tris[:, 2]] - points[tris[:, 0]]), axis=1).sum() / 2)


def islands(points: np.ndarray, tris: np.ndarray) -> list:
    """A mask of (n, 3) `tris` per island: triangles joined through corners at one position of `points`."""
    _, welded = np.unique(np.round(points, 3), axis=0, return_inverse=True)
    corners = welded.ravel()[tris]
    edges = np.concatenate([corners[:, :2], corners[:, 1:]])
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(points),) * 2)
    owner = connected_components(graph, directed=False)[1][corners[:, 0]]
    return [owner == label for label in np.unique(owner)]


def _screen(nif) -> 'tuple | None':
    """(shape index, mask of its triangles) of the largest island of an unlit textured shape; the lowest of equals.
    See: docs/fork/fo4_pipeline.md#terminal-one-screen
    """
    placed, best = _placements(nif), None
    for index, (kind, block) in enumerate(nif.blocks):
        if kind != 'BSTriShape' or index not in placed or not block['vertices'] or not _unlit(nif, block):
            continue
        points = _placed_points(block, placed[index])
        tris = np.array(block['triangles'], dtype=np.int64).reshape(-1, 3)
        for mask in islands(points, tris):
            key = (round(_area(points, tris[mask]), 1), -points[tris[mask]][..., 2].mean())
            if best is None or key > best[0]:
                best = (key, index, mask)
    return best[1:] if best else None


def _subset(shape: dict, mask: np.ndarray) -> dict:
    """A copy of BSTriShape fields `shape` holding only its `mask` triangles and the vertices they use."""
    tris = np.array(shape['triangles'], dtype=np.int64).reshape(-1, 3)[mask]
    used, local = np.unique(tris, return_inverse=True)
    verts = [shape['vertices'][i] for i in used]
    return dict(shape, vertices=verts, triangles=[tuple(map(int, t)) for t in local.reshape(-1, 3)],
                extra=list(shape.get('extra', [])), bound=sphere_bound([v['position'] for v in verts]))


def _split(nif, index: int, mask: np.ndarray) -> int:
    """The index of a shape holding shape `index`'s `mask` triangles: that shape when they are all of it, else a new
    one beside it (same parent, no controller), `index` keeping the rest."""
    if mask.all():
        return index
    shape = nif.blocks[index][1]
    parent = next(i for i, (_, b) in enumerate(nif.blocks) if isinstance(b, dict) and index in b.get('children', ()))
    nif.blocks[index] = ('BSTriShape', _subset(shape, ~mask))
    nif.blocks.append(('BSTriShape', dict(_subset(shape, mask), controller=NONE)))
    nif.blocks[parent][1]['children'].append(len(nif.blocks) - 1)
    return len(nif.blocks) - 1


def _placed_frame(nif, index: int) -> tuple:
    """(root-space points, root-space normals) of shape `index`."""
    placement, block = _placements(nif)[index], nif.blocks[index][1]
    normals = np.array([v['normal'] for v in block['vertices']], dtype=float) / 127.5 - 1.0
    return _placed_points(block, placement), normals @ placement[:3, :3].T


def screen_uv(points: np.ndarray, facing: np.ndarray) -> np.ndarray:
    """UVs filling 0 to 1 over `points`: u to the right, v down, for a viewer looking along -`facing`."""
    right = np.cross(-facing, UP)
    right /= np.linalg.norm(right) or 1.0
    s, t = points @ right, points @ UP
    return np.stack([(s - s.min()) / (np.ptp(s) or 1.0), (t.max() - t) / (np.ptp(t) or 1.0)], axis=1)


def _collision_child(nif) -> None:
    """Hand the root's own collision (pre-Elric, target first) to a new child node at the root's place."""
    root = nif.blocks[0][1]
    if root.get('collision', NONE) == NONE:
        return
    nif.blocks.append(('NiNode', {'name': nif.string(COLLISION_NODE), 'extra': [], 'controller': NONE,
                                  'flags': root['flags'], 'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY,
                                  'scale': 1.0, 'collision': root['collision'], 'children': []}))
    kind, raw = nif.blocks[root['collision']]
    nif.blocks[root['collision']] = (kind, struct.pack('<i', len(nif.blocks) - 1) + raw[4:])
    root['children'].append(len(nif.blocks) - 1)
    root['collision'] = NONE


def _moved(nif, angle: float, centre: np.ndarray) -> np.ndarray:
    """Turn every child of the root by `angle` about Z, then shift them flat so `centre` sits over the origin (their
    own transforms, which Elric bakes into physics); the move as a row-vector 4x4 (guns.turned)."""
    _collision_child(nif)
    c, s = math.cos(angle), math.sin(angle)
    turn = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    shift = -(turn @ centre) * np.array([1.0, 1.0, 0.0])
    for child in nif.blocks[0][1].get('children', []):
        block = nif.blocks[child][1] if child >= 0 else None
        if isinstance(block, dict) and 'rotation' in block:
            block['rotation'] = tuple((turn @ np.array(block['rotation']).reshape(3, 3)).flatten())
            block['translation'] = tuple(turn @ np.array(block['translation']) + shift)
    move = np.eye(4)
    move[:3, :3], move[3, :3] = turn.T, shift
    return move


def with_screen(converted) -> 'tuple | None':
    """(a copy of converted mesh `converted` whose screen is FO4's Screen:0, turned to face -Y and moved over the
    origin as FO4 needs to offer it (FACING), (screen centre, facing, the move: _moved) in the mesh's space); None
    when the mesh has no unlit textured shape.
    See: docs/fork/fo4_pipeline.md#terminal-facing
    """
    out = copy.deepcopy(converted)
    nif = out.nif
    found = _screen(nif)
    if found is None:
        return None
    index = _split(nif, *found)
    points, normals = _placed_frame(nif, index)
    facing = normals.mean(axis=0)
    facing /= np.linalg.norm(facing) or 1.0
    centre = (points.min(axis=0) + points.max(axis=0)) / 2
    move = _moved(nif, math.atan2(FACING[1], FACING[0]) - math.atan2(facing[1], facing[0]), centre)
    shape = nif.blocks[index][1]
    local = np.array([v['position'] for v in shape['vertices']], dtype=float)
    local_normals = np.array([v['normal'] for v in shape['vertices']], dtype=float) / 127.5 - 1.0
    shape['vertices'] = vertices(local, screen_uv(points, facing), local_normals, None, np.array(shape['triangles']))
    shader = lighting_shader(nif, SCREEN_MATERIAL, len(nif.blocks) + 1, 0)
    shader.update(SCREEN_SHADER)
    nif.blocks += [('BSLightingShaderProperty', shader), ('BSShaderTextureSet', {'textures': SCREEN_TEXTURES})]
    shape.update(name=nif.string(SCREEN), shader=len(nif.blocks) - 2, alpha_property=-1, vertex_desc=DESC_PLAIN)
    return out, (centre @ move[:3, :3] + move[3, :3], facing @ move[:3, :3], move)
