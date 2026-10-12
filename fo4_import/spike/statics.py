"""Spike 2 step 1: FNV statics converted and placed in QASmoke, to see them render in Fallout 4.

    py -3.14 -m fo4_import.spike.statics --export <FalloutNV.esm export> --out <plugin.esp> --data <Data> EDID...

Each named FNV STAT's mesh is converted (fo4_import.nif.convert_static) into
<Data>/Meshes/fnv, its materials into <Data>/Materials, its textures copied
into <Data>/Textures/fnv; the plugin gets one STAT per mesh and one placed
reference each, in a row in QASmoke.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

import argparse
import copy
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.base.writer import FO4PluginWriter
from fo4_import.nif import bgem, bgsm
from fo4_import.nif import file as nif_file
from asset_convert.texture import spec_mask
from fo4_import.nif.convert_static import PREFIX, fo4_texture, glow_image, spec_image, spec_map_path, texture_source
from fo4_import.pipeline.mesh_cache import cached_convert
from fo4_import.pipeline.work_cache import colour_map, normal_map
from fo4_import.nif.elric import finish
from fo4_import.nif.tree import tree_mesh
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import CELL_FO4, vanilla_cell
from tes5_import.base.text_reader import parse_export_file

MASTERS = ['Fallout4.esm']
#: First placement in QASmoke (beside the dialogue spike's speakers) and the spacing along X.
START, SPACING = (-1700.0, -1484.0, 0.0), 300.0


def mesh_bounds(nif) -> 'tuple | None':
    """OBND: the integer box around every shape's vertices; None for a mesh with none."""
    pts = np.array([v['position'] for kind, b in nif.blocks if kind == 'BSTriShape' for v in b['vertices']])
    if not len(pts):
        return None
    lo, hi = np.floor(pts.min(axis=0)).astype(int), np.ceil(pts.max(axis=0)).astype(int)
    return (*lo.tolist(), *hi.tolist())


def write_assets(export_dir: Path, model: str, data_dir: Path, pose: dict = None, animated: bool = True,
                 load: bool = False) -> 'tuple | None':
    """write_converted() of FNV `model` converted (convert()); a `load` door's static, as `<name>load.nif` (vanilla
    load door meshes' naming), or None when the mesh has no animation (the plain one serves)."""
    rel = model.replace('/', '\\').lower()
    converted = cached_convert(export_dir / 'meshes' / rel, export_dir, pose, animated and not load)
    if load and not converted.animatable:
        return None
    return write_converted(export_dir, converted, rel[:-4] + 'load.nif' if load else rel, data_dir)


def tree_assets(export_dir: Path, rec: dict, data_dir: Path) -> tuple:
    """write_converted() of FNV TREE `rec`'s generated mesh (nif.tree)."""
    return write_converted(export_dir, tree_mesh(export_dir, rec), f'trees\\{rec["EditorID"].lower()}.nif', data_dir)


def write_converted(export_dir: Path, converted, rel: str, data_dir: Path) -> tuple:
    """Write converted mesh `converted` as Meshes\\<PREFIX>\\`rel` with its materials and textures into
    <data_dir>; (FO4 model path under Meshes, OBND)."""
    out = data_dir / 'Meshes' / PREFIX / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(nif_file.write(converted.nif))
    written = [(p, bgsm.write(m)) for p, m in converted.materials.items()]
    written += [(p, bgem.write(m)) for p, m in converted.effects.items()]
    for path, raw in written:
        target = data_dir / path.replace('materials\\', 'Materials\\', 1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for texture in converted.textures:
        source = export_dir / texture_source(texture).replace('\\', '/')
        target = data_dir / 'Textures' / fo4_texture(texture)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.copyfile(source, target)
    for spec_path, (fnv_normal, smooth) in converted.spec_maps.items():
        normal = (export_dir / texture_source(fnv_normal).replace('\\', '/')).read_bytes()
        _write(data_dir / 'Textures' / spec_path, normal_map(spec_image(normal, smooth)))
    for glow_path, (*sources, cut) in converted.glow_maps.items():
        diffuse, glow = (export_dir / texture_source(t).replace('\\', '/') for t in sources)
        if diffuse.exists() and glow.exists():
            _write(data_dir / 'Textures' / glow_path,
                   colour_map(glow_image(diffuse.read_bytes(), glow.read_bytes(), cut)))
    return f'{PREFIX}\\{rel}', mesh_bounds(converted.nif)


def swap_material(export_dir: Path, model: str, node: str, texture: str, data_dir: Path) -> 'tuple | None':
    """(material of FNV `model`'s shape `node`, one showing FNV `texture` instead); None without such a shape.

    The swap material is the shape's BGSM with only the diffuse texture
    replaced; it and the texture are written into `data_dir`.
    """
    converted = cached_convert(export_dir / 'meshes' / model.replace('/', '\\').lower(), export_dir)
    nif = converted.nif
    shaders = [b['shader'] for kind, b in nif.blocks
               if kind == 'BSTriShape' and nif.strings[b['name']].lower() == node.lower() and b['shader'] >= 0]
    path = nif.strings[nif.blocks[shaders[0]][1]['name']] if shaders else ''
    if path not in converted.materials:
        return None
    source = f'textures\\{texture.replace("/", chr(92)).lower()}.dds'
    material = copy.deepcopy(converted.materials[path])
    old = material['textures']['diffuse'].rsplit('.', 1)[0].replace('/', '\\')
    material['textures']['diffuse'] = fo4_texture(source).replace('\\', '/')
    new = path.replace(old, fo4_texture(source).rsplit('.', 1)[0], 1)
    out = data_dir / new.replace('materials\\', 'Materials\\', 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bgsm.write(material))
    target = data_dir / 'Textures' / fo4_texture(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(export_dir / source.replace('\\', '/'), target)
    return path, new


def swapped_material(export_dir: Path, data_dir: Path, material: str, textures: tuple) -> str:
    """Material `material` (already in `data_dir`) showing FNV texture set `textures` (diffuse, normal or ''),
    written once with its textures beside it; its path.

    The normal map's alpha becomes the specular map, at the smoothness of
    the material's own map, as convert_static does; without a mask in it
    specular is off.

    See: docs/fork/fo4_spikes.md#spike-4-outfits
    """
    diffuse, normal = (texture_source(t) if t else '' for t in textures)
    mat = bgsm.read(_material_file(data_dir, material).read_bytes())
    old = mat['textures']['diffuse'].rsplit('.', 1)[0].replace('/', '\\')
    new = material.replace(old, fo4_texture(diffuse).rsplit('.', 1)[0], 1)
    if new == material or _material_file(data_dir, new).exists():
        return new
    mat['textures']['diffuse'] = fo4_texture(diffuse).replace('\\', '/')
    _copy_texture(export_dir, data_dir, diffuse)
    if normal:
        mat['textures']['normal'] = fo4_texture(normal).replace('\\', '/')
        _copy_texture(export_dir, data_dir, normal)
        _swapped_spec(export_dir, data_dir, mat, normal)
    target = _material_file(data_dir, new)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bgsm.write(mat))
    return new


def _swapped_spec(export_dir: Path, data_dir: Path, mat: dict, normal: str) -> None:
    """Point `mat`'s specular map at one made from FNV `normal`'s alpha, at the smoothness of its own."""
    own = data_dir / 'Textures' / mat['textures']['smooth_spec'].replace('/', '\\') if mat['specular'] else None
    raw = (export_dir / normal.replace('\\', '/')).read_bytes()
    if own is None or not own.exists() or not spec_mask.has_mask(raw):
        mat['specular'], mat['textures']['smooth_spec'] = False, ''
        return
    smooth = float(np.asarray(Image.open(own).convert('RGB'))[:, :, 1].mean()) / 255
    path = spec_map_path(normal)
    _write(data_dir / 'Textures' / path, normal_map(spec_image(raw, smooth)))
    mat['textures']['smooth_spec'] = path.replace('\\', '/')


def _write(target: Path, data: bytes) -> None:
    """Write `data` to `target`, making its folder."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _material_file(data_dir: Path, material: str) -> Path:
    """The data folder file of material path `material` (materials\\...)."""
    return data_dir / material.replace('materials\\', 'Materials\\', 1)


def _copy_texture(export_dir: Path, data_dir: Path, source: str) -> None:
    """Copy FNV texture `source` (textures\\...) to its FO4 path in `data_dir`."""
    target = data_dir / 'Textures' / fo4_texture(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(export_dir / source.replace('\\', '/'), target)


def build(export_dir: Path, out: Path, data_dir: Path, edids: list) -> list:
    """Write the plugin and the assets for FNV statics `edids`; [(edid, FO4 model)]."""
    models = {r['EditorID']: r['Model.MODL'] for r in parse_export_file(str(export_dir / 'STAT.txt'))
              if r.get('EditorID') in edids}
    w = FO4PluginWriter(masters=MASTERS, is_esm=False, description='FNV statics spike')
    fid, refs, made = len(MASTERS) << 24 | 0x800, b'', []
    for i, edid in enumerate(edids):
        model, bounds = write_assets(export_dir, models[edid], data_dir)
        w.add_record('STAT', R.pack_stat(fid, f'FNVSpike_{edid}', model, bounds))
        pos = (START[0] + i * SPACING, START[1], START[2])
        refs += R.pack_refr(fid + 1, fid, pos, (0.0, 0.0, 0.0))
        made.append((edid, model))
        fid += 2
    w.add_raw_group('CELL', R.pack_interior_cells([(vanilla_cell()[0], CELL_FO4, refs, b'')]))
    finish([data_dir / 'Meshes' / model for _, model in made])
    w.next_object_id = fid & 0xFFFFFF
    out.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(out))
    return made


def main():
    """Build the plugin and assets, and print what was placed."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, help='Plugin to write')
    ap.add_argument('--data', required=True, help='Data folder for meshes, materials and textures')
    ap.add_argument('edids', nargs='+', help='FNV STAT editor IDs')
    args = ap.parse_args()
    for edid, model in build(Path(args.export), Path(args.out), Path(args.data), args.edids):
        print(f'{edid}: Meshes\\{model}')


if __name__ == '__main__':
    main()
