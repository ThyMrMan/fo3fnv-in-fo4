"""Tests for tools/validate/shot_boxes.py: box parsing, measurement on a made-up image, and fo4_look's night road."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tools.validate import shot_boxes as SB

#: The user's FNV reference shot, kept outside the repo (Bethesda art).
NIGHT_FNV = Path(__file__).resolve().parents[2] / 'look_refs' / 'saloon_night_fnv.webp'


def _image() -> np.ndarray:
    """A 100 x 200 image: top half pure blue, bottom half grey 100."""
    image = np.full((100, 200, 3), 100, np.uint8)
    image[:50] = (0, 0, 255)
    return image


def test_measure_boxes():
    """Mean colour, luminance, saturation and hue of a box."""
    sky = SB.measure(_image(), (0.0, 0.0, 1.0, 0.5))
    ground = SB.measure(_image(), (0.1, 0.6, 0.9, 1.0))
    assert tuple(sky['rgb']) == (0, 0, 255) and round(sky['hue']) == 240 and sky['sat'] == 1.0
    assert round(sky['lum'], 2) == round(0.0722 * 255, 2)
    assert round(ground['lum'], 6) == 100.0 and ground['sat'] == 0.0


def test_parse_box_rejects_bad_boxes():
    """NAME=x0,y0,x1,y1 parses; a box with corners out of order is refused."""
    assert SB.parse_box('road=0.1,0.2,0.3,0.4') == ('road', (0.1, 0.2, 0.3, 0.4))
    with pytest.raises(ValueError):
        SB.parse_box('road=0.3,0.2,0.1,0.4')


def test_table_ratio_and_draw(tmp_path):
    """The second image's luminance is reported as a ratio of the first's; --draw writes an image."""
    first, second = tmp_path / 'fnv.png', tmp_path / 'fo4.png'
    Image.fromarray(_image()).save(first)
    Image.fromarray(_image() // 2).save(second)
    out = SB.table([str(first), str(second)], {'ground': (0.0, 0.6, 1.0, 1.0)})
    assert out.splitlines()[-1].endswith('0.50')
    SB.draw(str(first), {'ground': (0.0, 0.6, 1.0, 1.0)}, str(tmp_path / 'boxes.png'))
    assert (tmp_path / 'boxes.png').exists()


@pytest.mark.skipif(not NIGHT_FNV.exists(), reason='look_refs shots are on the user machine only')
def test_saloon_night_road_matches_fo4_look():
    """The saloon road box gives fo4_look's FNV night road (37, 38, 44) ±1."""
    rgb = SB.measure(SB.load(str(NIGHT_FNV)), SB.SPOTS['saloon']['road'])['rgb']
    assert np.abs(rgb - (37, 38, 44)).max() <= 1
