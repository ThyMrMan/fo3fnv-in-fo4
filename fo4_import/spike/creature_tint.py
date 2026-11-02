"""FO4's body material in an FNV creature's skin color, for a pair worn over FO4's own body (nif.creature).

FO4's body keeps its mesh, weights and texture layout; a copy of each of
its materials (its dismemberment gore's aside) takes a diffuse whose every
color channel has FNV's bare skin's mean and spread over the image. The
copies sit beside FNV's textures, and a material swap (MSWP) puts them on
the vanilla addon.
See: docs/fork/fo4_spikes.md#spike-4-creatures
"""

import io
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.face.texture import write_dds
from fo4_import.nif import bgsm
from fo4_import.nif import file as nif_file
from fo4_import.pipeline.export_index import export_file

#: Materials of FO4's body left as they are: its dismemberment caps' gore.
GORE = 'materials\\gore\\'
#: Where the tinted copies go, under Materials\ and Textures\.
FOLDER = 'fnv\\tinted\\'


def matched(rgba: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """`rgba` with each color channel's mean and standard deviation set to `rgb`'s; alpha kept."""
    out = rgba.astype(float)
    for c in range(3):
        src, ref = out[..., c], rgb[..., c].astype(float)
        out[..., c] = (src - src.mean()) / max(src.std(), 1e-6) * ref.std() + ref.mean()
    return np.clip(out, 0, 255).astype(np.uint8)


def body_materials(body: bytes) -> list:
    """The material paths (lower case, under Materials\\) of FO4 body NIF `body`'s shaders, gore left out."""
    nif = nif_file.read(body)
    names = {nif.strings[b['name']].lower() for k, b in nif.blocks
             if k == 'BSLightingShaderProperty' and isinstance(b, dict) and 0 <= b['name'] < len(nif.strings)}
    return sorted(n for n in names if n.startswith('materials\\') and not n.startswith(GORE))


def tinted(archives, export_dir: Path, data_dir: Path, body: str, skin: str) -> list:
    """[(FO4 material, tinted copy)] (paths under Materials\\) of FO4 body NIF `body` (in `archives`) in FNV bare
    skin texture `skin`'s color, the copies and their diffuses written under `data_dir`."""
    return tinted_materials(archives, export_dir, data_dir, body_materials(archives.read(body)), skin)


def tinted_materials(archives, export_dir: Path, data_dir: Path, materials: list, skin: str) -> list:
    """tinted() of FO4 `materials` (lower-case paths starting materials\\) in `archives`."""
    fnv = np.asarray(Image.open(export_file(export_dir, *skin.replace('\\', '/').split('/'))).convert('RGB'))
    stem = Path(skin).stem.lower()
    out = []
    for material in materials:
        mat = bgsm.read(archives.read(material))
        diffuse = mat['textures']['diffuse'].replace('/', '\\').lower()
        rgba = np.asarray(Image.open(io.BytesIO(archives.read('textures\\' + diffuse))).convert('RGBA'))
        name = f'{FOLDER}{stem}_{Path(material).stem.lower()}'
        texture = data_dir / 'Textures' / f'{name}.dds'
        texture.parent.mkdir(parents=True, exist_ok=True)
        write_dds(matched(rgba, fnv), texture)
        mat['textures']['diffuse'] = f'{name}.dds'.replace('\\', '/')
        target = data_dir / 'Materials' / f'{name}.bgsm'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bgsm.write(mat))
        out.append((material[len('materials\\'):], f'{name}.bgsm'))
    return out
