"""Object LOD of a build's worldspaces: the input list the build wrote (spike.object_lod), the atlas (lod_atlas),
then LODGenx64 in FO4 mode, unattended and bounded (lod_gen.run_lodgen), writing
Meshes/Terrain/<world>/Objects/*.bto into the Data folder.

A worldspace without terrain LOD has no LODSettings file and is skipped.
Each run is kept under the work folder by a key over everything LODGen
reads, so a build that changes none of it copies the kept tiles back.

    py -3.14 -m fo4_import.pipeline.object_lod --export export/FalloutNV.esm --data <Data> [WORLD ...]

See: docs/fork/fo4_pipeline.md#object-lod
"""

import argparse
import collections
import hashlib
import shutil
import struct
from pathlib import Path

from asset_convert.lod.lod_gen import LODGEN_EXE, run_lodgen
from fo4_import.base.ba2_pack import staging_root
from fo4_import.nif import file as F
from fo4_import.nif.convert_static import SLOT_SPECULAR
from fo4_import.pipeline import lod_atlas
from fo4_import.pipeline.code_tag import code_tag

#: Seconds LODGen may take for one worldspace before it is killed (a whole WastelandNV run takes far less).
TIMEOUT = 900
#: The reference rows' columns holding the LOD meshes of levels 4, 8, 16 and 32 (xEdit's FO4 row layout).
LOD_COLUMNS = slice(13, 17)
#: The input file's settings past the worldspace and paths, as xEdit writes them for FO4 (defaults).
SETTINGS = ('RemoveUnseenFaces=True', 'IgnoreWater=False', 'DontGenerateVertexColors=False',
            'DontGenerateTangents=False', 'DefaultAlphaThreshold=128', 'UseAlphaThreshold=False',
            'UseBacklightPower=False', f'AtlasTolerance={lod_atlas.UV_RANGE - 1.0:.1f}')
#: The specular flag of a lighting shader's first flags.
SPECULAR = 0x1
#: The end of the atlas diffuse's path in a LODGen tile, lowercase.
ATLAS_DIFFUSE = '.objects.dds'


def work_dir(data_dir: Path) -> Path:
    """`data_dir`'s object LOD work folder, beside its texture staging."""
    staged = staging_root(data_dir)
    return staged.parent.parent / 'object_lod' / staged.name


def list_path(data_dir: Path, world: str) -> Path:
    """The input list (reference rows) the build writes for FO4 worldspace `world`."""
    return work_dir(data_dir) / f'{world}.txt'


def lod_settings(data_dir: Path, world: str) -> 'tuple | None':
    """`world`'s LODSettings (SW cell x, y, side, lowest, highest level) or None."""
    settings = Path(data_dir) / 'LODSettings' / f'{world}.lod'
    return struct.unpack_from('<2h3I', settings.read_bytes()) if settings.is_file() else None


def tile_level(name: str, world: str) -> int:
    """The LOD level of `world`'s tile file `name` (<world>.<level>.<x>.<y>.bto)."""
    return int(name[len(world) + 1:].split('.')[0])


def with_specular(data: bytes) -> bytes:
    """A LODGen .bto with every lit shape's specular as vanilla's: an atlas shape without a specular map names the
    atlas's; a shape of its own texture without one has specular off.
    See: docs/fork/fo4_pipeline.md#object-lod
    """
    nif = F.read(data)
    for kind, block in nif.blocks:
        if kind != 'BSLightingShaderProperty' or isinstance(block, bytes) or block['texture_set'] < 0:
            continue
        slots = nif.blocks[block['texture_set']][1]['textures']
        if slots[SLOT_SPECULAR]:
            continue
        if slots[0].lower().endswith(ATLAS_DIFFUSE):
            slots[SLOT_SPECULAR] = f'{slots[0][:-len(ATLAS_DIFFUSE)]}.objects_s.dds'
        else:
            block['flags1'] &= ~SPECULAR
    return F.write(nif)


def lod_meshes(rows: list) -> list:
    """The LOD meshes (paths under Meshes) the reference rows name, each once."""
    names = {name for row in rows for name in row.split('\t')[LOD_COLUMNS] if name}
    return sorted(name.split('\\', 1)[1] for name in names)


def _bytes_named(data_dir: Path, meshes: list, world: str) -> list:
    """Bytes of every file a run reads: the LOD meshes, the materials they name, and `world`'s .btr tiles."""
    files = [Path(data_dir) / 'Meshes' / mesh for mesh in meshes]
    names = (s.lower() for f in files if f.is_file() for s in F.read(f.read_bytes()).strings)
    materials = {name for name in names if name.endswith('.bgsm')}
    files += [Path(data_dir) / m for m in sorted(materials)]
    files += sorted((Path(data_dir) / 'Meshes' / 'Terrain' / world).glob('*.btr'))
    return [f.read_bytes() if f.is_file() else b'' for f in files]


def run_key(text: str, data_dir: Path, meshes: list, world: str) -> str:
    """The key of a LODGen run: this code, LODGen's size, the input and atlas map text, and _bytes_named()."""
    digest = hashlib.sha1(f'{code_tag(__name__)}\0{LODGEN_EXE.stat().st_size}\0{text}'.encode())
    for data in _bytes_named(data_dir, meshes, world):
        digest.update(hashlib.sha1(data).digest())
    return digest.hexdigest()[:16]


def header(world: str, sw: tuple, data_dir: Path, atlas_map: 'Path | None') -> list:
    """LODGen's input header, its output folder aside."""
    head = ['GameMode=FO4', f'Worldspace={world}', f'CellSW={sw[0]} {sw[1]}', *SETTINGS,
            f'PathData={Path(data_dir).resolve()}\\']
    return head + ([f'TextureAtlasMap={atlas_map}'] if atlas_map else [])


def _baked(folder: Path, head: list, rows: list, key: str) -> 'Path | None':
    """The folder of the .bto LODGen writes for input header `head` and `rows`: kept under `folder` as `key`, run
    when missing; None when the run fails. Other keys' runs are dropped."""
    kept = folder / key
    if kept.is_dir():
        return kept
    for old in (p for p in folder.iterdir() if p.is_dir()):
        shutil.rmtree(old)
    out, lodgen_input = folder / 'out', folder / 'LODGen.txt'
    out.mkdir()
    lodgen_input.write_text('\n'.join([*head, f'PathOutput={out}', *rows]) + '\n', encoding='utf-8')
    if not run_lodgen(lodgen_input, out, TIMEOUT):
        return None
    out.rename(kept)
    return kept


def install(kept: Path, data_dir: Path, world: str, levels: tuple) -> int:
    """Replace `world`'s .bto in `data_dir` with the kept run's tiles of LOD `levels` (lowest, highest), each
    with_specular(); how many.
    See: docs/fork/fo4_pipeline.md#object-lod
    """
    target = Path(data_dir) / 'Meshes' / 'Terrain' / world / 'Objects'
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob('*.bto'):
        old.unlink()
    tiles = [t for t in sorted(kept.glob('*.bto')) if levels[0] <= tile_level(t.name, world) <= levels[1]]
    for tile in tiles:
        (target / tile.name).write_bytes(with_specular(tile.read_bytes()))
    return len(tiles)


def bake(export_dir: Path, data_dir: Path, world: str) -> tuple:
    """Write FO4 worldspace `world`'s object LOD from the build's list (module notes); (outcome, tiles)."""
    grid, rows = lod_settings(data_dir, world), list_path(data_dir, world).read_text(encoding='utf-8').splitlines()
    if grid is None or not rows:
        return ('skipped, no terrain LOD' if grid is None else 'skipped, no references'), 0
    folder = work_dir(data_dir) / world
    folder.mkdir(parents=True, exist_ok=True)
    meshes = lod_meshes(rows)
    atlas = lod_atlas.build(export_dir, data_dir, world, [m.replace('\\', '/') for m in meshes])
    atlas_map = folder / 'atlas.txt' if atlas else None
    if atlas_map:
        atlas_map.write_text('\n'.join(atlas) + '\n', encoding='utf-8')
    head = header(world, grid[:2], data_dir, atlas_map)
    kept = _baked(folder, head, rows, run_key('\n'.join([*head, *rows, *atlas]), data_dir, meshes, world))
    return ('LODGen failed', 0) if kept is None else ('baked', install(kept, data_dir, world, grid[3:]))


def bake_all(export_dir: Path, data_dir: Path, worlds: list) -> collections.Counter:
    """bake() each of `worlds` with a list; counts per outcome."""
    counts = collections.Counter()
    for world in worlds:
        outcome, tiles = bake(export_dir, data_dir, world)
        print(f'object LOD {world}: {outcome}, {tiles} tiles')
        counts[f'object LOD worldspaces {outcome}'] += 1
        counts['object LOD tiles'] += tiles
    return counts


def main() -> None:
    """Bake the named worldspaces (all with a list by default) from the command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, type=Path, help='FNV export folder (the textures for the atlas)')
    ap.add_argument('--data', required=True, type=Path, help='The built Data folder')
    ap.add_argument('worlds', nargs='*', help='FO4 worldspace EditorIDs (default: every list the build wrote)')
    args = ap.parse_args()
    worlds = args.worlds or sorted(p.stem for p in work_dir(args.data).glob('*.txt'))
    for key, count in sorted(bake_all(args.export, args.data, worlds).items()):
        print(f'{key}: {count}')


if __name__ == '__main__':
    main()
