"""The converter's own DDS encoder: Pillow decodes what it writes close to the source, at every format and size.

See: docs/fork/fo4_facegen_plan.md#own-dds-encoder
"""

import io
import struct

import numpy as np
import pytest
from PIL import Image

from fo4_import.base import dds_encode as E


def _decoded(data: bytes) -> np.ndarray:
    """DDS bytes decoded by Pillow, RGBA floats."""
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'), float)


def _smooth(width: int, height: int) -> np.ndarray:
    """A smooth RGBA image (colour and alpha gradients), uint8."""
    y, x = np.mgrid[0:height, 0:width] / max(width, height)
    return (np.stack([x, y, (x + y) / 2, 1 - x * y], 2) * 255).astype(np.uint8)


@pytest.mark.parametrize('fmt, channels', [(E.BC1, 3), (E.BC3, 4), (E.BC5, 2)])
def test_each_format_decodes_close_to_its_source(fmt, channels):
    """Pillow reads each format back within a few levels of a smooth source."""
    rgba = _smooth(64, 64)
    out = _decoded(E.encode(rgba, fmt, mips=False))
    assert np.abs(out[..., :channels] - rgba[..., :channels]).mean() < 2.5


def test_a_flat_colour_decodes_exactly_as_565_holds_it():
    """A block of one colour decodes to that colour rounded to 5:6:5."""
    rgba = np.zeros((8, 8, 4), np.uint8)
    rgba[...] = (200, 100, 40, 255)
    assert tuple(_decoded(E.encode(rgba, E.BC1, mips=False))[0, 0, :3]) == (198, 101, 41)


def test_the_header_names_the_size_mips_and_four_cc():
    """A 64x32 BC1 at its own size has 7 mips down to 1x1; a resize gives the size asked for."""
    out = E.encode(_smooth(64, 32), E.BC1)
    height, width, _, _, mips = struct.unpack_from('<IIIII', out, 12)
    assert (width, height, mips, out[84:88]) == (64, 32, 7, b'DXT1')
    assert len(out) == 128 + sum(max(1, (64 >> i) // 4) * max(1, (32 >> i) // 4) * 8 for i in range(7))
    big = E.encode(_smooth(16, 16), E.BC5, (32, 32), mips=False)
    assert struct.unpack_from('<II', big, 12) == (32, 32) and big[84:88] == b'BC5U'


def test_a_format_it_cannot_write_is_refused():
    """BC7 and the rest raise rather than write a wrong file."""
    with pytest.raises(ValueError):
        E.encode(_smooth(8, 8), 98)
