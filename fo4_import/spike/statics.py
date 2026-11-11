"""Spike 2 step 1: FNV statics converted and placed in QASmoke, to see them render in Fallout 4.

    py -3.14 -m fo4_import.spike.statics --export <FalloutNV.esm export> --out <plugin.esp> --data <Data> EDID...

Each named FNV STAT's mesh is converted (fo4_import.nif.convert_static) into
<Data>/Meshes/fnv, its materials into <Data>/Materials, its textures copied
into <Data>/Textures/fnv; the plugin gets one STAT per mesh and one placed
reference each, in a row in QASmoke. Every texture is written through
ba2_pack.stage_texture: once per run, and only when its staged copy is not
current. A copy's signature is its source's path, size and time; a derived
map's is its work-cache key, so a current one is neither decoded nor written.
A placed mesh's NIF and material bytes and OBND come from
mesh_cache.cached_files, and a file already holding its bytes is not written.

See: docs/fork/fo4_spikes.md#spike-2-static
"""

import argparse
import copy
import functools
import shutil
from pathlib import Path

from fo4_import.base.ba2_pack import stage_texture
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.nif import bgsm, elric
from fo4_import.nif import file as nif_file
from asset_convert.texture import spec_mask
from fo4_import.nif.convert_static import (PREFIX, fo4_texture, retextured, smoothness, spec_glossiness, spec_map_path,
                                           texture_source)
from fo4_import.pipeline.elric_cache import finish, write_mesh, write_new
from fo4_import.pipeline.mesh_cache import cached_convert, cached_files, mesh_files
from fo4_import.pipeline.work_cache import glow_map, spec_map
from fo4_import.nif.terminal import with_screen
from fo4_import.nif.tree import tree_mesh
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import CELL_FO4, vanilla_cell
from fo4_import.pipeline.export_index import export_file, replaced_file
from fo4_import.base.premultiplied import MENDED_VERSION, write_mended
from fo4_import.base.source_fault import SourceFault, count
from tes5_import.base.text_reader import parse_export_file

MASTERS = ['Fallout4.esm']
#: First placement in QASmoke (beside the dialogue spike's speakers) and the spacing along X.
START, SPACING = (-1700.0, -1484.0, 0.0), 300.0


def write_assets(export_dir: Path, model: str, data_dir: Path, pose: dict = None, animated: bool = True,
                 load: bool = False, suffix: str = '') -> 'tuple | None':
    """write_files() of FNV `model` converted (cached_files()) as `<name><suffix>.nif` (a posed weapon's
    `_weapon`); a `load` door's static, as `<name>load.nif` (vanilla load door meshes' naming), or None when the
    mesh has no animation (the plain one serves)."""
    rel = model.replace('/', '\\').lower()
    files = cached_files(export_file(export_dir, 'meshes', rel), export_dir, pose, animated and not load)
    if load and not files.animatable:
        return None
    return write_files(export_dir, files, rel[:-4] + ('load' if load else suffix) + '.nif', data_dir)


def prop_assets(export_dir: Path, model: str, data_dir: Path, pose: dict, bone: str) -> tuple:
    """write_assets() of FNV idle prop `model` in `pose`, unanimated, as `<name>_prop.nif` hung from FO4 bone `bone`
    (`Prn`); one with Havok input gets its collision from Elric at once."""
    rel = model.replace('/', '\\').lower()
    files = cached_files(export_file(export_dir, 'meshes', rel), export_dir, pose, False)
    nif = nif_file.read(files.nif)
    nif_file.hang_from(nif, bone)
    made = write_files(export_dir, files._replace(nif=nif_file.write(nif)), rel[:-4] + '_prop.nif', data_dir)
    if elric.has_havok(files.nif):
        finish([data_dir / 'Meshes' / made[0]])
    return made


def terminal_assets(export_dir: Path, model: str, data_dir: Path) -> 'tuple | None':
    """(write_converted() of FNV terminal `model` with its screen made FO4's, as `<name>terminal.nif`, the screen's
    (centre, facing)); None when the mesh has no screen (nif.terminal)."""
    rel = model.replace('/', '\\').lower()
    made = with_screen(cached_convert(export_file(export_dir, 'meshes', rel), export_dir))
    if made is None:
        return None
    return write_converted(export_dir, made[0], rel[:-4] + 'terminal.nif', data_dir), made[1]


def tree_assets(export_dir: Path, rec: dict, data_dir: Path) -> tuple:
    """write_converted() of FNV TREE `rec`'s generated mesh (nif.tree)."""
    return write_converted(export_dir, tree_mesh(export_dir, rec), f'trees\\{rec["EditorID"].lower()}.nif', data_dir)


def write_converted(export_dir: Path, converted, rel: str, data_dir: Path) -> tuple:
    """write_files() of converted mesh `converted` (mesh_files())."""
    return write_files(export_dir, mesh_files(converted), rel, data_dir)


def write_files(export_dir: Path, files, rel: str, data_dir: Path) -> tuple:
    """Write `files` as Meshes\\<PREFIX>\\`rel`, staged; (model path, OBND)."""
    write_mesh(data_dir / 'Meshes' / PREFIX / rel, files.nif)
    stage_files(export_dir, files, data_dir)
    return f'{PREFIX}\\{rel}', files.bounds


def stage_files(export_dir: Path, files, data_dir: Path) -> None:
    """Write mesh_files() `files`' materials and stage their textures and derived maps into <data_dir>."""
    for path, data in files.materials:
        write_new(_material_file(data_dir, path), data)
    for texture in files.textures:
        if _source(export_dir, texture).exists():
            copy_texture(export_dir, data_dir, texture_source(texture))
    for spec_path, (fnv_normal, glossiness) in files.spec_maps.items():
        stage_derived(data_dir, spec_path, spec_map, (_source(export_dir, fnv_normal),), smoothness(glossiness))
    for glow_path, (*sources, cut) in files.glow_maps.items():
        paths = tuple(_source(export_dir, t) for t in sources)
        if all(p.exists() for p in paths):
            stage_derived(data_dir, glow_path, glow_map, paths, cut)


def _source(export_dir: Path, fnv_texture: str) -> Path:
    """The export's file of FNV texture path `fnv_texture`."""
    return export_file(export_dir, texture_source(fnv_texture).replace('\\', '/'))


def stage_derived(data_dir: Path, rel: str, work, sources: tuple, *args) -> bool:
    """Stage texture `rel` made by work_cache `work` from `sources`' bytes and `args`."""
    return stage_texture(data_dir, rel, functools.partial(_derived_plan, work, sources, args))


def _derived_plan(work, sources: tuple, args: tuple) -> tuple:
    """stage_texture's (signature, writer) of `work` on `sources`' bytes and `args`."""
    key, get = work(*(path.read_bytes() for path in sources), *args)
    return key, functools.partial(_write_value, get)


def _write_value(get, target: Path) -> None:
    """Write get()'s bytes to `target`."""
    target.write_bytes(get())


def swap_material(export_dir: Path, model: str, node: str, texture: str, data_dir: Path) -> 'tuple | None':
    """(material of FNV `model`'s shape `node`, one showing FNV `texture` instead); None without such a shape.

    The swap material is the shape's BGSM with only the diffuse texture
    replaced; it and the texture are written into `data_dir`.
    """
    converted = cached_convert(export_file(export_dir, 'meshes', model.replace('/', '\\').lower()), export_dir)
    nif = converted.nif
    shaders = [b['shader'] for kind, b in nif.blocks
               if kind == 'BSTriShape' and nif.strings[b['name']].lower() == node.lower() and b['shader'] >= 0]
    path = nif.strings[nif.blocks[shaders[0]][1]['name']] if shaders else ''
    if path not in converted.materials:
        return None
    source = f'textures\\{texture.replace("/", chr(92)).lower()}.dds'
    material = copy.deepcopy(converted.materials[path])
    material['textures']['diffuse'] = fo4_texture(source).replace('\\', '/')
    new = retextured(path, converted.materials[path], material)
    out = _material_file(data_dir, new)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bgsm.write(material))
    copy_texture(export_dir, data_dir, source)
    return path, new


def swapped_material(export_dir: Path, data_dir: Path, material: str, textures: tuple) -> str:
    """Material `material` (already in `data_dir`) showing FNV texture set `textures` (diffuse, normal or ''),
    written with its textures beside it; its path (retextured(): named by its contents).

    The normal map's alpha becomes the specular map, at the glossiness of
    the material's own map, as convert_static does; without a mask in it
    specular is off.

    See: docs/fork/fo4_spikes.md#spike-4-outfits
    """
    diffuse, normal = (texture_source(t) if t else '' for t in textures)
    own = bgsm.read(_material_file(data_dir, material).read_bytes())
    mat = copy.deepcopy(own)
    mat['textures']['diffuse'] = fo4_texture(diffuse).replace('\\', '/')
    copy_texture(export_dir, data_dir, diffuse)
    if normal:
        mat['textures']['normal'] = fo4_texture(normal).replace('\\', '/')
        copy_texture(export_dir, data_dir, normal)
        _swapped_spec(export_dir, data_dir, mat, normal)
    new = retextured(material, own, mat)
    if new != material:
        target = _material_file(data_dir, new)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bgsm.write(mat))
    return new


def _swapped_spec(export_dir: Path, data_dir: Path, mat: dict, normal: str) -> None:
    """Point `mat`'s specular map at one made from FNV `normal`'s alpha, at the glossiness of its own."""
    source = export_file(export_dir, normal.replace('\\', '/'))
    if not mat['specular'] or not spec_mask.has_mask(source.read_bytes()):
        mat['specular'], mat['textures']['smooth_spec'] = False, ''
        return
    glossiness = spec_glossiness(mat['textures']['smooth_spec'])
    path = spec_map_path(normal, glossiness)
    stage_derived(data_dir, path, spec_map, (source,), smoothness(glossiness))
    mat['textures']['smooth_spec'] = path.replace('\\', '/')


def _material_file(data_dir: Path, material: str) -> Path:
    """The data folder file of material path `material` (materials\\...)."""
    return data_dir / material.replace('materials\\', 'Materials\\', 1)


def copy_texture(export_dir: Path, data_dir: Path, source: str, later: 'list | None' = None) -> bool:
    """stage_texture() FNV texture `source` (textures\\...) at its FO4 path; False, counting a source fault,
    when no export layer holds it."""
    rel = texture_source(source).replace('\\', '/')
    path = export_file(export_dir, rel)
    if not path.is_file():
        count(SourceFault(path, 'missing texture (in no export layer)'))
        return False
    plan = functools.partial(_copy_plan, path, replaced_file(export_dir, rel))
    return stage_texture(data_dir, fo4_texture(source), plan, later)


def _copy_plan(path: Path, replaced: 'Path | None') -> tuple:
    """stage_texture's (signature, writer) of `path`: a copy, or, when it replaces `replaced`, _mend().
    See: docs/fork/fo4_plugin_layout.md#premultiplied-replacers
    """
    stat = path.stat()
    signature = f'copy {str(path).lower()} {stat.st_size} {stat.st_mtime_ns}'
    if replaced is None:
        return signature, functools.partial(shutil.copyfile, path)
    under = replaced.stat()
    return (f'{signature} over {str(replaced).lower()} {under.st_size} {under.st_mtime_ns} v{MENDED_VERSION}',
            functools.partial(write_mended, path, replaced))


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
