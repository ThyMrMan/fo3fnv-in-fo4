"""Pack a Data folder's loose textures into the plugin's texture BA2 with the CK's Archive2.

Fallout 4 streams a texture's mips from a BA2's chunks; a loose DDS can stay
on a low mip, and past iTextureDegradeDistance the game drops a texture's top
chunk (a 512 FNV texture to 256). Each texture is one chunk, as some vanilla
ones are, so it always shows in full, as in FNV. Loose files under
<data>/Textures move into <data>/_ba2/Textures (a folder the game does not
read), which keeps every texture any build wrote, and all of it becomes `<plugin> - Textures.ba2`, loaded with the plugin.
Folders the archiver cannot take (uncompressed one-mip LUTs, which vanilla
keeps in a general archive) stay loose.

See: docs/fork/fo4_spikes.md#spike-4-exterior
"""

import shutil
import subprocess
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR

ARCHIVE2 = FALLOUT4_DIR / 'Tools' / 'Archive2' / 'Archive2.exe'
#: Folder under the Data folder holding every texture packed so far.
STAGING = '_ba2'
#: Chunks per texture: one, so the game has no top mips to drop with distance.
CHUNKS = 1


def pack_textures(data_dir: Path, plugin: str, keep_loose: tuple = ()) -> int:
    """Pack <data_dir>/Textures (but `keep_loose` folders) as `<plugin stem> - Textures.ba2`; the file count."""
    loose, root = data_dir / 'Textures', data_dir / STAGING
    kept = [loose / folder.replace(chr(92), '/') for folder in keep_loose]
    for path in sorted(p for p in loose.rglob('*') if p.is_file()) if loose.exists() else []:
        if any(path.is_relative_to(folder) for folder in kept):
            continue
        target = root / 'Textures' / path.relative_to(loose)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(path, target)
    archive = data_dir / f'{Path(plugin).stem} - Textures.ba2'
    subprocess.run([str(ARCHIVE2), str(root / 'Textures'), f'-c={archive}', '-f=DDS', f'-r={root}',
                    f'-maxChunkCount={CHUNKS}', '-q'], check=True, capture_output=True, **POPEN_FLAGS)
    return sum(1 for p in (root / 'Textures').rglob('*') if p.is_file())
