"""Premultiplied replacer textures are mended against the texture they replace; straight ones are kept.

See: docs/fork/fo4_plugin_layout.md#premultiplied-replacers
"""

import io

import numpy as np
from PIL import Image

from asset_convert.texture.image_transcode import _halved, encode_dds
from fo4_import.base.premultiplied import mended

SIZE = 64


def _wood() -> np.ndarray:
    """A lit, striped RGB image standing in for an authored texture."""
    y = np.arange(SIZE)[:, None, None]
    return np.broadcast_to(90 + 40 * (y % 8 < 4), (SIZE, SIZE, 3)).astype(np.float32) + [20, 10, 0]


def _alpha() -> np.ndarray:
    """An alpha mask: a clear band, a ramp, and solid."""
    alpha = np.full((SIZE, SIZE), 255.0)
    alpha[:, :16] = 0
    alpha[:, 16:32] = np.linspace(0, 255, 16)
    return alpha


def _dds(rgb: np.ndarray, alpha: np.ndarray) -> bytes:
    """DXT5 bytes of float `rgb` with `alpha`."""
    return encode_dds(Image.fromarray(np.dstack([rgb, alpha]).round().clip(0, 255).astype(np.uint8), 'RGBA'))


def _rgba(data: bytes) -> np.ndarray:
    """Float RGBA of DDS `data`'s top mip."""
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'), np.float32)


def test_premultiplied_replacer_gets_the_replaced_color_back():
    """A replacer whose color is the replaced color times alpha is mended: its clear band shows the wood again."""
    wood, alpha = _wood(), _alpha()
    out = mended(_dds(wood * alpha[:, :, None] / 255, alpha), _dds(wood, alpha))
    assert out is not None
    rgba = _rgba(out)
    assert abs(rgba[:, :16, :3].mean() - wood[:, :16].mean()) < 6
    assert np.abs(rgba[:, :, 3] - alpha).max() < 12


def test_straight_and_opaque_replacers_are_kept():
    """Straight-alpha and opaque replacers: mended() is None."""
    wood, alpha = _wood(), _alpha()
    assert mended(_dds(wood * 1.1, alpha), _dds(wood, alpha)) is None
    assert mended(_dds(np.zeros_like(wood), np.full((SIZE, SIZE), 255.0)), _dds(wood, alpha)) is None


def test_mips_keep_color_where_alpha_is_clear():
    """encode_dds mips keep color under clear alpha."""
    image = Image.fromarray(np.dstack([_wood(), _alpha()]).astype(np.uint8), 'RGBA')
    half = np.asarray(_halved(image), np.float32)
    assert half[:, :8, :3].mean() > 80
