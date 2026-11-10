"""An FNV terminal mesh made a Fallout 4 terminal: its screen becomes the shape FO4 draws the terminal menu on.

Fallout 4 draws a terminal's menu onto its shape named `Screen:0` (the name
the exe's terminal menu code looks up), lit by a lighting shader naming
Materials\\Interface\\PipScreenTerminals.BGSM, as vanilla TerminalOn.nif's
screen. FNV draws its terminal menu over the whole view, so its meshes mark no
screen: the screen is the largest unlit shape FNV textures (the glass it
textures with its screen texture); an untextured glare pane, which the
conversion draws through WHITE, is not one. The menu fills UV 0 to 1, laid out as
vanilla's: u left to right and v top to bottom for a viewer facing it.

See: docs/fork/fo4_pipeline.md#terminals
"""

import copy
import math

import numpy as np

from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import DESC_PLAIN, WHITE, lighting_shader, vertices

SCREEN = 'Screen:0'
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


def _screen(nif) -> 'tuple | None':
    """(shape index, its root-space points, its root-space normals) of the largest unlit textured shape."""
    placed, best = _placements(nif), None
    for index, (kind, block) in enumerate(nif.blocks):
        if kind != 'BSTriShape' or index not in placed or not block['vertices'] or not _unlit(nif, block):
            continue
        local = np.array([v['position'] for v in block['vertices']], dtype=float)
        points = local @ placed[index][:3, :3].T + placed[index][:3, 3]
        normals = np.array([v['normal'] for v in block['vertices']], dtype=float) / 127.5 - 1.0
        area = _area(points, block['triangles'])
        if best is None or area > best[0]:
            best = (area, index, points, normals @ placed[index][:3, :3].T)
    return best[1:] if best else None


def screen_uv(points: np.ndarray, facing: np.ndarray) -> np.ndarray:
    """UVs filling 0 to 1 over `points`: u to the right, v down, for a viewer looking along -`facing`."""
    right = np.cross(-facing, UP)
    right /= np.linalg.norm(right) or 1.0
    s, t = points @ right, points @ UP
    return np.stack([(s - s.min()) / (np.ptp(s) or 1.0), (t.max() - t) / (np.ptp(t) or 1.0)], axis=1)


def _turned(nif, angle: float) -> np.ndarray:
    """Turn every child of the root by `angle` about Z (their own transforms, which Elric bakes into physics); the
    turn's matrix, the identity when the root itself has collision (it would not turn)."""
    if nif.blocks[0][1].get('collision', NONE) != NONE:
        return np.eye(3)
    c, s = math.cos(angle), math.sin(angle)
    turn = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    for child in nif.blocks[0][1].get('children', []):
        block = nif.blocks[child][1] if child >= 0 else None
        if isinstance(block, dict) and 'rotation' in block:
            block['rotation'] = tuple((turn @ np.array(block['rotation']).reshape(3, 3)).flatten())
            block['translation'] = tuple(turn @ np.array(block['translation']))
    return turn


def with_screen(converted) -> 'tuple | None':
    """(a copy of converted mesh `converted` whose screen is FO4's Screen:0, turned to face -Y as FO4 needs to offer
    it (FACING), (screen centre, facing, the turn in radians) in the mesh's space); None when the mesh has no unlit
    textured shape.
    See: docs/fork/fo4_pipeline.md#terminal-facing
    """
    out = copy.deepcopy(converted)
    nif = out.nif
    found = _screen(nif)
    if found is None:
        return None
    index, points, normals = found
    facing = normals.mean(axis=0)
    facing /= np.linalg.norm(facing) or 1.0
    angle = math.atan2(FACING[1], FACING[0]) - math.atan2(facing[1], facing[0])
    turn = _turned(nif, angle)
    angle = angle if not np.allclose(turn, np.eye(3)) else 0.0
    shape = nif.blocks[index][1]
    local = np.array([v['position'] for v in shape['vertices']], dtype=float)
    local_normals = np.array([v['normal'] for v in shape['vertices']], dtype=float) / 127.5 - 1.0
    shape['vertices'] = vertices(local, screen_uv(points, facing), local_normals, None, np.array(shape['triangles']))
    shader = lighting_shader(nif, SCREEN_MATERIAL, len(nif.blocks) + 1, 0)
    shader.update(SCREEN_SHADER)
    nif.blocks += [('BSLightingShaderProperty', shader), ('BSShaderTextureSet', {'textures': SCREEN_TEXTURES})]
    shape.update(name=nif.string(SCREEN), shader=len(nif.blocks) - 2, alpha_property=-1, vertex_desc=DESC_PLAIN)
    return out, (turn @ ((points.min(axis=0) + points.max(axis=0)) / 2), turn @ facing, angle)
