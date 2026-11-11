"""FNV SpeedTree trees (TREE records, `.spt`) as Fallout 4 meshes, built like vanilla's wind-animated trees.

A TREE has no mesh: its geometry is asset_convert.speedtree's generator's
(bark, leaf cards with the wind weight in vertex alpha, a collision mesh),
seeded by the record. Vanilla Fallout 4 trees are statics; its 66
wind-animated ones (blastedforestfungaltreelarge01) have a BSLeafAnimNode
root, BSXFlags 130, vertex-coloured shapes, the leaves alpha-tested,
two-sided and on a tree-flagged material (shader flags2 Tree Anim). The
collision is the generated mesh on the source game's own tree body (FNV's
nvgreybirch01, FO3's treedead01: fixed), finished by Elric as the statics' is.

See: docs/fork/fo4_spikes.md#spike-4-trees
"""

from pathlib import Path

import numpy as np

from asset_convert.nif.pyffi_monkey_patch import apply_patches
from asset_convert.speedtree.spt_generator import build_tree
from asset_convert.speedtree.spt_parser import parse_spt
from fo4_import.nif import fnv_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.collision import material, mesh_collision
from fo4_import.nif.convert_static import IDENTITY, NODE_FLAGS, Converted, emit, lit_material
from fo4_import.nif.file import NifFile
from fo4_import.pipeline.export_index import export_file, source_game

apply_patches()
from pyffi.formats.nif import NifFormat

#: Vanilla wind-animated tree shapes' lighting shader flags (blastedforestfungaltreelarge01): leaves, bark.
LEAF_FLAGS, BARK_FLAGS = (0x80400209, 0x20000031), (0x8C400201, 0x21)
#: Vanilla tree leaves' NiAlphaProperty: alpha test (flags) and its threshold.
LEAF_ALPHA = (0x12EC, 160)
#: BSXFlags of vanilla's trees (131 of 151).
TREE_BSX = 130
#: FNV Havok material wood (index into collision.MATERIALS).
FNV_WOOD = 9
#: Per source game (export_index.source_game), its own tree whose collision object gives the trunk's body settings.
BODY_TEMPLATES = {'fnv': Path('meshes') / 'landscape' / 'trees' / 'nvgreybirch01.nif',
                  'fo3': Path('meshes') / 'landscape' / 'trees' / 'treedead01.nif'}


class _Alpha:
    """An NiAlphaProperty's two fields, as convert_static's material code reads them."""

    def __init__(self, flags: int, threshold: int):
        """`flags` and `threshold` of the property."""
        self.flags, self.threshold = flags, threshold


def tree_mesh(export_dir: Path, rec: dict) -> Converted:
    """The FO4 mesh of FNV TREE `rec` (its .spt under <export>/trees, its first seed, leaves from ICON)."""
    spt = export_file(export_dir, 'trees', Path(rec['Model.MODL'].replace('\\', '/')).name.lower())
    tree = parse_spt(spt)
    geo = build_tree(tree, seed=int(rec['Seed[0]']) if 'Seed[0]' in rec else None)
    nif = NifFile()
    out = Converted(nif)
    root = {'name': nif.string(rec['EditorID']), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS,
            'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0, 'collision': NONE, 'children': []}
    nif.blocks.append(('BSLeafAnimNode', root))
    nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': TREE_BSX}))
    root['extra'].append(1)
    bark = Path(tree.bark_texture.replace('\\', '/')).stem.lower()
    bark_textures = [f'textures\\trees\\branches\\{bark}.dds', f'textures\\trees\\branches\\{bark}_n.dds']
    bark_mat = lit_material([t for t in bark_textures if export_file(export_dir, t.replace('\\', '/')).exists()], {}, None, False,
                     False, export_dir)
    root['children'].append(_shape(nif, f'{rec["EditorID"]}:Bark', (geo.bark_verts, geo.bark_uvs, geo.bark_normals,
                                   geo.bark_colors), geo.bark_tris, bark_mat, BARK_FLAGS, out))
    leaf_mat = lit_material([f'textures\\trees\\leaves\\{rec["ICON"].lower()}'], {}, _Alpha(*LEAF_ALPHA), True, False,
                     export_dir)
    leaf_mat.data['tree'] = True
    for i, group in enumerate(geo.leaf_groups):
        root['children'].append(_shape(nif, f'{rec["EditorID"]}:Leaves{i}', (group['verts'], group['uvs'],
                                       group['normals'], group['colors']), group['tris'], leaf_mat, LEAF_FLAGS, out))
    root['collision'] = _collision(nif, export_dir, geo)
    return out


def _shape(nif: NifFile, name: str, arrays: tuple, tris, mat, flags: tuple, out: Converted) -> int:
    """One generated shape (positions, UVs, normals, RGBA colours) with `mat`, its shader flags set to `flags`."""
    pos, uv, nrm, colors = (np.asarray(a, float) for a in arrays)
    index = emit(nif, name, (pos, uv, nrm, colors, None), np.asarray(tris, int), mat, out)
    shader = nif.blocks[index + 1][1]
    shader['flags1'], shader['flags2'] = flags
    return index


def _collision(nif: NifFile, export_dir: Path, geo) -> int:
    """The generated collision mesh (wood) on the source game's BODY_TEMPLATES collision object, for the root."""
    data = fnv_file.read(export_file(export_dir, BODY_TEMPLATES[source_game(export_dir)]))
    template = next(b for b in data.blocks if isinstance(b, NifFormat.bhkCollisionObject))
    tris = [tuple(tuple(float(c) for c in verts[i]) for i in tri)
            for verts, faces in zip(geo.collision_verts, geo.collision_tris) for tri in np.asarray(faces, int)]
    return mesh_collision(nif, 0, tris, [material(FNV_WOOD)] * len(tris), template)
