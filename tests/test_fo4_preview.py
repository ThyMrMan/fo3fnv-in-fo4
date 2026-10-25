"""fo4_import.app.preview: NIF to parts, materials, tangents, camera, and an off-screen render."""

import io

import numpy as np
import pytest
from PIL import Image

from fo4_import.app.preview import render as RD
from fo4_import.app.preview import scene as SC
from fo4_import.app.preview.materials import Materials, decode
from fo4_import.nif import blocks as K
from fo4_import.nif import file as F

ATTRS = K.VA_VERTEX | K.VA_UV | K.VA_NORMAL


def _av(name: int, **extra) -> dict:
    """NiAVObject fields: no rotation, unit scale, plus `extra`."""
    return {'name': name, 'extra': [], 'controller': -1, 'flags': 0, 'translation': (0.0, 0.0, 0.0),
            'rotation': (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), 'scale': 1.0, 'collision': -1, **extra}


def _nif_bytes() -> bytes:
    """A NIF: a node moved by (10, 0, 0) and scaled 2, holding one triangle with UVs and +Z normals."""
    nif = F.NifFile(strings=['Root', 'Tri'])
    vert = lambda x, y: {'position': (x, y, 0.0), 'bitangent_x': 0, 'uv': (x, y), 'normal': (128, 128, 255),
                         'bitangent_y': 0}
    shape = _av(1, bound=(0.0, 0.0, 0.0, 1.0), skin=-1, shader=-1, alpha_property=-1, vertex_desc=ATTRS << 44 | 4,
                vertices=[vert(0.0, 0.0), vert(1.0, 0.0), vert(0.0, 1.0)], triangles=[(0, 1, 2)])
    nif.blocks = [('NiNode', _av(0, translation=(10.0, 0.0, 0.0), scale=2.0, children=[1])), ('BSTriShape', shape)]
    return F.write(nif)


def test_load_composes_node_transforms():
    """A shape's vertices land in model space through its parent's translation and scale."""
    parts = SC.load(_nif_bytes())
    assert len(parts) == 1 and parts[0].name == 'Tri'
    assert np.allclose(parts[0].positions, [(10, 0, 0), (12, 0, 0), (10, 2, 0)])
    assert np.allclose(parts[0].normals[:, 2], 1.0, atol=0.01)
    center, radius = SC.bounds(parts)
    assert np.allclose(center, (11, 1, 0)) and radius == pytest.approx(np.sqrt(2))


def test_tangents_follow_u():
    """On a flat triangle whose U runs along +X, the tangent is +X."""
    part = SC.load(_nif_bytes())[0]
    assert np.allclose(RD.tangents(part)[:, :3], [(1, 0, 0)] * 3, atol=1e-2)


def test_camera_centers_the_model():
    """The bounds' center projects to the middle of the view."""
    mvp, eye, _ = RD.matrices(np.array([5.0, 5.0, 5.0]), 2.0, RD.Camera(), 1.0)
    clip = mvp @ np.array([5.0, 5.0, 5.0, 1.0])
    assert np.allclose(clip[:2] / clip[3], 0.0, atol=1e-9)
    assert np.linalg.norm(eye - 5.0) == pytest.approx(2.0 * RD.Camera().zoom)


class _Files:
    """A files stand-in holding {Data path: bytes}."""

    def __init__(self, found: dict):
        """Files with `found`."""
        self.found = found

    def read(self, path: str):
        """The bytes at `path`, or None."""
        return self.found.get(path)


def _png(color: tuple) -> bytes:
    """A 4x4 PNG of one color."""
    out = io.BytesIO()
    Image.new('RGBA', (4, 4), color).save(out, 'PNG')
    return out.getvalue()


def test_texture_set_used_without_a_material():
    """With no material file, the texture set's slots 0, 1 and 7 give the maps (any case, `textures` added)."""
    part = SC.load(_nif_bytes())[0]
    part.textures = ['Textures\\Gun_D.dds', 'gun_n.dds', '', '', '', '', '', 'textures\\gun_s.dds']
    files = _Files({'textures\\gun_d.dds': _png((255, 0, 0, 255)), 'textures\\gun_s.dds': _png((9, 9, 9, 255))})
    surface = Materials(files).surface(part)
    assert surface.diffuse.rgba[:4] == b'\xff\x00\x00\xff' and surface.normal is None
    assert surface.specular is not None and surface.alpha_test == -1


def test_decode_rejects_junk():
    """Bytes that are not an image give no texture."""
    assert decode(b'not an image') is None and decode(None) is None


def test_render_draws_the_model():
    """An off-screen render of the untextured model leaves the corner background and draws something."""
    try:
        image = RD.render_image(SC.load(_nif_bytes()), [None], (64, 64))
    except Exception as error:
        pytest.skip(f'no OpenGL 3.3 here: {error}')
    background = image.getpixel((0, 0))
    assert background[:3] == tuple(round(c * 255) for c in RD.BACKGROUND[:3])
    assert int(np.any(np.asarray(image) != background, axis=2).sum()) > 50
