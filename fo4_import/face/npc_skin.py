"""One NPC's skin written onto its Creation Kit FaceGen head, as FNV draws it.

- Face: a base NPC's is T1 (FO4's template face plus FNV's colour offset and
  race skin, the tone kept in) with FNV's brows drawn over it, faded by the
  race's neck mask to the face set's untinted diffuse under the skin tint; an
  own face set's (a race with its own skin) is the CK's export scaled per
  channel to FNV's whole skin.
- Skin tone (QNAM): the tint drawing the neck as the template's times T1's
  tone and the race's shade (skin_seams.face_texture), or the NPC's own over an
  own face set's scale, so the body takes what the face does at the neck.
- Rear head: its own texture of FNV's colour (skin_seams.rear_texture) on the
  race skin's body (clean, as under an outfit), cut to the part's UV island at
  REAR_SIZE, the shape's UVs moved onto it, drawn with the skin tone; only the
  FaceGeom names it.
- Shine (own face sets): face and rear head specular maps from FNV's skin
  (skin_seams.shine_texture).

See: docs/fork/fo4_facegen_plan.md#build-faces
"""

import functools
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.face import facegeom, hair, skin_seams, tint
from fo4_import.face.bake import face_shape, positions, seam_tree, triangles, uvs, with_uvs
from fo4_import.face.texture import (ISLAND_PADDING, VANILLA_FACE, bilinear, dds_as, dds_like, texel_map,
                                     texel_points, vanilla_face_texture, write_dds)
from fo4_import.nif import file as nif_file

#: The rear head texture's size: its UV island (268 x 375 texels of the 2048 body texture) at about 1.5 x.
REAR_SIZE = 512
#: The texture set slot of the specular map.
SPECULAR = 7


@dataclass
class Skin:
    """One NPC's inputs: sex, FNV colour (fnv_face), own face set or not, FNV brows RGBA at the template face's
    size (base NPCs), FNV shine (fnv_shine) or None, the race's neck mask (0..1 at the template face's size),
    the NPC's QNAM RGB, the race skin's body _d and _s DDS bytes, the tint basis template's QNAM RGB, the
    race's overall shade (fnv_npc.race_shade), the face set's untinted diffuse RGB at the template face's size."""

    female: bool
    colour: tuple
    own: bool
    brows: object
    shine: object
    neck: np.ndarray
    qnam: np.ndarray
    rear: tuple
    template: np.ndarray
    shade: np.ndarray
    head: np.ndarray


def whole_scale(drawn: np.ndarray, face_geo: tuple, colour: tuple) -> np.ndarray:
    """Per channel, the face texture `drawn` (RGB) over FNV's whole skin on the same face texels."""
    fnv, (stock, offset, race_skin) = colour
    rows, cols, fnv_uv, _ = texel_map(face_geo, (fnv.mean, fnv.triangles, fnv.uvs), drawn.shape[:2])
    whole = bilinear(stock, fnv_uv) + bilinear(offset, fnv_uv)
    whole += 0 if race_skin is None else bilinear(race_skin, fnv_uv)
    return np.median(drawn[rows, cols], 0) / np.median(whole, 0)


def own_face_texture(diffuse: Path, face_geo: tuple, colour: tuple) -> np.ndarray:
    """Rewrite the CK's face texture of an own face set at `diffuse`, divided per channel by its whole_scale to
    FNV's whole skin (its median over the face); that scale.
    See: docs/fork/fo4_facegen_plan.md#willow-skin
    """
    rgba = hair.image(diffuse.read_bytes()).astype(float)
    scale = whole_scale(rgba[..., :3], face_geo, colour)
    rgba[..., :3] /= scale
    write_dds(np.clip(rgba, 0, 255).astype(np.uint8), diffuse)
    vanilla_face_texture(diffuse)
    return scale


@functools.cache
def template_face(female: bool) -> np.ndarray:
    """The tint template's face texture (RGBA) at the shipped face size."""
    size = VANILLA_FACE['d'][1]
    return np.asarray(Image.fromarray(tint.load_basis(female)[2]).resize((size, size), Image.BOX))


@functools.lru_cache(maxsize=4)
def untinted_face(src: facegeom.Sources, path: str, size: int) -> np.ndarray:
    """Face diffuse `path` (under Textures) through `src`, RGB floats at `size`."""
    rgb = np.asarray(hair.image(src.read('textures\\' + path)))[..., :3]
    return np.asarray(Image.fromarray(rgb).resize((size, size), Image.BOX), float)


def base_face_texture(skin: Skin, diffuse: Path, face_geo: tuple) -> np.ndarray:
    """Write a base NPC's face texture at `diffuse`: T1 with the tone kept in, faded at the neck, FNV's brows
    over it; its QNAM RGB (skin_seams.face_texture)."""
    neck = (skin.neck, skin.template, skin.shade, skin.head)
    rgba, qnam = skin_seams.face_texture(template_face(skin.female), face_geo, *skin.colour, neck)
    if skin.brows is not None:
        alpha = skin.brows[..., 3:] / 255
        rgba = rgba.astype(float)
        rgba[..., :3] = rgba[..., :3] * (1 - alpha) + skin.brows[..., :3] * alpha
        rgba = np.clip(rgba, 0, 255).astype(np.uint8)
    write_dds(rgba, diffuse)
    vanilla_face_texture(diffuse)
    return qnam


def shine_means(before: np.ndarray, after: np.ndarray, part: tuple) -> str:
    """Mean R and G over part `part`'s texels, before and after."""
    rows, cols, _ = texel_points(*part, before.shape[0])
    old, new = before[rows, cols, :2].mean(0), after[rows, cols, :2].mean(0)
    return f'specular R {old[0]:.1f} -> {new[0]:.1f}, smoothness G {old[1]:.1f} -> {new[1]:.1f}'


def face_shine(skin: Skin, specular: Path, face_geo: tuple, seam) -> str:
    """Rewrite the CK's face specular map at `specular` with FNV's shine, faded to it at the neck `seam`;
    shine_means' line."""
    own = specular.read_bytes()
    before = hair.image(own)
    after = skin_seams.shine_texture(before, face_geo, None, skin.colour[0], skin.shine, seam)
    specular.write_bytes(dds_like(after, own))
    return 'face ' + shine_means(before, hair.image(specular.read_bytes()), face_geo)


def skinned(skin: Skin, nif_bytes: bytes, folder: Path, stem: str, rear_name: tuple) -> tuple:
    """Write the NPC's skin (module doc): its face textures `folder`/`stem`_* in place, its rear head's at
    `rear_name` = (Textures folder, path under it without the `_d.dds`); (FaceGeom NIF bytes, QNAM RGB, lines)."""
    face_geo, seam = face_shape(nif_bytes), seam_tree(nif_bytes)
    diffuse = folder / f'{stem}_d.dds'
    if skin.own:
        qnam, whole = skin.qnam / own_face_texture(diffuse, face_geo, skin.colour), np.ones(3)
    else:
        qnam, whole = base_face_texture(skin, diffuse, face_geo), None
    qnam = np.clip(qnam, 0.0, 1.0)
    shine_neck = None if skin.shine is None else seam
    lines = [] if shine_neck is None else [face_shine(skin, folder / f'{stem}_s.dds', face_geo, shine_neck)]
    neck = (seam, (skin.template, qnam), None if skin.own else (face_geo[1], skin.neck))
    nif = rear_head(skin, nif_bytes, (face_geo[0], neck, whole, shine_neck), rear_name)
    return nif, qnam, lines


def island(uv: np.ndarray, size: int) -> tuple:
    """((u, v) low, (u, v) high): the square around UVs `uv` on a `size` square texture, ISLAND_PADDING texels out,
    on whole texels."""
    lo, hi = np.floor(uv.min(0) * size) - ISLAND_PADDING, np.ceil(uv.max(0) * size) + ISLAND_PADDING
    side = min(float((hi - lo).max()), size)
    lo = np.clip(np.floor((lo + hi - side) / 2), 0, size - side)
    return lo / size, (lo + side) / size


def cut(rgba: np.ndarray, box: tuple) -> np.ndarray:
    """`rgba`'s (square) region `box`."""
    (c0, r0), (c1, r1) = (np.round(corner * rgba.shape[0]).astype(int) for corner in box)
    return rgba[r0:r1, c0:c1]


def write_rear(rgba: np.ndarray, like: bytes, where: tuple) -> str:
    """Write `rgba` at REAR_SIZE in DDS `like`'s format at `where` = (Textures folder, path under it); the path."""
    root, name = where
    path = root / name.replace('\\', '/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dds_as(np.asarray(Image.fromarray(rgba).resize((REAR_SIZE, REAR_SIZE), Image.BILINEAR)), like))
    return name


def rear_head(skin: Skin, nif_bytes: bytes, place: tuple, rear_name: tuple) -> bytes:
    """The FaceGeom with each skin-tint part (the rear head) on its own textures, cut to its UV island, and drawn
    with the skin tone. `place` = (face points, neck as rear_texture takes it, whole scale or None, the neck as
    shine_texture takes it or None to copy the race skin's specular map)."""
    frame, neck, whole, shine_neck = place
    root, name = rear_name
    nif = nif_file.read(nif_bytes)
    for i, (kind, raw) in enumerate(list(nif.blocks)):
        sh = nif.blocks[hair.shader_index(raw)][1] if kind in facegeom.SHAPES and isinstance(raw, bytes) else None
        if not isinstance(sh, dict) or sh.get('skin_tint') is None:
            continue
        textures, own = nif.blocks[sh['texture_set']][1]['textures'], hair.image(skin.rear[0])
        box = island(uvs(raw), own.shape[0])
        part = (positions(raw), (uvs(raw) - box[0]) / (box[1] - box[0]), triangles(raw))
        rgba = skin_seams.rear_texture(cut(own, box), part, frame, skin.colour, neck, whole)
        textures[0] = write_rear(rgba, skin.rear[0], (root, f'{name}_d.dds'))
        spec = cut(hair.image(skin.rear[1]), box)
        if shine_neck is not None:
            spec = skin_seams.shine_texture(spec, part, frame, skin.colour[0], skin.shine, shine_neck)
        textures[SPECULAR] = write_rear(spec, skin.rear[1], (root, f'{name}_s.dds'))
        nif.blocks[i] = (kind, with_uvs(raw, part[1]))
        sh['skin_tint'] = (*(np.round(neck[1][1] * 255) / 255).tolist(), sh['skin_tint'][3])
    return nif_file.write(nif)


def tone_scale(qnam: np.ndarray, current: bytes) -> np.ndarray:
    """The per-channel scale taking QNAM bytes `current` to RGB `qnam`."""
    return qnam / np.maximum(np.array(struct.unpack('<4f', current)[:3]), 1e-6)
