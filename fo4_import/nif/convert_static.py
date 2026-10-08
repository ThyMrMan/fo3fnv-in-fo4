"""An FNV static mesh as a Fallout 4 one: geometry, lighting shaders and their BGSM materials.

Every visible NiTriShape/NiTriStrips becomes one BSTriShape under the root
NiNode, its transform baked in; its textures and alpha become a material
`materials\\fnv\\<diffuse path>.bgsm`, shared by every shape with the same
textures and alpha. Collision becomes pre-Elric Havok blocks at the end
(collision.py; elric.finish makes them FO4 physics). Textures keep their FNV paths
under `textures\\fnv\\`.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

import functools
import io
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from asset_convert.texture import spec_mask
from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile

apply_patches()
from pyffi.formats.nif import NifFormat

from asset_convert.collision.collision_falloutnv import latch_source
from fo4_import.nif.collision import collision_nodes

PREFIX = 'fnv'
#: BSVertexDesc of a vanilla static shape (ClutterGen, SetDressing): half positions, UV, normal, tangent.
DESC_PLAIN = 0x1B00000430205
#: The same with vertex colours.
DESC_COLOR = 0x3B00005430206
#: Root NiNode flags and lighting shader flags of vanilla ClutterGenShelfA.
NODE_FLAGS, SHADER_FLAGS = 0xE, (0x80400201, 0x11)
#: Texture set slots a lighting shader fills (vanilla: 10, specular at 7).
TEXTURE_SLOTS, SLOT_SPECULAR = 10, 7
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
#: FNV BSXFlags bits kept (same meaning in FO4): Havok, Complex, Dynamic, Articulated; vanilla statics carry 0x82.
BSX_KEPT = 0x2 | 0x8 | 0x40 | 0x80
#: BSXFlags Havok, Complex, Articulated: all 2,352 vanilla FURN/STAT/MISC meshes with Havok, not Complex, set Articulated.
BSX_HAVOK, BSX_COMPLEX, BSX_ARTICULATED = 0x2, 0x8, 0x80
BGSM_TEXTURES = ('diffuse', 'normal', 'smooth_spec', 'greyscale', 'envmap', 'glow', 'inner_layer', 'wrinkles',
                 'displacement')
#: Vanilla ChemistrySetBeaker01's effect shader: flags, lighting influence, falloff, base colour, env map scale.
EFFECT_FLAGS = (0xA00000C0, 0x40000010)
BEAKER_SHADER = {'lighting_influence': 242, 'falloff': (1.0, -4.371138828673793e-08, 0.6000000238418579, 1.0),
                 'base_color': (0.18039216101169586, 0.18823537230491638, 0.20392164587974548, 0.8999999761581421),
                 'base_color_scale': 0.20000000298023224, 'env_map_scale': 2.0}
#: Effect shader flags of an unlit FNV shape: (flags1 z-test, flags2 0); the bits added per shape.
UNLIT_FLAGS, UNLIT_VERTEX_ALPHA = (0x80000000, 0), 0x8
UNLIT_ZWRITE, UNLIT_TWO_SIDED, UNLIT_COLORS = 0x1, 0x10, 0x20
#: Vanilla ChemistrySetBeaker01.BGEM, textures aside: FO4's glass for a small prop.
GLASS_EFFECT = {
    'version': 2, 'tile_flags': 3, 'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0), 'alpha': 0.8999999761581421,
    'alpha_blend': True, 'src_blend': 6, 'dst_blend': 7, 'alpha_test_ref': 128, 'alpha_test': False,
    'zbuffer_write': False, 'zbuffer_test': True, 'ssr': False, 'wetness_ssr': False, 'decal': False,
    'two_sided': True, 'decal_no_fade': False, 'non_occluder': True, 'refraction': False,
    'refraction_falloff': False, 'refraction_power': 0.0, 'env_mapping': True, 'env_mask_scale': 1.0,
    'grayscale_to_palette': False, 'blood': False, 'effect_lighting': True, 'falloff': True,
    'falloff_color': False, 'grayscale_to_palette_alpha': False, 'soft': False,
    'base_color': (0.18039216101169586, 0.1882353127002716, 0.2039215862751007), 'base_color_scale': 0.20000000298023224,
    'falloff_start_angle': 1.0, 'falloff_stop_angle': -4.371138828673793e-08, 'falloff_start_opacity': 0.5,
    'falloff_stop_opacity': 0.8999999761581421, 'lighting_influence': 0.949999988079071, 'env_min_lod': 0,
    'soft_depth': 100.0,
}
#: Vanilla BloatflyWing.BGEM, textures aside: FO4's lit translucent surface (no falloff, full scene lighting).
TRANSLUCENT_EFFECT = dict(GLASS_EFFECT, alpha=1.0, two_sided=False, env_mapping=False, falloff=False,
                          base_color=(1.0, 1.0, 1.0), base_color_scale=1.0, falloff_start_angle=1.0,
                          falloff_stop_angle=1.0, falloff_start_opacity=0.0, falloff_stop_opacity=0.0,
                          lighting_influence=1.0)
#: Vanilla bloatfly.nif's wing effect shader values, and its flags (z-test, effect lighting; skinned bit dropped).
WING_SHADER = {'lighting_influence': 255, 'falloff': (1.0, 1.0, 0.0, 0.0), 'base_color': (1.0, 1.0, 1.0, 1.0),
               'base_color_scale': 1.0, 'env_map_scale': 1.0}
WING_FLAGS, EFFECT_ENV_MAP = (0xA0000000, 0x40000000), 0x80
#: Alpha from which a texel is seen, and solid; the seen share in between that keeps a blend (else a cut-out).
SEEN_ALPHA, SOLID_ALPHA, TRANSLUCENT_SHARE = 8, 247, 0.5
#: The alpha test of a cut-out made from a blend: vanilla's most common threshold, test on, blend off.
CUTOUT_REF, ALPHA_TEST_BIT = 128, 0x200
#: The blend (src alpha, inverse src alpha) FNV gives an unlit shape fading by vertex alpha without an alpha property.
VERTEX_ALPHA_BLEND = (0x10ED, 0)
#: Barycentric points sampled per triangle when judging its texels: corners, edge midpoints, centre.
TRIANGLE_SAMPLES = np.array([(1, 0, 0), (0, 1, 0), (0, 0, 1), (.5, .5, 0), (0, .5, .5), (.5, 0, .5), (1 / 3,) * 3])
#: Lighting shader flags1 of a decal (Decal, Dynamic_Decal), as vanilla's blended decals carry them.
DECAL_FLAGS = 0x0C000000
#: The most common value of every field over Fallout4.esm's 6,616 BGSMs, textures and root material aside.
MATERIAL = {
    'version': 2, 'tile_flags': 3, 'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0), 'alpha': 1.0,
    'alpha_blend': False, 'src_blend': 6, 'dst_blend': 7, 'alpha_test_ref': 128, 'alpha_test': False,
    'zbuffer_write': True, 'zbuffer_test': True, 'ssr': False, 'wetness_ssr': False, 'decal': False,
    'two_sided': False, 'decal_no_fade': False, 'non_occluder': False, 'refraction': False,
    'refraction_falloff': False, 'refraction_power': 0.0, 'env_mapping': False, 'env_mask_scale': 1.0,
    'grayscale_to_palette': False, 'editor_alpha_ref': False, 'rim_lighting': False, 'rim_power': 2.0,
    'backlight_power': 0.0, 'subsurface': False, 'subsurface_rolloff': 0.30000001192092896, 'specular': True,
    'specular_color': (1.0, 1.0, 1.0), 'specular_mult': 1.0, 'smoothness': 1.0, 'fresnel_power': 5.0,
    'wet_spec_scale': -1.0, 'wet_spec_power': -1.0, 'wet_spec_minvar': -1.0, 'wet_env_map_scale': -1.0,
    'wet_fresnel': -1.0, 'wet_metalness': -1.0, 'aniso_lighting': False, 'emittance': False,
    'emittance_mult': 1.0, 'model_space_normals': False, 'external_emittance': False, 'back_lighting': False,
    'receive_shadows': False, 'hide_secret': False, 'cast_shadows': True, 'dissolve_fade': False,
    'assume_shadowmask': False, 'glowmap': False, 'env_window': False, 'env_eye': False, 'hair': False,
    'hair_tint': (0.501960813999176,) * 3, 'tree': False, 'facegen': False, 'skin_tint': False,
    'tessellate': False, 'displacement_bias': 0.0, 'displacement_scale': 0.0, 'tessellation_pn_scale': 0.0,
    'tessellation_base': 0.0, 'tessellation_fade': 0.0, 'grayscale_scale': 0.501960813999176,
    'skew_specular_alpha': False,
}


@dataclass
class Converted:
    """One converted mesh: the NIF, {material path: BGSM dict}, the FNV textures it needs.

    `spec_maps` is {FO4 specular map path: (FNV normal map path, smoothness)},
    the maps to build from FNV's normal-map alpha; `effects` is {path: BGEM dict}.
    """
    nif: NifFile
    materials: dict = field(default_factory=dict)
    textures: set = field(default_factory=set)
    spec_maps: dict = field(default_factory=dict)
    effects: dict = field(default_factory=dict)


def fo4_texture(fnv_path: str) -> str:
    """An FNV texture path as the path under FO4's textures folder; '' for none."""
    rel = texture_source(fnv_path)[len('textures\\'):]
    return f'{PREFIX}\\{rel}' if rel else ''


def texture_source(fnv_path: str) -> str:
    """An FNV texture path as `textures\\...`, lowercase."""
    rel = fnv_path.replace('/', '\\').lower()
    rel = rel[len('data\\'):] if rel.startswith('data\\') else rel
    return rel if rel.startswith('textures\\') else 'textures\\' + rel


def _unit(v: np.ndarray) -> np.ndarray:
    """Rows scaled to length 1 (zero rows stay zero)."""
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n > 0, n, 1.0)


def tangent_frame(pos: np.ndarray, uv: np.ndarray, nrm: np.ndarray, tris: np.ndarray) -> tuple:
    """(dP/du, dP/dv) per vertex, summed over its triangles and made perpendicular to the normal."""
    du, dv = np.zeros_like(pos), np.zeros_like(pos)
    e1, e2 = pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]]
    t1, t2 = uv[tris[:, 1]] - uv[tris[:, 0]], uv[tris[:, 2]] - uv[tris[:, 0]]
    det = t1[:, 0] * t2[:, 1] - t2[:, 0] * t1[:, 1]
    inv = np.where(np.abs(det) > 1e-12, 1.0 / np.where(det == 0, 1, det), 0.0)[:, None]
    for k in range(3):
        np.add.at(du, tris[:, k], (e1 * t2[:, 1:2] - e2 * t1[:, 1:2]) * inv)
        np.add.at(dv, tris[:, k], (e2 * t1[:, 0:1] - e1 * t2[:, 0:1]) * inv)
    du = _unit(du - nrm * np.sum(du * nrm, axis=1, keepdims=True))
    dv = _unit(dv - nrm * np.sum(dv * nrm, axis=1, keepdims=True))
    return du, dv


def _byte(x: float) -> int:
    """A -1..1 component as nif.xml's normbyte."""
    return int(round((max(-1.0, min(1.0, x)) + 1.0) * 127.5))


def vertices(pos, uv, nrm, colors, tris) -> list:
    """BSVertexData dicts; FO4's 'tangent' is dP/dv and its bitangent dP/du (measured on vanilla)."""
    du, dv = tangent_frame(pos, uv, nrm, tris)
    out = []
    for i in range(len(pos)):
        v = {'position': tuple(float(c) for c in pos[i]), 'bitangent_x': float(du[i, 0]),
             'uv': (float(uv[i, 0]), float(uv[i, 1])), 'normal': tuple(_byte(c) for c in nrm[i]),
             'bitangent_y': _byte(du[i, 1]), 'tangent': tuple(_byte(c) for c in dv[i]),
             'bitangent_z': _byte(du[i, 2])}
        if colors is not None:
            v['color'] = tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in colors[i])
        out.append(v)
    return out


def _geometry(geom, root) -> tuple:
    """(positions, UVs, normals, colours or None, triangles) of one FNV shape in root space."""
    data, m = geom.data, np.array(geom.get_transform(root).as_list())
    pos = np.array([(v.x, v.y, v.z, 1.0) for v in data.vertices]) @ m
    nrm = np.array([(n.x, n.y, n.z) for n in data.normals]) @ m[:3, :3] if data.has_normals else None
    uv = (np.array([(t.u, t.v) for t in data.uv_sets[0]]) if data.num_uv_sets and len(data.uv_sets)
          else np.zeros((data.num_vertices, 2)))
    colors = (np.array([(c.r, c.g, c.b, c.a) for c in data.vertex_colors]) if data.has_vertex_colors else None)
    tris = np.array([t for t in data.get_triangles() if len(set(t)) == 3], dtype=np.int64).reshape(-1, 3)
    if nrm is None:
        nrm = np.zeros_like(pos[:, :3])
        for k in range(3):
            face = np.cross(pos[tris[:, 1], :3] - pos[tris[:, 0], :3], pos[tris[:, 2], :3] - pos[tris[:, 0], :3])
            np.add.at(nrm, tris[:, k], face)
    return pos[:, :3], uv, _unit(nrm), colors, tris


def smoothness(glossiness: float) -> float:
    """Blinn-Phong glossiness as smoothness: 1 - (2 / (power + 2)) ** 0.25.

    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    return 1.0 - (2.0 / (max(glossiness, 0.0) + 2.0)) ** 0.25


def _square(dds: bytes) -> bool:
    """True for a DDS whose width equals its height."""
    return len(dds) >= 20 and struct.unpack_from('<I', dds, 12) == struct.unpack_from('<I', dds, 16)


def spec_map_path(fnv_normal: str) -> str:
    """The FO4 specular map path for an FNV normal map: x_n.dds becomes x_s.dds."""
    path = fo4_texture(fnv_normal).rsplit('.', 1)[0]
    return (path[:-2] if path.endswith('_n') else path) + '_s.dds'


def _specular(mat: dict, fnv_normal: str, props: dict, texture_root) -> 'tuple | None':
    """Set `mat`'s specular from FNV's normal-map alpha; (map path, (normal, smoothness)) or None.

    Specular is off when the alpha carries no mask (spec_mask's rule, which
    ignores the mesh's material colour) or the map is not square.
    """
    source = Path(texture_root) / texture_source(fnv_normal).replace('\\', '/') if texture_root and fnv_normal else None
    data = source.read_bytes() if source and source.exists() else b''
    if not spec_mask.has_mask(data) or not _square(data):
        mat['specular'] = False
        return None
    material = props.get('NiMaterialProperty')
    path = spec_map_path(fnv_normal)
    mat['textures']['smooth_spec'] = path.replace('\\', '/')
    return path, (fnv_normal, smoothness(material.glossiness if material else 0.0))


def spec_image(normal_dds: bytes, smooth: float) -> np.ndarray:
    """The RGB image of an FO4 specular map: R the normal map's alpha, G the smoothness."""
    alpha = np.asarray(Image.open(io.BytesIO(normal_dds)).convert('RGBA'))[:, :, 3]
    out = np.zeros(alpha.shape + (3,), np.uint8)
    out[:, :, 0], out[:, :, 1] = alpha, int(round(smooth * 255))
    return out


@dataclass
class ShapeMaterial:
    """A shape's material, its path and dict, FNV textures, alpha, spec map.

    kind 'lit' is a BGSM, 'effect' a BGEM, 'unlit' an effect shader with no
    material file (path ''; data holds its texture and vertex alpha). An
    effect's `shader` is its NIF shader's values and flags (vanilla beaker
    glass when None); `flags1` is added to a lit shader's flags1; `split` is
    (translucent material, texture) for a cut-out's see-through triangles.
    """
    kind: str
    path: str
    data: dict
    textures: list
    alpha: 'tuple | None'
    spec: 'tuple | None'
    shader: 'tuple | None' = None
    flags1: int = 0
    split: 'tuple | None' = None


def _alpha_fields_of(flags: int, threshold: int) -> dict:
    """The material fields of NiAlphaProperty flags and threshold (same blend enum)."""
    return {'alpha_blend': bool(flags & 1), 'src_blend': (flags >> 1) & 0xF, 'dst_blend': (flags >> 5) & 0xF,
            'alpha_test': bool(flags & ALPHA_TEST_BIT), 'alpha_test_ref': threshold}


def _alpha_fields(alpha) -> dict:
    """The material fields an FNV NiAlphaProperty sets."""
    return _alpha_fields_of(alpha.flags, alpha.threshold)


def _alpha_part(alpha) -> 'tuple | None':
    """(flags, threshold) of an FNV NiAlphaProperty, or None."""
    return (alpha.flags, alpha.threshold) if alpha is not None else None


def _unlit(shader, alpha, two_sided: bool, fades: bool) -> ShapeMaterial:
    """An FNV BSShaderNoLightingProperty shape: its texture, vertex alpha, blend and sidedness.

    One that fades by vertex alpha (`fades`: some vertex alpha below 1, sf_vertex_alpha) blends with no
    NiAlphaProperty, as FNV's baked soft shadows do; an untextured one that fades has only its vertex
    alpha to blend by, flagged or not (NV_NoSo_RanchHouse03:1).
    """
    fnv = shader.file_name.decode('cp1252')
    vertex_alpha = bool(shader.shader_flags.sf_vertex_alpha) or (not fnv and fades)
    data = {'texture': fo4_texture(fnv), 'vertex_alpha': vertex_alpha, 'two_sided': two_sided}
    part = _alpha_part(alpha) or (VERTEX_ALPHA_BLEND if vertex_alpha and fades else None)
    return ShapeMaterial('unlit', '', data, [fnv] if fnv else [], part, None)


def _effect(fnv: list, alpha) -> ShapeMaterial:
    """Alpha-blended FNV glass as vanilla's beaker glass, with FNV's textures and blend."""
    tex = [fo4_texture(t).replace('\\', '/') if t else '' for t in fnv + [''] * 6]
    data = dict(GLASS_EFFECT, **_alpha_fields(alpha), env_mapping=bool(tex[4]),
                textures={'base': tex[0], 'grayscale': '', 'envmap': tex[4], 'normal': tex[1], 'env_mask': ''})
    stem = tex[0].replace('/', '\\').rsplit('.', 1)[0] or f'{PREFIX}\\untextured'
    return ShapeMaterial('effect', f'materials\\{stem}_effect.bgem', data,
                         [t for i, t in enumerate(fnv[:5]) if t and i in (0, 1, 4)], _alpha_part(alpha), None)


@functools.cache
def texture_alpha(texture: Path) -> 'np.ndarray | None':
    """A texture's alpha channel, read once per run; None when it cannot be read."""
    try:
        return np.asarray(Image.open(texture).convert('RGBA'))[:, :, 3]
    except (OSError, ValueError):
        return None


def _mostly_partial(alpha: np.ndarray, axis=None) -> np.ndarray:
    """Whether most seen alpha values (along `axis`) are partly transparent."""
    seen = alpha >= SEEN_ALPHA
    partial = (seen & (alpha < SOLID_ALPHA)).sum(axis)
    return (partial >= TRANSLUCENT_SHARE * np.maximum(seen.sum(axis), 1)) & seen.any(axis)


def translucent(texture: Path) -> bool:
    """True when most of a texture's seen texels are partly transparent."""
    alpha = texture_alpha(texture)
    return alpha is not None and bool(_mostly_partial(alpha))


def translucent_triangles(texture: Path, uv: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Per triangle, whether its texels (TRIANGLE_SAMPLES) are mostly partly transparent."""
    alpha = texture_alpha(texture)
    if alpha is None or not len(tris):
        return np.zeros(len(tris), bool)
    h, w = alpha.shape
    points = np.einsum('sk,tkd->tsd', TRIANGLE_SAMPLES, uv[tris])
    texels = alpha[(points[..., 1] * h).astype(int) % h, (points[..., 0] * w).astype(int) % w]
    return _mostly_partial(texels, axis=1)


def _translucent(fnv: list, alpha, two_sided: bool) -> ShapeMaterial:
    """A blended FNV surface whose texture is mostly see-through, as vanilla's lit insect-wing BGEM."""
    tex = [fo4_texture(t).replace('\\', '/') if t else '' for t in fnv + [''] * 6]
    data = dict(TRANSLUCENT_EFFECT, **_alpha_fields(alpha), two_sided=two_sided,
                textures={'base': tex[0], 'grayscale': '', 'envmap': '', 'normal': tex[1], 'env_mask': ''})
    stem = tex[0].replace('/', '\\').rsplit('.', 1)[0] or f'{PREFIX}\\untextured'
    flags = (WING_FLAGS[0], WING_FLAGS[1] | (DOUBLE_SIDED if two_sided else 0))
    return ShapeMaterial('effect', f'materials\\{stem}{"_2s" if two_sided else ""}_translucent.bgem', data,
                         [t for t in fnv[:2] if t], _alpha_part(alpha), None, (WING_SHADER, flags))


def _lit_alpha(alpha, decal: bool) -> 'tuple | None':
    """A lit shape's FNV alpha as FO4 draws it: decals keep their blend; other blends become a cut-out."""
    if alpha is None or not alpha.flags & 1 or decal:
        return _alpha_part(alpha)
    threshold = alpha.threshold if alpha.flags & ALPHA_TEST_BIT else CUTOUT_REF
    return (alpha.flags & ~1) | ALPHA_TEST_BIT, threshold


def _bgsm(fnv: list, props: dict, alpha, two_sided: bool, decal: bool, texture_root) -> ShapeMaterial:
    """A lit FNV shape's BGSM: its textures, spec map, sidedness and alpha as FO4 draws it (_lit_alpha)."""
    mat = dict(MATERIAL, root_material='', two_sided=two_sided, decal=decal,
               textures={**dict.fromkeys(BGSM_TEXTURES, '')})
    mat['textures']['diffuse'] = fo4_texture(fnv[0]).replace('\\', '/')
    mat['textures']['normal'] = fo4_texture(fnv[1] if len(fnv) > 1 else '').replace('\\', '/')
    spec = _specular(mat, fnv[1] if len(fnv) > 1 else '', props, texture_root)
    part = _lit_alpha(alpha, decal)
    suffix = '_2s' if two_sided else ''
    if part is not None:
        mat.update(_alpha_fields_of(*part))
        suffix += f'_a{part[0]:x}_{part[1]}'
    stem = mat['textures']['diffuse'].replace('/', '\\').rsplit('.', 1)[0] or f'{PREFIX}\\untextured'
    return ShapeMaterial('lit', f'materials\\{stem}{suffix}.bgsm', mat, [t for t in fnv[:2] if t],
                         part, spec, flags1=DECAL_FLAGS if decal else 0)


def _fades(geom) -> bool:
    """Whether an FNV shape has a vertex alpha below 1."""
    return bool(geom.data.has_vertex_colors and any(c.a < 1 for c in geom.data.vertex_colors))


def _material(geom, texture_root=None) -> ShapeMaterial:
    """The FO4 material of an FNV shape.

    Unlit shapes get an inline effect shader. A blended one with a mostly
    see-through texture gets vanilla's beaker BGEM when environment-mapped
    (FNV glass), else its insect-wing BGEM; the rest a BGSM (blended decals as
    FO4 decals, other blends as cut-outs whose see-through triangles split off
    to that BGEM: `split`). FO4 draws no blended lit surface but a decal. A
    NiStencilProperty makes it two-sided.

    See: docs/fork/fo4_spikes.md#spike-2-transparency
    """
    props = {type(p).__name__: p for p in geom.get_properties()}
    alpha, two_sided = props.get('NiAlphaProperty'), 'NiStencilProperty' in props
    if 'BSShaderNoLightingProperty' in props:
        return _unlit(props['BSShaderNoLightingProperty'], alpha, two_sided, _fades(geom))
    shader, grass = props.get('BSShaderPPLightingProperty'), props.get('TallGrassShaderProperty')
    fnv = [t.decode('cp1252') for t in shader.texture_set.textures] if shader and shader.texture_set else \
        [grass.file_name.decode('cp1252')] if grass else ['']
    blended = alpha is not None and alpha.flags & 1 and shader
    glass = bool(blended and shader.shader_flags.sf_environment_mapping)
    flags = shader.shader_flags if shader else None
    decal = bool(flags and (flags.sf_decal_single_pass or flags.sf_dynamic_decal_single_pass))
    texture = Path(texture_root) / texture_source(fnv[0]).replace('\\', '/') if texture_root and fnv[0] else None
    cut_from_blend = bool(blended and not decal and not alpha.flags & ALPHA_TEST_BIT and texture)
    clear = _effect(fnv, alpha) if glass else _translucent(fnv, alpha, two_sided) if cut_from_blend else None
    if glass and not cut_from_blend or cut_from_blend and translucent(texture):
        return clear
    mat = _bgsm(fnv, props, alpha, two_sided, decal, texture_root)
    if cut_from_blend:
        mat.split = (clear, texture)
    return mat


def _visible_shapes(root) -> list:
    """FNV shapes that render: shaded triangles, not hidden or editor markers.

    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    return [g for g in root.tree() if isinstance(g, NifFormat.NiTriBasedGeom) and not g.flags & 1
            and not g.name.lower().startswith(b'editormarker') and g.data is not None and _shaded(g)]


def _shaded(geom) -> bool:
    """Whether an FNV shape has a shader (or old texturing) property."""
    return any(isinstance(p, (NifFormat.BSShaderProperty, NifFormat.NiTexturingProperty)) for p in geom.get_properties())


def _emit(nif: NifFile, name: str, geometry: tuple, tris: np.ndarray, mat: ShapeMaterial, out: Converted) -> int:
    """Append one FO4 shape (`tris` of `geometry`, its used vertices only) with `mat`'s blocks; its index."""
    pos, uv, nrm, colors, _ = geometry
    used, local = np.unique(tris, return_inverse=True)
    pos, uv, nrm = pos[used], uv[used], nrm[used]
    colors, tris = (colors[used] if colors is not None else None), local.reshape(-1, 3)
    if mat.kind != 'unlit':
        (out.effects if mat.kind == 'effect' else out.materials)[mat.path] = mat.data
    out.textures |= set(mat.textures)
    if mat.spec:
        out.spec_maps[mat.spec[0]] = mat.spec[1]
    index = len(nif.blocks)
    after_shader = index + (3 if mat.kind == 'lit' else 2)
    center = (pos.min(axis=0) + pos.max(axis=0)) / 2
    shape = {'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS,
             'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0, 'collision': NONE,
             'bound': (*map(float, center), float(np.linalg.norm(pos - center, axis=1).max())),
             'skin': NONE, 'shader': index + 1, 'alpha_property': after_shader if mat.alpha else NONE,
             'vertex_desc': DESC_COLOR if colors is not None else DESC_PLAIN,
             'vertices': vertices(pos, uv, nrm, colors, tris), 'triangles': [tuple(map(int, t)) for t in tris]}
    nif.blocks.append(('BSTriShape', shape))
    if mat.kind == 'effect':
        nif.blocks.append(('BSEffectShaderProperty', _effect_shader(nif, mat)))
    elif mat.kind == 'unlit':
        nif.blocks.append(('BSEffectShaderProperty', _unlit_shader(nif, mat, colors is not None)))
    else:
        nif.blocks.append(('BSLightingShaderProperty', lighting_shader(nif, mat.path, index + 2, mat.flags1)))
        slots = [f'textures\\{fo4_texture(t)}' for t in mat.textures] + [''] * TEXTURE_SLOTS
        if mat.spec:
            slots[SLOT_SPECULAR] = f'textures\\{mat.spec[0]}'
        nif.blocks.append(('BSShaderTextureSet', {'textures': slots[:TEXTURE_SLOTS]}))
    if mat.alpha:
        nif.blocks.append(('NiAlphaProperty', {'name': NONE, 'extra': [], 'controller': NONE,
                                               'alpha_flags': mat.alpha[0], 'threshold': mat.alpha[1]}))
    return index


def _shape_blocks(nif: NifFile, geom, root, out: Converted, texture_root) -> list:
    """Append one FNV shape as FO4 shapes: one, or a cut-out plus its see-through triangles; their indices."""
    geometry = _geometry(geom, root)
    tris, mat, name = geometry[4], _material(geom, texture_root), geom.name.decode('cp1252')
    if mat.split:
        see_through = translucent_triangles(mat.split[1], geometry[1], tris)
        if see_through.all():
            mat = mat.split[0]
        elif see_through.any():
            return [_emit(nif, name, geometry, tris[~see_through], mat, out),
                    _emit(nif, name, geometry, tris[see_through], mat.split[0], out)]
    return [_emit(nif, name, geometry, tris, mat, out)]


def _effect_shader(nif: NifFile, mat: ShapeMaterial) -> dict:
    """An effect shader naming the BGEM `mat`: its values and flags (vanilla beaker glass's by default), textures."""
    values, flags = mat.shader or (BEAKER_SHADER, EFFECT_FLAGS)
    tex = mat.data['textures']
    full = {k: f'textures\\{v}'.replace('/', '\\') if v else '' for k, v in tex.items()}
    return {'name': nif.string(mat.path), 'extra': [], 'controller': NONE, 'flags1': flags[0],
            'flags2': flags[1], 'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0),
            'source_texture': full['base'], 'clamp': 3, 'env_min_lod': 0, 'unused': 0, 'soft_depth': 100.0,
            'greyscale': '', 'env_map': full['envmap'], 'normal': full['normal'], 'env_mask': '', **values}


def _unlit_shader(nif: NifFile, mat: ShapeMaterial, has_colors: bool) -> dict:
    """An effect shader with no material file and no scene lighting, as vanilla's 1,104 untextured ones.

    Flags: z-test always; z-write unless it blends; vertex colours and vertex
    alpha when the shape has colours (and FNV used their alpha); two-sided.
    """
    data = mat.data
    flags1 = UNLIT_FLAGS[0] | (UNLIT_VERTEX_ALPHA if has_colors and data['vertex_alpha'] else 0)
    flags2 = ((0 if mat.alpha and mat.alpha[0] & 1 else UNLIT_ZWRITE) | (UNLIT_COLORS if has_colors else 0)
              | (UNLIT_TWO_SIDED if data['two_sided'] else 0))
    return {'name': nif.string(''), 'extra': [], 'controller': NONE, 'flags1': flags1, 'flags2': flags2,
            'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0),
            'source_texture': f'textures\\{data["texture"]}' if data['texture'] else '', 'clamp': 3,
            'lighting_influence': 0, 'env_min_lod': 0, 'unused': 0, 'falloff': (1.0, 1.0, 1.0, 1.0),
            'base_color': (1.0, 1.0, 1.0, 1.0), 'base_color_scale': 1.0, 'soft_depth': 100.0, 'greyscale': '',
            'env_map': '', 'normal': '', 'env_mask': '', 'env_map_scale': 1.0}


def lighting_shader(nif: NifFile, material: str, texture_set: int, flags1: int) -> dict:
    """A lighting shader naming `material` (root material ''; `flags1` added), vanilla ClutterGenShelfA's values."""
    return {'shader_type': 0, 'name': nif.string(material), 'extra': [], 'controller': NONE,
            'flags1': SHADER_FLAGS[0] | flags1, 'flags2': SHADER_FLAGS[1],
            'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0),
            'texture_set': texture_set, 'emissive_color': (0.0, 0.0, 0.0), 'emissive_multiple': 1.0,
            'root_material': nif.empty_string(), 'clamp': 3, 'alpha': 1.0, 'refraction': 0.0, 'smoothness': 1.0,
            'specular_color': (1.0, 1.0, 1.0), 'specular_strength': 1.0, 'subsurface_rolloff': 0.0,
            'rimlight_power': 3.4028234663852886e38, 'backlight_power': 0.0, 'grayscale_scale': 0.501960813999176,
            'fresnel_power': 5.0, 'wetness': (-1.0,) * 6}


def posed(root, pose: dict) -> None:
    """Move the nodes under `root` that `pose` names: {name: (translation or None, rotation rows or None)}."""
    for node in root.tree():
        moved = pose.get(node.name.decode('cp1252')) if isinstance(node, NifFormat.NiNode) else None
        if moved and moved[0]:
            node.translation.x, node.translation.y, node.translation.z = moved[0]
        if moved and moved[1]:
            for i, row in enumerate(moved[1]):
                for j, value in enumerate(row):
                    setattr(node.rotation, f'm_{i + 1}{j + 1}', value)


def convert(path: str, texture_root=None, pose: dict = None) -> Converted:
    """The FO4 version of the FNV mesh at `path`; `texture_root` holds FNV's textures folder, `pose` moves
    named nodes first (posed())."""
    data = NifFormat.Data()
    with open(path, 'rb') as f:
        data.read(f)
    latch_source(data)
    root = data.roots[0]
    posed(root, pose or {})
    nif = NifFile()
    out = Converted(nif)
    node = {'name': nif.string(root.name.decode('cp1252')), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS,
            'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0, 'collision': NONE, 'children': []}
    nif.blocks.append(('NiNode', node))
    node['children'] = [i for g in _visible_shapes(root) for i in _shape_blocks(nif, g, root, out, texture_root)]
    bsx = sum(int(e.integer_data) for e in root.get_extra_datas() if isinstance(e, NifFormat.BSXFlags)) & BSX_KEPT
    bsx |= BSX_ARTICULATED if bsx & (BSX_HAVOK | BSX_COMPLEX) == BSX_HAVOK else 0
    if bsx:
        nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': bsx}))
        node['extra'].append(len(nif.blocks) - 1)
    collision_nodes(nif, root, 0, NODE_FLAGS)
    return out
