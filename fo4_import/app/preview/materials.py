"""What a part looks like: its diffuse, normal and specular maps and alpha, from its material file or texture set.

A lit part's BGSM (fo4_import.nif.bgsm) names its maps (diffuse, normal, smooth_spec) and its alpha test, blend
and two-sidedness; without one, the NIF's texture set is used (slot 0 diffuse, 1 normal, 7 specular). An effect
part's BGEM (fo4_import.nif.bgem) names a base and a normal map. Files come through fo4_import.app.files; maps
are decoded by Pillow (BC1-BC7) and scaled down to MAX_SIZE for the preview.

See: docs/fork/fo4_gui.md#preview
"""

import io
import struct
from dataclasses import dataclass

from PIL import Image

from fo4_import.app.files import key
from fo4_import.nif import bgem, bgsm

#: Longest side of a preview texture.
MAX_SIZE = 1024
#: Texture set slots of the diffuse, normal and specular (smoothness) maps.
SET_DIFFUSE, SET_NORMAL, SET_SPECULAR = 0, 1, 7
MATERIAL_SUFFIXES = ('.bgsm', '.bgem')


@dataclass
class Texture:
    """A decoded map: width, height and RGBA bytes."""
    width: int
    height: int
    rgba: bytes


@dataclass
class Surface:
    """A part's maps (None where missing), alpha (test threshold, -1 off; blending; two-sided), and for a
    greyscale-to-palette material its palette and the palette row (the material's greyscale scale)."""
    diffuse: 'Texture | None'
    normal: 'Texture | None'
    specular: 'Texture | None'
    alpha_test: int
    blend: bool
    two_sided: bool
    palette: 'Texture | None' = None
    palette_row: float = 0.0


class Materials:
    """Surfaces of parts, each file read and each texture decoded once, through `files`."""

    def __init__(self, files):
        """Read materials and textures through `files` (fo4_import.app.files.Files)."""
        self.files, self.images, self.materials = files, {}, {}

    def surface(self, part) -> Surface:
        """The Surface of a scene Part."""
        paths, alpha_test, blend, two_sided = self._sources(part)
        made = Surface(*(self.texture(p) for p in paths), alpha_test, blend, two_sided)
        material = self._material(part.material)
        if material and material.get('grayscale_to_palette') and material['textures'].get('greyscale'):
            made.palette = self.texture(material['textures']['greyscale'])
            made.palette_row = float(material.get('grayscale_scale', 0.0))
        return made

    def _sources(self, part) -> tuple:
        """((diffuse, normal, specular) texture paths, alpha test, blend, two-sided) of `part`."""
        material = self._material(part.material)
        if material is None:
            slots = part.textures + [''] * (SET_SPECULAR + 1)
            maps = (slots[0], slots[1], '') if part.effect else (slots[SET_DIFFUSE], slots[SET_NORMAL],
                                                                 slots[SET_SPECULAR])
            return maps, part.alpha_test, part.blend, False
        textures = material['textures']
        maps = (textures['base'], textures['normal'], '') if 'base' in textures else (
            textures['diffuse'], textures['normal'], textures['smooth_spec'])
        test = material['alpha_test_ref'] if material['alpha_test'] else -1
        return maps, test, bool(material['alpha_blend']), bool(material['two_sided'])

    def _material(self, name: str) -> 'dict | None':
        """The BGSM or BGEM a shader names, read once; None for none or one not found or not parsed."""
        if not name.lower().endswith(MATERIAL_SUFFIXES):
            return None
        path = key(name)
        path = path if path.startswith('materials\\') else f'materials\\{path}'
        if path not in self.materials:
            self.materials[path] = _parsed(name, self.files.read(path))
        return self.materials[path]

    def texture(self, path: str) -> 'Texture | None':
        """The map at `path` (with or without `textures\\`), decoded and scaled once; None if missing or unreadable."""
        if not path:
            return None
        wanted = key(path) if key(path).startswith('textures\\') else f'textures\\{key(path)}'
        if wanted not in self.images:
            self.images[wanted] = decode(self.files.read(wanted))
        return self.images[wanted]


def _parsed(name: str, raw: 'bytes | None') -> 'dict | None':
    """Material file bytes read as a BGEM or BGSM; None when missing or unreadable (reported)."""
    if raw is None:
        return None
    try:
        return (bgem if raw[:4] == bgem.MAGIC else bgsm).read(raw)
    except (ValueError, KeyError, IndexError, UnicodeDecodeError, struct.error) as error:
        print(f'preview: material {name} not read ({error})')
        return None


def decode(raw: 'bytes | None') -> 'Texture | None':
    """A DDS (or any image Pillow reads) as an RGBA Texture no larger than MAX_SIZE; None if it does not decode."""
    if not raw:
        return None
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (OSError, ValueError, NotImplementedError):
        return None
    image = image.convert('RGBA')
    image.thumbnail((MAX_SIZE, MAX_SIZE))
    return Texture(image.width, image.height, image.tobytes())
