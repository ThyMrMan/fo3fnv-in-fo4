"""A look race's skin textures: Fallout 4's clean body and hands under FNV's race dirt, faded in from the body's
neck edge as Fallout 4's own dirty skin fades in over its clean one.

- Dirt: per channel, FNV's race texture over its stock one (both blurred past the DXT blocks), darkening only,
  over the race's overall shade, which the NPC's skin tone already carries (fnv_npc.race_shade).
- Body: the dirt carried onto Fallout 4's body UVs through the outfit body fit, faded by fade_curve.
- Drawn: the texture the skin tint `tint` draws as the clean texture's drawing times the dirt (skin_tint).

See: docs/fork/fo4_look_races_plan.md#body-transfer
"""

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.spatial import cKDTree

from fo4_import.face.bake import surface
from fo4_import.face.skin_tint import tinted, untinted
from fo4_import.face.texture import bilinear, surface_uv, texel_points
from fo4_import.nif.convert_static import NifFormat
from fo4_import.nif.outfit import FNV_BODIES, BodyFit, fnv_nif, fnv_skin, is_cap
from fo4_import.pipeline.export_index import export_file

#: The texture size the dirt and its fade are carried at, before they are resized to FO4's.
WORK = 1024
#: Gaussian blur (texels at a BLUR_AT texture) on FNV's textures, past their DXT blocks.
BLUR, BLUR_AT = 3.0, 1024
#: A stock texel under this share of the stock's median brightness is not bare skin (padding, underwear, shadow).
SKIN_SHARE = 0.5
#: The fade curve's step along the body from the neck edge (game units).
FADE_STEP = 1.0


def fnv_body(export_dir, sex: str, fit: BodyFit) -> tuple:
    """(placed points, triangles, UVs) of FNV's body of `sex`, in `fit.anchors` order moved onto FO4's body."""
    root = fnv_nif(export_file(export_dir, 'meshes', FNV_BODIES[sex]))
    geoms = [g for g in root.tree() if isinstance(g, NifFormat.NiTriBasedGeom) and g.skin_instance and not is_cap(g)]
    uvs = [fnv_skin(g, root)[3] for g in geoms]
    starts = np.cumsum([0] + [len(u) for u in uvs])
    tris = np.vstack([np.array([t for t in g.data.get_triangles() if len(set(t)) == 3]) + s
                      for g, s in zip(geoms, starts)])
    return fit.anchors + fit.offsets, tris, np.vstack(uvs)


def resized(image: np.ndarray, shape: tuple) -> np.ndarray:
    """Float image `image` bilinearly resized to `shape` (rows, columns), channel by channel."""
    if image.shape[:2] == tuple(shape[:2]):
        return image.astype(float)
    return np.stack([np.asarray(Image.fromarray(image[..., c].astype(np.float32)).resize(
        (shape[1], shape[0]), Image.BILINEAR)) for c in range(image.shape[2])], 2)


def _blurred(image: np.ndarray, skin: np.ndarray) -> np.ndarray:
    """`image`'s RGB blurred by BLUR (at its size) over the `skin` texels alone."""
    sigma = BLUR * image.shape[0] / BLUR_AT
    weight = np.maximum(gaussian_filter(skin.astype(float), sigma), 1e-6)
    return np.stack([gaussian_filter(image[..., c] * skin, sigma) / weight for c in range(3)], 2)


def _nearest_fill(image: np.ndarray, kept: np.ndarray) -> np.ndarray:
    """`image` with each texel outside `kept` its nearest kept texel's."""
    index = distance_transform_edt(~kept, return_distances=False, return_indices=True)
    return image[index[0], index[1]]


def skin_texels(stock: np.ndarray) -> np.ndarray:
    """Per texel of FNV stock texture `stock`, whether it is bare skin (SKIN_SHARE)."""
    light = stock[..., :3].mean(2)
    return light >= SKIN_SHARE * np.median(light[light > 0])


def dirt(race: np.ndarray, stock: np.ndarray, shade: np.ndarray) -> np.ndarray:
    """Per texel and channel, FNV texture `race` over `stock` (resized to it), both blurred over the stock's skin
    texels, at most 1, over `shade`; other texels take their nearest skin texel's."""
    clean = resized(stock, race.shape)
    skin = skin_texels(clean)
    ratio = np.minimum(_blurred(race, skin) / np.maximum(_blurred(clean, skin), 1.0), 1.0)
    return _nearest_fill(ratio, skin) / shade


def hand_dirt(race: np.ndarray, stock: np.ndarray, shade: np.ndarray) -> np.ndarray:
    """The median dirt() of FNV hand textures over the stock hand's skin texels."""
    return np.median(dirt(race, stock, shade)[skin_texels(resized(stock, race.shape))], 0)


def _filled(values: np.ndarray, rows: np.ndarray, cols: np.ndarray, size: int) -> np.ndarray:
    """A `size` square image of `values` at (rows, cols), each other texel its nearest set texel's."""
    out = np.zeros((size, size) + values.shape[1:])
    covered = np.zeros((size, size), bool)
    out[rows, cols], covered[rows, cols] = values, True
    return _nearest_fill(out, covered)


def carried(fit: BodyFit, fnv: tuple, fnv_image: np.ndarray, size: int = WORK) -> np.ndarray:
    """`fnv_image` (FNV body UVs) at each texel of a `size` FO4 body texture: its value where the texel's point
    projects onto the triangle of FNV's placed body `fnv` nearest it."""
    points, tris, uv = fnv
    samples, owner, _ = surface(points, tris)
    rows, cols, at = texel_points(fit.points, fit.uv, fit.tris, size)
    fnv_uv = surface_uv((points, tris[owner], uv), at, cKDTree(samples).query(at)[1])
    return _filled(bilinear(fnv_image, fnv_uv), rows, cols, size)


def neck_distance(fit: BodyFit, size: int = WORK) -> np.ndarray:
    """Per texel of a `size` FO4 body texture, its body point's distance from the body's neck edge (the open edge
    highest up)."""
    edges = [np.vstack(segments) for _, segments in fit.seams]
    neck = max(edges, key=lambda e: e[:, 2].mean())
    rows, cols, at = texel_points(fit.points, fit.uv, fit.tris, size)
    return _filled(cKDTree(neck).query(at)[0], rows, cols, size)


def fade_curve(distance: np.ndarray, clean: np.ndarray, dirty: np.ndarray) -> np.ndarray:
    """Per texel [h, w, 1] 0..1, how much of Fallout 4's dirty body `dirty` shows over `clean` at `distance` from
    the neck: their mean difference per FADE_STEP over the whole body's, never falling with distance, at most 1."""
    change = np.abs(resized(dirty, distance.shape)[..., :3] - resized(clean, distance.shape)[..., :3]).mean(2)
    steps = (distance / FADE_STEP).astype(int)
    sums, counts = np.bincount(steps.ravel(), change.ravel()), np.bincount(steps.ravel())
    curve = np.maximum.accumulate(sums / np.maximum(counts, 1) / change.mean())
    return np.minimum(curve, 1.0)[steps][..., None]


def drawn_dirt(clean: np.ndarray, dirt_image, weight, tint: np.ndarray) -> np.ndarray:
    """FO4 RGBA `clean` as the texture skin tint `tint` draws as `clean` drawn times `dirt_image` (an image,
    resized to it, or an RGB triple) faded by `weight` (likewise, or 1)."""
    ratio, fade = (resized(v, clean.shape) if np.ndim(v) == 3 else np.asarray(v, float) for v in (dirt_image, weight))
    out = clean.astype(float)
    out[..., :3] = untinted(np.clip(tinted(out[..., :3], tint) * (1.0 + (ratio - 1.0) * fade), 0, 255), tint)
    return np.clip(out, 0, 255).round().astype(np.uint8)
