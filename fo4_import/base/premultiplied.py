"""A replacer texture saved premultiplied (its color already times its alpha), mended against the texture it
replaces.

FNV and FO4 read a diffuse's color as is; alpha only cuts or blends. A
premultiplied replacer is black where its alpha is clear, which an opaque
material shows (the alpha of a siding that also serves alpha-tested ruins).
The test reads it against the texture it replaces, which is that texture's
authored color: where alpha is not solid, is the replacer's color nearer the
replaced color times alpha, or the replaced color? The mend adds back the
replaced color by the clear share.

See: docs/fork/fo4_plugin_layout.md#premultiplied-replacers
"""

import io
from pathlib import Path

import numpy as np
from PIL import Image

from asset_convert.texture.image_transcode import encode_dds

#: Alpha above which a texel counts as solid: the test reads the others.
SOLID = 224
#: Color the replaced texture needs at a texel for it to tell anything (dark there, both readings agree).
LIT = 24.0
#: Share of the texels that must be lit and not solid for the test to decide.
SHARE = 0.01
#: Part of a staged replacer texture's signature: bump it when mended() writes differently.
MENDED_VERSION = 1


def _rgba(data: bytes) -> np.ndarray:
    """DDS `data`'s top mip as float RGBA."""
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'), np.float32)


def _resized(rgb: np.ndarray, size: tuple) -> np.ndarray:
    """Float color `rgb` resampled to `size` (width, height), unweighted by any alpha."""
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')
    return np.asarray(image.resize(size, Image.BICUBIC), np.float32)


def premultiplied(replacer: np.ndarray, under: np.ndarray) -> bool:
    """Whether float RGBA `replacer`'s mean color where its alpha is not solid is nearer float RGB `under` (the
    replaced texture's color at the replacer's size, scaled to match where solid) times that alpha than `under`
    itself (module notes)."""
    alpha, mine, theirs = replacer[:, :, 3], replacer[:, :, :3].mean(axis=2), under.mean(axis=2)
    lit = theirs > LIT
    seen, solid = lit & (alpha <= SOLID), lit & (alpha > SOLID)
    if seen.mean() < SHARE:
        return False
    scale = mine[solid].mean() / theirs[solid].mean() if solid.any() else 1.0
    shown, kept = mine[seen].mean(), theirs[seen] * scale
    return bool(abs(shown - (kept * alpha[seen] / 255.0).mean()) < abs(shown - kept.mean()))


def mended(replacer: bytes, replaced: bytes) -> 'bytes | None':
    """DDS `replacer` with `replaced`'s color added back by its clear share (module notes), alpha kept; None when
    it is not premultiplied against `replaced`."""
    mine = _rgba(replacer)
    if (mine[:, :, 3] <= SOLID).mean() < SHARE:
        return None
    under = _resized(_rgba(replaced)[:, :, :3], (mine.shape[1], mine.shape[0]))
    if not premultiplied(mine, under):
        return None
    rgb = mine[:, :, :3] + (1.0 - mine[:, :, 3:] / 255.0) * under
    out = np.dstack([np.clip(np.round(rgb), 0, 255), mine[:, :, 3:]]).astype(np.uint8)
    return encode_dds(Image.fromarray(out, 'RGBA'))


def write_mended(path: Path, replaced: Path, target: Path) -> None:
    """Texture `path` to `target`, mended() against `replaced` if need be."""
    data = path.read_bytes()
    target.write_bytes(mended(data, replaced.read_bytes()) or data)
