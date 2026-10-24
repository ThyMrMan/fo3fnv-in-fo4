"""An FNV static mesh as a Fallout 4 one: geometry, lighting shaders and their BGSM materials.

Every visible NiTriShape/NiTriStrips becomes one BSTriShape under the root
NiNode, its transform baked in; its textures and alpha become a material
`materials\\fnv\\<diffuse path>.bgsm`, shared by every shape with the same
contents: every field a material or derived map holds is in its path (a tag
for each field off its usual value). Collision becomes pre-Elric Havok blocks
(collision.py; elric.finish makes them FO4 physics). Textures keep their FNV
paths under `textures\\fnv\\`.

See: docs/fork/fo4_spikes.md#spike-2-static
See: docs/fork/fo4_tool_audit.md#meshes
"""

import collections
import functools
import hashlib
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
from fo4_import.nif.animation import add_nodes, animatable, controllers, kept_nodes, manager_of, skin, with_parents
from fo4_import.nif.particles import add_system, systems as particle_systems, wanted_nodes
from fo4_import.nif.glow_scale import fo4_glow
from fo4_import.nif.shader_anim import GLOW_SUFFIX
from fo4_import.spike.imagespace import DISPLAY_GAMMA
from fo4_import.nif.collision import collision_nodes, moves, node_transform

PREFIX = 'fnv'
#: BSVertexDesc of a vanilla static shape (ClutterGen, SetDressing): half positions, UV, normal, tangent.
DESC_PLAIN = 0x1B00000430205
#: The same with vertex colours.
DESC_COLOR = 0x3B00005430206
#: Root NiNode flags and lighting shader flags of vanilla ClutterGenShelfA.
NODE_FLAGS, SHADER_FLAGS = 0xE, (0x80400201, 0x11)
#: Texture set slots a lighting shader fills (vanilla: 10, specular at 7).
TEXTURE_SLOTS, SLOT_SPECULAR = 10, 7
#: A glow-mapped lighting shader's type and flags2 bit, as vanilla cagebulb01.nif (type 2, flags2 0x41).
SHADER_GLOW, GLOW_MAP_FLAG = 2, 0x40
#: The glow map's slot in an FNV texture set and in FO4's.
GLOW_SLOT = 2
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
#: FNV BSXFlags bits kept (same meaning in FO4): Havok, Complex, Dynamic, Articulated; vanilla statics carry 0x82.
BSX_KEPT = 0x2 | 0x8 | 0x40 | 0x80
#: BSXFlags Havok, Complex, Articulated: vanilla meshes with Havok, not Complex (2,352), or joints set Articulated.
BSX_HAVOK, BSX_COMPLEX, BSX_DYNAMIC, BSX_ARTICULATED = 0x2, 0x8, 0x40, 0x80
#: BSXFlags Animated: on every vanilla door and container mesh with a NiControllerManager (animation).
BSX_ANIMATED = 0x1
#: BSXFlags Addon: set on vanilla meshes with add-on nodes (WorkstationWoodCookingFire 0x29B, BarrelTank 0x5B).
BSX_ADDON = 0x10
BGSM_TEXTURES = ('diffuse', 'normal', 'smooth_spec', 'greyscale', 'envmap', 'glow', 'inner_layer', 'wrinkles',
                 'displacement')
#: Vanilla ChemistrySetBeaker01's effect shader: flags, lighting influence, falloff, base colour, env map scale.
EFFECT_FLAGS = (0xA00000C0, 0x40000010)
BEAKER_SHADER = {'lighting_influence': 242, 'falloff': (1.0, -4.371138828673793e-08, 0.6000000238418579, 1.0),
                 'base_color': (0.18039216101169586, 0.18823537230491638, 0.20392164587974548, 0.8999999761581421),
                 'base_color_scale': 0.20000000298023224, 'env_map_scale': 2.0}
#: Effect shader flags of an unlit FNV shape: (flags1 z-test, flags2 0); the bits added per shape (Double_Sided: any).
UNLIT_FLAGS, UNLIT_VERTEX_ALPHA = (0x80000000, 0), 0x8
UNLIT_ZWRITE, DOUBLE_SIDED, UNLIT_COLORS = 0x1, 0x10, 0x20
#: Effect shader flags1 Use_Falloff (nif.xml Fallout4ShaderPropertyFlags1 bit 6).
USE_FALLOFF = 0x40
#: Flags1 Soft_Effect (bit 30) and its depth: all 31 vanilla beam BGEMs (two-sided, view falloff) are soft, median 150.
SOFT_EFFECT, SOFT_DEPTH = 0x40000000, 150.0
#: Shader flags1 External_Emittance (bit 29): the reference's XEMI colours the shape, as FNV's sf_external_emittance.
EXTERNAL_EMITTANCE = 0x20000000
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
#: Vanilla NeonRed01.BGEM (signgeneralopen.nif's neon): additive (src alpha, one), unlit, no z-write.
NEON_EFFECT = dict(TRANSLUCENT_EFFECT, src_blend=6, dst_blend=0, effect_lighting=False)
#: Its NIF effect shader: values, flags (z-test only) and alpha property (blend 0x100D).
NEON_SHADER = {'lighting_influence': 255, 'falloff': (1.0, 1.0, 0.0, 0.0), 'env_map_scale': 1.0}
NEON_FLAGS, NEON_ALPHA = (0x80000000, 0x0), (0x100D, 128)
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
#: Game units a blended sheet's vertices may stand off its plane and still count as flat (overlay_sheet).
SHEET_DEPTH = 0.5
#: NiMaterialProperty's default glossiness, the most common one: a specular map at it keeps the plain name.
GLOSSINESS = 10.0
#: (blend bits, alpha test ref) of most FNV glass and see-through surfaces: blend, src alpha, inverse src alpha.
EFFECT_ALPHA = (0xED, 0)
#: FNV grass (TallGrassShaderProperty) lit as vanilla grass is, its most common setting (fo4_spikes.md#spike-4-exterior).
GRASS_LIGHTING = {'subsurface': True, 'subsurface_rolloff': 4.0, 'backlight_power': 12.5}
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

    `spec_maps` is {FO4 specular map path: (FNV normal map path, glossiness)},
    the maps to build from FNV's normal-map alpha; `effects` is {path: BGEM dict}; `animatable`: the FNV mesh
    has an animation it can keep (kept unless converted not `animated`).
    """
    nif: NifFile
    materials: dict = field(default_factory=dict)
    textures: set = field(default_factory=set)
    spec_maps: dict = field(default_factory=dict)
    effects: dict = field(default_factory=dict)
    animatable: bool = False
    glow_maps: dict = field(default_factory=dict)


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
    """(positions, UVs, normals, colours or None, triangles) of one FNV shape in the space of its ancestor
    `root`."""
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


def gloss_tag(glossiness: float) -> str:
    """Glossiness as a path tag: '' at GLOSSINESS, else its exact value, '.' as 'p'."""
    return '' if glossiness == GLOSSINESS else repr(float(glossiness)).removesuffix('.0').replace('.', 'p')


def spec_map_path(fnv_normal: str, glossiness: float = GLOSSINESS) -> str:
    """FO4 specular map of an FNV normal map: x_n.dds as x_s.dds, x_s_g<gloss_tag>.dds"""
    path = fo4_texture(fnv_normal).rsplit('.', 1)[0]
    tag = gloss_tag(glossiness)
    return (path[:-2] if path.endswith('_n') else path) + '_s' + (f'_g{tag}' if tag else '') + '.dds'


def spec_glossiness(spec_path: str) -> float:
    """The glossiness spec_map_path() named `spec_path` for."""
    _, sep, tag = spec_path.rsplit('.', 1)[0].rpartition('_s_g')
    plain = not sep or not tag or any(c in tag for c in '_/\\')
    return GLOSSINESS if plain else float(tag.replace('p', '.'))


def _specular(mat: dict, fnv_normal: str, props: dict, texture_root) -> 'tuple | None':
    """Set `mat`'s specular from FNV's normal-map alpha; (map path, (normal, glossiness)) or None.

    Specular is off when the alpha carries no mask (spec_mask's rule, which
    ignores the mesh's material colour) or the map is not square.
    """
    source = Path(texture_root) / texture_source(fnv_normal).replace('\\', '/') if texture_root and fnv_normal else None
    data = source.read_bytes() if source and source.exists() else b''
    if not spec_mask.has_mask(data) or not _square(data):
        mat['specular'] = False
        return None
    material = props.get('NiMaterialProperty')
    glossiness = material.glossiness if material else 0.0
    path = spec_map_path(fnv_normal, glossiness)
    mat['textures']['smooth_spec'] = path.replace('\\', '/')
    return path, (fnv_normal, glossiness)


def specular_scale(smooth: float) -> float:
    """FO4 specular per unit of FNV's, at equal energy: 2 pi / (n + 2)."""
    return min(1.0, math.pi * (1.0 - smooth) ** 4)


def spec_image(normal_dds: bytes, smooth: float) -> np.ndarray:
    """The RGB image of an FO4 specular map: R the normal map's alpha scaled by specular_scale(), G the
    smoothness."""
    alpha = np.asarray(Image.open(io.BytesIO(normal_dds)).convert('RGBA'))[:, :, 3]
    out = np.zeros(alpha.shape + (3,), np.uint8)
    out[:, :, 0] = np.round(alpha * specular_scale(smooth)).astype(np.uint8)
    out[:, :, 1] = int(round(smooth * 255))
    return out


def _beside(stem: str, suffix: str) -> str:
    """A diffuse `stem`'s usual companion: `stem` (`_d` dropped) plus `suffix`."""
    return (stem[:-2] if stem.endswith('_d') else stem) + suffix


def _hashed(letter: str, value: str, usual: str) -> str:
    """The path tag `_<letter><6 hex of value's SHA-1>`; '' when `value` is `usual`."""
    return '' if value == usual else f'_{letter}{hashlib.sha1(value.encode()).hexdigest()[:6]}'


def glow_map_path(fnv_diffuse: str, fnv_glow: str, cut: 'int | None' = None) -> str:
    """FO4 path of glow_image's bake: <diffuse>_<glow name>[_f<folder hash>][_cut<cut>].dds, the folder tag when
    the glow map is not beside the diffuse."""
    diffuse = fo4_texture(fnv_diffuse).rsplit('.', 1)[0]
    folder, _, glow = fo4_texture(fnv_glow).rsplit('.', 1)[0].rpartition('\\')
    tag = _hashed('f', folder, diffuse.rpartition('\\')[0])
    return f'{diffuse}_{glow}{tag}{"" if cut is None else f"_cut{cut}"}.dds'


def glow_image(diffuse_dds: bytes, glow_dds: bytes, cut: 'int | None' = None) -> Image.Image:
    """FNV's glow as FO4's: the diffuse colour times the glow map's, at the diffuse's size. With a `cut` (the neon
    overlay) it is black where the diffuse's alpha is below `cut` (FNV's alpha test), raised so its brightest texel
    is white, as vanilla's neon tubes are, and stored as linear light (^ DISPLAY_GAMMA), as the effect shader shows it.

    See: docs/fork/fo4_look.md#emissive
    """
    source = Image.open(io.BytesIO(diffuse_dds)).convert('RGBA')
    glow = Image.open(io.BytesIO(glow_dds)).convert('RGB').resize(source.size, Image.BILINEAR)
    pixels = np.asarray(source, np.float32)
    lit = pixels[:, :, :3] * (np.asarray(glow, np.float32) / 255)
    if cut is not None:
        lit[pixels[:, :, 3] < cut] = 0
        lit = 255 * (lit / max(float(lit.max()), 1.0)) ** DISPLAY_GAMMA
    return Image.fromarray(np.round(lit).astype(np.uint8), 'RGB')


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
    glow: 'tuple | None' = None
    overlay: 'ShapeMaterial | None' = None


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


def _unlit(shader, alpha, two_sided: bool, fades: bool, normals: bool) -> ShapeMaterial:
    """An FNV BSShaderNoLightingProperty shape: its texture, vertex alpha, blend, sidedness and view falloff.

    One that fades by vertex alpha (`fades`: some vertex alpha below 1, sf_vertex_alpha) blends with no
    NiAlphaProperty, as FNV's baked soft shadows do; an untextured one that fades has only its vertex
    alpha to blend by, flagged or not (NV_NoSo_RanchHouse03:1). A shape with `normals` keeps FNV's view
    falloff (angle cosines, opacities), as FNV applies it.
    See: docs/fork/fo4_pipeline.md#effects
    """
    fnv = shader.file_name.decode('cp1252')
    vertex_alpha = bool(shader.shader_flags.sf_vertex_alpha) or (not fnv and fades)
    falloff = tuple(getattr(shader, f'falloff_{k}') for k in ('start_angle', 'stop_angle', 'start_opacity',
                                                               'stop_opacity')) if normals else None
    data = {'texture': fo4_texture(fnv), 'vertex_alpha': vertex_alpha, 'two_sided': two_sided, 'falloff': falloff,
            'external': bool(shader.shader_flags.sf_external_emittance)}
    part = _alpha_part(alpha) or (VERTEX_ALPHA_BLEND if vertex_alpha and fades else None)
    return ShapeMaterial('unlit', '', data, [fnv] if fnv else [], part, None)


def texel_peaks(root, texture_root) -> dict:
    """{shape name: brightest texel x vertex colour at its vertices} of FNV `root`'s unlit shapes whose texture is
    found under `texture_root`: what their emittance multiplies (glow_scale.map_keys' `peak`)."""
    out = {}
    for geom in (g for g in root.tree() if isinstance(g, NifFormat.NiTriBasedGeom)):
        shader = next((p for p in geom.get_properties() if type(p).__name__ == 'BSShaderNoLightingProperty'), None)
        fnv = shader.file_name.decode('cp1252') if shader else ''
        path = Path(texture_root) / texture_source(fnv).replace('\\', '/') if texture_root and fnv else None
        if path is None or not path.exists() or not geom.data.uv_sets:
            continue
        image = np.asarray(Image.open(path).convert('RGB'), np.float32) / 255
        height, width, _ = image.shape
        data = geom.data
        texels = np.array([image[int(uv.v % 1 * height), int(uv.u % 1 * width)] for uv in data.uv_sets[0]])
        if data.has_vertex_colors:
            texels *= np.array([(c.r, c.g, c.b) for c in data.vertex_colors], np.float32)
        out[geom.name.decode('cp1252')] = float(texels.max()) if len(texels) else 1.0
    return out


def _effect(fnv: list, alpha) -> ShapeMaterial:
    """Alpha-blended FNV glass as vanilla's beaker glass, with FNV's textures and blend."""
    tex = [fo4_texture(t).replace('\\', '/') if t else '' for t in fnv + [''] * 6]
    data = dict(GLASS_EFFECT, **_alpha_fields(alpha), env_mapping=bool(tex[4]),
                textures={'base': tex[0], 'grayscale': '', 'envmap': tex[4], 'normal': tex[1], 'env_mask': ''})
    stem = tex[0].replace('/', '\\').rsplit('.', 1)[0] or f'{PREFIX}\\untextured'
    return ShapeMaterial('effect', f'materials\\{stem}_effect{effect_tags(data)}.bgem', data,
                         [t for i, t in enumerate(fnv[:5]) if t and i in (0, 1, 4)], _alpha_part(alpha), None)


def effect_tags(data: dict) -> str:
    """BGEM `data`'s path tags for what its plain name leaves out: blend and alpha test other than EFFECT_ALPHA
    (`_a<bits>_<ref>`), a normal map other than `<base>_n` (`_n<hash>`), an env map (`_e<hash>`)."""
    tex = data['textures']
    bits = int(data['alpha_blend']) | data['src_blend'] << 1 | data['dst_blend'] << 5 | int(data['alpha_test']) << 9
    alpha = '' if (bits, data['alpha_test_ref']) == EFFECT_ALPHA else f'_a{bits:x}_{data["alpha_test_ref"]}'
    return alpha + _hashed('n', tex['normal'], _beside(tex['base'].rsplit('.', 1)[0], '_n.dds')) + \
        _hashed('e', tex['envmap'], '')


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
    return ShapeMaterial('effect', f'materials\\{stem}{"_2s" if two_sided else ""}_translucent{effect_tags(data)}.bgem',
                         data, [t for t in fnv[:2] if t], _alpha_part(alpha), None, (WING_SHADER, flags))


def _lit_alpha(alpha, decal: bool) -> 'tuple | None':
    """A lit shape's FNV alpha as FO4 draws it: decals keep their blend; other blends become a cut-out."""
    if alpha is None or not alpha.flags & 1 or decal:
        return _alpha_part(alpha)
    threshold = alpha.threshold if alpha.flags & ALPHA_TEST_BIT else CUTOUT_REF
    return (alpha.flags & ~1) | ALPHA_TEST_BIT, threshold


def lit_material(fnv: list, props: dict, alpha, two_sided: bool, decal: bool, texture_root) -> ShapeMaterial:
    """A lit FNV shape's BGSM: its textures, spec map, sidedness and alpha as FO4 draws it (_lit_alpha)."""
    mat = dict(MATERIAL, root_material='', two_sided=two_sided, decal=decal,
               textures={**dict.fromkeys(BGSM_TEXTURES, '')})
    mat.update(GRASS_LIGHTING if 'TallGrassShaderProperty' in props else {})
    mat['textures']['diffuse'] = fo4_texture(fnv[0]).replace('\\', '/')
    mat['textures']['normal'] = fo4_texture(fnv[1] if len(fnv) > 1 else '').replace('\\', '/')
    spec = _specular(mat, fnv[1] if len(fnv) > 1 else '', props, texture_root)
    part = _lit_alpha(alpha, decal)
    cut = bool(part and part[0] & ALPHA_TEST_BIT)
    suffix = ('_2s' if two_sided else '') + ('' if cut else _glow(mat, fnv, props))
    if part is not None:
        mat.update(_alpha_fields_of(*part))
        suffix += f'_a{part[0]:x}_{part[1]}'
    stem = mat['textures']['diffuse'].replace('/', '\\').rsplit('.', 1)[0] or f'{PREFIX}\\untextured'
    textures = list(fnv[:GLOW_SLOT + 1]) if mat['glowmap'] else [t for t in fnv[:2] if t]
    glow = (glow_map_path(fnv[0], fnv[GLOW_SLOT]), (fnv[0], fnv[GLOW_SLOT], None)) if mat['glowmap'] and fnv[0] \
        else None
    overlay = _glow_overlay(fnv, props, two_sided, part[1]) if cut and len(fnv) > GLOW_SLOT and fnv[GLOW_SLOT] \
        and fnv[0] else None
    return ShapeMaterial('lit', f'materials\\{stem}{suffix}{lit_tags(mat)}.bgsm', mat, textures, part, spec,
                         flags1=DECAL_FLAGS if decal else 0, glow=glow, overlay=overlay)


def lit_tags(mat: dict) -> str:
    """BGSM `mat`'s path tags for what its plain name leaves out: a normal map other than the diffuse's `_n`
    (_beside; `_n<hash>`), a glow map other than the bake of its `_g` (`_l<hash>`), the specular map's glossiness
    tag (`_g<tag>`), a decal (`_decal`). Specular itself follows the normal map."""
    tex = mat['textures']
    stem = tex['diffuse'].rsplit('.', 1)[0]
    glow = f'{stem}_{_beside(stem.rsplit("/", 1)[-1], "_g")}.dds' if mat['glowmap'] else ''
    gloss = gloss_tag(spec_glossiness(tex['smooth_spec'])) if tex['smooth_spec'] else ''
    return (_hashed('n', tex['normal'], _beside(stem, '_n.dds')) + _hashed('l', tex['glow'], glow)
            + (f'_g{gloss}' if gloss else '') + ('_decal' if mat['decal'] else ''))


def retextured(path: str, old: dict, new: dict) -> str:
    """Path of BGSM `new`, `old` (at `path`) retextured: its diffuse and lit_tags."""
    base = path.rsplit('.', 1)[0].removesuffix(lit_tags(old))
    return base.replace(_diffuse_stem(old), _diffuse_stem(new), 1) + lit_tags(new) + '.bgsm'


def _diffuse_stem(mat: dict) -> str:
    """BGSM `mat`'s diffuse path without its extension, with backslashes."""
    return mat['textures']['diffuse'].rsplit('.', 1)[0].replace('/', '\\')


def _emission(props: dict) -> tuple:
    """(colour clamped to 0-1, multiplier) of an FNV shape's NiMaterialProperty emission; white x1 without one."""
    material = props.get('NiMaterialProperty')
    if material is None:
        return (1.0, 1.0, 1.0), 1.0
    color = tuple(max(0.0, min(1.0, float(getattr(material.emissive_color, c)))) for c in 'rgb')
    return color, float(getattr(material, 'emit_multi', 1.0))


def _glow_overlay(fnv: list, props: dict, two_sided: bool, cut: int) -> ShapeMaterial:
    """An alpha-tested glow shape's glow as vanilla's neon (NeonRed01.BGEM): additive, unlit, its glow map baked
    black past alpha threshold `cut`; a decal over the shape's own triangles, as vanilla's eyeao.bgem overlays the eye.
    Its brightness is FNV's multiplier ranked into vanilla's neon range (glow_scale).

    See: docs/fork/fo4_look.md#emissive
    """
    color, fnv_mult = _emission(props)
    mult = fo4_glow('neon', fnv_mult)
    baked = glow_map_path(fnv[0], fnv[GLOW_SLOT], cut)
    data = dict(NEON_EFFECT, two_sided=two_sided, decal=True, base_color=color, base_color_scale=mult,
                textures={'base': baked.replace('\\', '/'), 'grayscale': '', 'envmap': '', 'normal': '', 'env_mask': ''})
    values = dict(NEON_SHADER, base_color=(*color, 1.0), base_color_scale=mult)
    flags = (NEON_FLAGS[0] | DECAL_FLAGS, NEON_FLAGS[1] | (DOUBLE_SIDED if two_sided else 0))
    look = ''.join(f'{round(c * 255):02x}' for c in color) + f'x{mult:.3g}' + ('_2s' if two_sided else '')
    return ShapeMaterial('effect', f'materials\\{baked.rsplit(".", 1)[0]}_neon{look}.bgem', data,
                         [fnv[0], fnv[GLOW_SLOT]], NEON_ALPHA, None, (values, flags),
                         glow=(baked, (fnv[0], fnv[GLOW_SLOT], cut)))


def _glow(mat: dict, fnv: list, props: dict) -> str:
    """Give `mat` FNV's glow map (texture set slot 2), lit by the shape's emissive colour, its multiplier ranked
    into vanilla's lit glow range (glow_scale); the material path's suffix for it ('' without one).

    See: docs/fork/fo4_look.md#emissive
    """
    if len(fnv) <= GLOW_SLOT or not fnv[GLOW_SLOT]:
        return ''
    shader = props.get('BSShaderPPLightingProperty')
    color, mult = _emission(props)
    external = bool(shader and shader.shader_flags.sf_external_emittance)
    glow = glow_map_path(fnv[0], fnv[GLOW_SLOT]) if fnv[0] else fo4_texture(fnv[GLOW_SLOT])
    mat['textures']['glow'] = glow.replace('\\', '/')
    mat.update(glowmap=True, emittance=True, emittance_color=color, emittance_mult=fo4_glow('lit', mult),
               external_emittance=external)
    return '_glow' + ''.join(f'{round(c * 255):02x}' for c in color) + (f'x{mult:g}' if mult != 1.0 else '') + \
        ('e' if external else '')


def _fades(geom) -> bool:
    """Whether an FNV shape has a vertex alpha below 1."""
    return bool(geom.data.has_vertex_colors and any(c.a < 1 for c in geom.data.vertex_colors))


def _material(geom, texture_root=None) -> ShapeMaterial:
    """The FO4 material of an FNV shape.

    Unlit shapes get an inline effect shader. A blended one with a mostly
    see-through texture gets vanilla's beaker BGEM when environment-mapped
    or additive (FNV glass), else its insect-wing BGEM; the rest a BGSM (blended decals as
    FO4 decals, other blends as cut-outs whose see-through triangles split off
    to that BGEM: `split`). FO4 draws no blended lit surface but a decal. A
    NiStencilProperty makes it two-sided.

    See: docs/fork/fo4_spikes.md#spike-2-transparency
    """
    props = {type(p).__name__: p for p in geom.get_properties()}
    alpha, two_sided = props.get('NiAlphaProperty'), 'NiStencilProperty' in props
    if 'BSShaderNoLightingProperty' in props:
        return _unlit(props['BSShaderNoLightingProperty'], alpha, two_sided, _fades(geom), bool(geom.data.has_normals))
    shader, grass = props.get('BSShaderPPLightingProperty'), props.get('TallGrassShaderProperty')
    fnv = [t.decode('cp1252') for t in shader.texture_set.textures] if shader and shader.texture_set else \
        [grass.file_name.decode('cp1252')] if grass else ['']
    blended = alpha is not None and alpha.flags & 1 and shader
    glass = bool(blended and (shader.shader_flags.sf_environment_mapping or not alpha.flags >> 5 & 0xF))
    flags = shader.shader_flags if shader else None
    decal = bool(flags and (flags.sf_decal_single_pass or flags.sf_dynamic_decal_single_pass)) or \
        bool(blended and not glass and overlay_sheet(geom))
    texture = Path(texture_root) / texture_source(fnv[0]).replace('\\', '/') if texture_root and fnv[0] else None
    cut_from_blend = bool(blended and not decal and not alpha.flags & ALPHA_TEST_BIT and texture)
    clear = _effect(fnv, alpha) if glass else _translucent(fnv, alpha, two_sided) if cut_from_blend else None
    splits = cut_from_blend or bool(glass and alpha.flags >> 5 & 0xF and texture and not translucent(texture))
    if clear and not splits or splits and translucent(texture):
        return clear
    mat = lit_material(fnv, props, alpha, two_sided, decal, texture_root)
    if splits:
        mat.split = (clear, texture)
    return mat


def overlay_sheet(geom) -> bool:
    """Whether FNV shape `geom` is a still, flat sheet (no controller or skin; every vertex within SHEET_DEPTH of
    one plane): graffiti, posters, stains and blood, which FO4 places as decal meshes.
    See: docs/fork/fo4_pipeline.md#overlay-decals
    """
    if geom.controller is not None or geom.skin_instance is not None or geom.data.num_vertices < 3:
        return False
    points = np.array([(v.x, v.y, v.z) for v in geom.data.vertices])
    centred = points - points.mean(axis=0)
    normal = np.linalg.svd(centred, full_matrices=False)[2][-1]
    return bool(np.abs(centred @ normal).max() < SHEET_DEPTH)


def _visible_shapes(root) -> list:
    """FNV shapes that render: shaded triangles, not hidden or editor markers.

    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    return [g for g in root.tree() if isinstance(g, NifFormat.NiTriBasedGeom) and not g.flags & 1
            and not g.name.lower().startswith(b'editormarker') and g.data is not None and _shaded(g)]


def _shaded(geom) -> bool:
    """Whether an FNV shape has a shader (or old texturing) property."""
    return any(isinstance(p, (NifFormat.BSShaderProperty, NifFormat.NiTexturingProperty)) for p in geom.get_properties())


def emit(nif: NifFile, name: str, geometry: tuple, tris: np.ndarray, mat: ShapeMaterial, out: Converted) -> int:
    """Append one FO4 shape (`tris` of `geometry`, its used vertices only) with `mat`'s blocks; its index."""
    pos, uv, nrm, colors, _ = geometry
    used, local = np.unique(tris, return_inverse=True)
    pos, uv, nrm = pos[used], uv[used], nrm[used]
    colors, tris = (colors[used] if colors is not None else None), local.reshape(-1, 3)
    index = len(nif.blocks)
    center = (pos.min(axis=0) + pos.max(axis=0)) / 2
    shape = {'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS,
             'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0, 'collision': NONE,
             'bound': (*map(float, center), float(np.linalg.norm(pos - center, axis=1).max())),
             'skin': NONE, 'shader': NONE, 'alpha_property': NONE,
             'vertex_desc': DESC_COLOR if colors is not None else DESC_PLAIN,
             'vertices': vertices(pos, uv, nrm, colors, tris), 'triangles': [tuple(map(int, t)) for t in tris]}
    nif.blocks.append(('BSTriShape', shape))
    shape['shader'], shape['alpha_property'] = material_blocks(nif, mat, out, colors is not None)
    return index


def material_blocks(nif: NifFile, mat: ShapeMaterial, out: Converted, has_colors: bool) -> tuple:
    """Append `mat`'s shader (and texture set) and alpha property, registering its files in `out`; (shader, alpha)
    indices, alpha -1 without one."""
    if mat.kind != 'unlit':
        (out.effects if mat.kind == 'effect' else out.materials)[mat.path] = mat.data
    out.textures |= {t for t in mat.textures if t}
    if mat.spec:
        out.spec_maps[mat.spec[0]] = mat.spec[1]
    if mat.glow:
        out.glow_maps[mat.glow[0]] = mat.glow[1]
    shader = len(nif.blocks)
    if mat.kind == 'effect':
        nif.blocks.append(('BSEffectShaderProperty', _effect_shader(nif, mat)))
    elif mat.kind == 'unlit':
        nif.blocks.append(('BSEffectShaderProperty', _unlit_shader(nif, mat, has_colors)))
    else:
        nif.blocks += _lit_blocks(nif, mat, shader - 1)
    if not mat.alpha:
        return shader, NONE
    nif.blocks.append(('NiAlphaProperty', {'name': NONE, 'extra': [], 'controller': NONE,
                                           'alpha_flags': mat.alpha[0], 'threshold': mat.alpha[1]}))
    return shader, len(nif.blocks) - 1


def opaque(colors: np.ndarray) -> np.ndarray:
    """`colors` with alpha 1 (a lit shape: SHADER_FLAGS has no vertex alpha).
    See: docs/fork/fo4_pipeline.md#vertex-alpha
    """
    return np.column_stack([colors[:, :3], np.ones(len(colors))])


def is_grass(geom) -> bool:
    """Whether an FNV shape draws as grass (TallGrassShaderProperty): its vertex alpha anchors the blades.
    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    return any(isinstance(p, NifFormat.TallGrassShaderProperty) for p in geom.get_properties())


def _shape_blocks(nif: NifFile, geom, root, out: Converted, texture_root) -> list:
    """Append one FNV shape as FO4 shapes: one, or a cut-out plus its see-through triangles; their indices."""
    geometry = _geometry(geom, root)
    tris, mat, name = geometry[4], _material(geom, texture_root), geom.name.decode('cp1252')
    if mat.kind == 'lit' and geometry[3] is not None and not is_grass(geom):
        geometry = (*geometry[:3], opaque(geometry[3]), tris)
    if mat.split:
        see_through = translucent_triangles(mat.split[1], geometry[1], tris)
        if see_through.all():
            mat = mat.split[0]
        elif see_through.any():
            return [emit(nif, name, geometry, tris[~see_through], mat, out),
                    emit(nif, name, geometry, tris[see_through], mat.split[0], out)]
    made = [emit(nif, name, geometry, tris, mat, out)]
    return made + ([emit(nif, name + GLOW_SUFFIX, geometry, tris, mat.overlay, out)] if mat.overlay else [])


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
    alpha when the shape has colours (and FNV used their alpha); two-sided; FNV's falloff when it has one, and
    soft when also two-sided (a beam, faded where it meets geometry); coloured by the reference's emittance (XEMI).
    """
    data = mat.data
    beam = bool(data['falloff'] and data['two_sided'])
    flags1 = (UNLIT_FLAGS[0] | (UNLIT_VERTEX_ALPHA if has_colors and data['vertex_alpha'] else 0)
              | (USE_FALLOFF if data['falloff'] else 0) | (SOFT_EFFECT if beam else 0)
              | (EXTERNAL_EMITTANCE if data['external'] else 0))
    flags2 = ((0 if mat.alpha and mat.alpha[0] & 1 else UNLIT_ZWRITE) | (UNLIT_COLORS if has_colors else 0)
              | (DOUBLE_SIDED if data['two_sided'] else 0))
    return {'name': nif.string(''), 'extra': [], 'controller': NONE, 'flags1': flags1, 'flags2': flags2,
            'uv_offset': (0.0, 0.0), 'uv_scale': (1.0, 1.0),
            'source_texture': f'textures\\{data["texture"]}' if data['texture'] else '', 'clamp': 3,
            'lighting_influence': 0, 'env_min_lod': 0, 'unused': 0, 'falloff': data['falloff'] or (1.0, 1.0, 1.0, 1.0),
            'base_color': (1.0, 1.0, 1.0, 1.0), 'base_color_scale': 1.0,
            'soft_depth': SOFT_DEPTH if beam else 100.0, 'greyscale': '',
            'env_map': '', 'normal': '', 'env_mask': '', 'env_map_scale': 1.0}


def _lit_blocks(nif: NifFile, mat: ShapeMaterial, index: int) -> list:
    """A lit shape's shader and texture set blocks; a glow-mapped one is a glow shader, as vanilla's.

    See: docs/fork/fo4_pipeline.md#glow
    """
    shader = lighting_shader(nif, mat.path, index + 2, mat.flags1)
    slots = [f'textures\\{fo4_texture(t)}' if t else '' for t in mat.textures] + [''] * TEXTURE_SLOTS
    if mat.spec:
        slots[SLOT_SPECULAR] = f'textures\\{mat.spec[0]}'
    if mat.data.get('glowmap'):
        shader.update(shader_type=SHADER_GLOW, flags2=shader['flags2'] | GLOW_MAP_FLAG)
    if mat.glow:
        slots[GLOW_SLOT] = f'textures\\{mat.glow[0]}'
    return [('BSLightingShaderProperty', shader), ('BSShaderTextureSet', {'textures': slots[:TEXTURE_SLOTS]})]


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


def convert(path: str, texture_root=None, pose: dict = None, animated: bool = True, addons: dict = None) -> Converted:
    """The FO4 version of the FNV mesh at `path`; `texture_root` holds FNV's textures folder, `pose` moves
    named nodes first (posed()), `addons` maps FNV ADDN indices to FO4's (nif.addons; none: add-on nodes left
    out). An animated mesh keeps its animated nodes, skins and controllers (nif.animation) unless not
    `animated` (a weapon, which FO4 animates through its behaviour graph; a load door, which FNV never opens)."""
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
    manager = manager_of(root)
    animate = animated and manager is not None and animatable(manager)
    kept = kept_nodes(root, manager) if animate else []
    joined = any(isinstance(b, NifFormat.bhkConstraint) for b in data.blocks)
    found = particle_systems(root)
    bones = _bones(root, kept or (with_parents(root, _has_body) if joined else []), found)
    nodes = add_nodes(nif, bones, root, NODE_FLAGS) if bones else {id(root): 0}
    out.animatable = manager is not None and animatable(manager)
    _shapes(nif, root, nodes, out, texture_root)
    made = _particles(nif, root, found, nodes, out, texture_root)
    added = _addon_nodes(nif, root, addons or {})
    bsx = sum(int(e.integer_data) for e in root.get_extra_datas() if isinstance(e, NifFormat.BSXFlags)) & BSX_KEPT
    bodies = [b for b in data.blocks if isinstance(b, NifFormat.bhkRigidBody)]
    bsx &= ~BSX_DYNAMIC if bodies and not any(moves(b) for b in bodies) else ~0
    bsx |= BSX_ADDON if added else 0
    bsx |= BSX_ARTICULATED if bsx & (BSX_HAVOK | BSX_COMPLEX) == BSX_HAVOK or joined else 0
    bsx |= BSX_ANIMATED if animate or found else 0
    if bsx:
        nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': bsx}))
        node['extra'].append(len(nif.blocks) - 1)
    if animate:
        controllers(nif, root, manager, nodes, made, texel_peaks(root, texture_root))
    collision_nodes(nif, root, 0, NODE_FLAGS, nodes)
    return out


def _bones(root, bones: list, found: list) -> list:
    """`bones` and the nodes FNV particle systems `found` hang under or name, with their parents, parents first."""
    if not found:
        return bones
    keep = {id(n) for n in bones} | wanted_nodes(root, found)
    return with_parents(root, lambda node: id(node) in keep)


def _particles(nif: NifFile, root, found: list, nodes: dict, out: Converted, texture_root) -> dict:
    """Append FNV particle systems `found` under their kept parents, each with its material's shader;
    {id(FNV controller): FO4 index} of their controllers.

    See: docs/fork/fo4_pipeline.md#particles
    """
    made, scene = {}, {'nodes': nodes, 'place': lambda geom: nodes[id(_owner(geom, root, nodes))], 'emitters': {}}
    for system in found:
        shader = material_blocks(nif, _material(system, texture_root), out, bool(system.data.has_vertex_colors))
        made.update(add_system(nif, system, scene['place'](system), shader, scene))
    return made


def _addon_nodes(nif: NifFile, root, addons: dict) -> bool:
    """FNV `root`'s shown add-on nodes as FO4 BSValueNodes on the root in its space, each ADDN index mapped by
    `addons` and named for it as vanilla's (AddOnNode04, a repeat AddOnNode04@#0); whether any was written.

    One under a hidden node (a vehicle's damage stage, shown once damaged) is left out.
    See: docs/fork/fo4_pipeline.md#addons
    """
    parents = {id(c): n for n in root.tree() if hasattr(n, 'children') for c in n.children if c is not None}
    seen = collections.Counter()
    for node in root.tree():
        chain, at = [], node
        while at is not None:
            chain.append(at)
            at = parents.get(id(at))
        shown = type(node).__name__ == 'BSValueNode' and not any(n.flags & 1 for n in chain)
        index = addons.get(int(node.value)) if shown else None
        if index is None:
            continue
        translation, rotation, scale = node_transform(node, root)
        name = f'AddOnNode{index:02d}' + (f'@#{seen[index] - 1}' if seen[index] else '')
        seen[index] += 1
        nif.blocks.append(('BSValueNode', {
            'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS,
            'translation': translation, 'rotation': rotation, 'scale': scale, 'collision': NONE, 'children': [],
            'value': index, 'value_flags': 0}))
        nif.blocks[0][1]['children'].append(len(nif.blocks) - 1)
    return bool(seen)


def _has_body(node) -> bool:
    """Whether FNV `node` carries a rigid body (a jointed mesh keeps it).

    See: docs/fork/fo4_pipeline.md#ragdolls
    """
    co = getattr(node, 'collision_object', None)
    return co is not None and type(getattr(co, 'body', None)).__name__.startswith('bhkRigidBody')


def _shapes(nif: NifFile, root, nodes: dict, out: Converted, texture_root) -> None:
    """Append FNV `root`'s visible shapes under their kept `nodes` (a skinned one under the root, skinned to
    them)."""
    for g in _visible_shapes(root):
        skinned = len(nodes) > 1 and g.skin_instance is not None
        owner = root if skinned else _owner(g, root, nodes)
        made = _shape_blocks(nif, g, owner, out, texture_root)
        nif.blocks[nodes[id(owner)]][1]['children'] += made
        if skinned:
            skin(nif, made, g, root, nodes)


def _owner(geom, root, nodes: dict):
    """The nearest of `geom`'s ancestors among the kept `nodes` ({id(FNV node): index}, the root included)."""
    parents = {id(child): node for node in root.tree() if hasattr(node, 'children') for child in node.children
               if child is not None}
    current = parents.get(id(geom), root)
    while id(current) not in nodes:
        current = parents.get(id(current), root)
    return current
