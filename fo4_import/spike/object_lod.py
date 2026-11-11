"""A build's distant object LOD: each flagged static's LOD meshes (STAT flag and MNAM), and per worldspace the
LODGenx64 rows of the references placed on them, written as the input list pipeline.object_lod bakes.

A static keeps FNV's Visible When Distant flag. Its LOD mesh is FNV's
`<model>_lod.nif`, else, for one at least LOD8_MIN_SIZE across, lod_far_gen's
reduction of its model; either goes through the static mesh path. MNAM
names it at levels 4 and 8, and 16 from LOD16_MIN_SIZE across. A row is
xEdit's FO4 reference line: the REFR as written (degrees), then the base.

Trees: FNV ships no tree LOD lists, so its Has Tree LOD statics popped in.
One keeps its `_lod.nif` when FNV ships one (Joshua tree A), else gets a
crossed card from Fallout 3's tree LOD atlas (TREE_CARDS); a TREE gets a
card of its SpeedTree billboard. Either takes the LOD mesh path above.

See: docs/fork/fo4_pipeline.md#object-lod
See: docs/fork/fo4_pipeline.md#tree-lod
"""

import io
import math
import struct
import tempfile
from pathlib import Path

import numpy as np

from asset_convert.lod.lod_far_gen import generate_far_nif
from asset_convert.lod.lod_gen import LOD8_MIN_SIZE, LOD16_MIN_SIZE
from asset_convert.nif.pyffi_monkey_patch import apply_patches
from fo4_import.base.source_fault import without_fault
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.export_index import export_file, source_game
from fo4_import.pipeline.mesh_cache import cached_files
from fo4_import.pipeline.object_lod import list_path
from fo4_import.pipeline.work_cache import cached
from fo4_import.spike.statics import write_files
from tes5_import.base.tes5_reader import subrecords

apply_patches()
from pyffi.formats.nif import NifFormat

#: STAT flag Has Distant LOD (FNV's Visible When Distant, the same bit), also a reference's.
VISIBLE_DISTANT = 0x8000
#: FNV STAT flag Has Tree LOD (record flag 6, as Fallout 3's).
HAS_TREE_LOD = 0x40
#: Fallout 3's tree LOD cards (Wasteland treetypes.lst; see #tree-lod): model -> (TREE_ATLAS rect, card size).
TREE_CARDS = {
    'landscape\\trees\\treewastelandevergreen04.nif': ((0.0, 0.5, 0.35692617, 1.0), (338.55756, 526.62073)),
    'landscape\\trees\\treewastelandevergreen03.nif': ((0.61846215, 0.5, 0.79177582, 1.0), (350.64441, 1004.1193)),
    'landscape\\trees\\treewastelandhardwood01.nif': ((0.0, 0.0, 0.5, 0.5), (803.62482, 846.87396)),
    'landscape\\trees\\treedead03.nif': ((0.68818724, 0.0, 0.8039158, 0.5), (160.26001, 753.96527)),
    'landscape\\trees\\treedead04.nif': ((0.8419894, 0.09047115, 0.94584173, 0.49597114), (143.43336, 611.67938)),
    'landscape\\trees\\treedead02.nif': ((0.53505367, 0.15139377, 0.65164417, 0.49989378), (161.20332, 525.79095)),
    'landscape\\trees\\treewastelandevergreen01.nif': ((0.36, 0.49999994, 1.0, 0.7475785), (350.64441, 1004.1193)),
    'landscape\\trees\\treewastelandevergreen02.nif': ((0.0, 0.5, 0.35692617, 1.0), (338.55756, 526.62073)),
}
#: The atlas TREE_CARDS map into, under textures (FNV ships Fallout 3's).
TREE_ATLAS = 'landscape\\trees\\treedeadlod.dds'
#: A whole billboard texture's UV rectangle.
WHOLE = (0.0, 0.0, 1.0, 1.0)
#: Per source game (export_index.source_game), its own flat tree LOD mesh whose node and properties a card keeps.
CARD_TEMPLATES = {'fnv': Path('meshes') / 'landscape' / 'trees' / 'treejoshanv_lod.nif',
                  'fo3': Path('meshes') / 'landscape' / 'trees' / 'treedead02_lod_flat.nif'}
#: REFR flag Initially Disabled.
INITIALLY_DISABLED = 0x800
#: Bytes of a record's header before its fields (signature, size, flags, FormID, version control, form version).
RECORD_HEADER = 24
#: Where FNV-format reductions of models without a LOD mesh are kept, and their work-cache site.
FAR_CACHE, FAR_SITE = ROOT / 'output' / 'fo4_cache' / 'object_lod' / 'far', 'lod_far_reduction'
#: Empty fields closing a row: enable parent, base and swap materials, a static collection part's 7 transforms.
ROW_TAIL = '\t' * 10


def size(rec: dict) -> int:
    """An FNV record's largest OBND side."""
    return max(abs(int(rec.get(f'OBND.{a}2', 0)) - int(rec.get(f'OBND.{a}1', 0))) for a in 'XYZ')


def model_rel(rec: dict) -> str:
    """An FNV record's model path under meshes, lowercase with backslashes."""
    return rec.get('Model.MODL', '').replace('/', '\\').lower()


def lod_sources(export_dir: Path, recs: list) -> set:
    """FNV `_lod.nif` files of the flagged statics among `recs`."""
    flagged = (r for r in recs if r.get('Signature') == 'STAT' and int(r.get('RecordFlags', 0)) & VISIBLE_DISTANT)
    found = {export_file(export_dir, 'meshes', f'{model_rel(r)[:-4]}_lod.nif') for r in flagged if model_rel(r)}
    return {path for path in found if path.is_file()}


def _reduced(source: Path) -> 'bytes | None':
    """lod_far_gen's reduction of FNV mesh `source`; None if none."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'far.nif'
        return target.read_bytes() if generate_far_nif(source, target) else None


def far_source(export_dir: Path, rel: str) -> 'Path | None':
    """The kept reduction (FAR_CACHE/`rel` as `_lod.nif`) of FNV model `rel`, work-cached by its bytes; None when
    it has no source or cannot be reduced; keyed by the reducer's module, not this one (which reaches the records)."""
    source = export_file(export_dir, 'meshes', rel)
    made = (cached(FAR_SITE, generate_far_nif.__module__, (source.read_bytes(),), lambda: _reduced(source))
            if source.is_file() else None)
    return None if made is None else keep(rel, made)


def keep(rel: str, made: bytes) -> Path:
    """FAR_CACHE/`rel` as `_lod.nif`, holding FNV-format LOD mesh `made` (rewritten only when it changed)."""
    target = FAR_CACHE / f'{rel[:-4]}_lod.nif'
    if not target.is_file() or target.read_bytes() != made:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(made)
    return target


def _card_data(rect: tuple, size: tuple):
    """NiTriShapeData of two crossed quads `size` (width, height) standing on 0, textured by `rect`."""
    (u0, v0, u1, v1), (width, height) = rect, size
    half = width / 2
    corners = [(-half, 0, 0), (half, 0, 0), (half, 0, height), (-half, 0, height),
               (0, -half, 0), (0, half, 0), (0, half, height), (0, -half, height)]
    data = NifFormat.NiTriShapeData()
    data.num_vertices, data.has_vertices, data.has_normals, data.num_uv_sets = 8, True, True, 1
    data.vertices.update_size()
    data.normals.update_size()
    data.uv_sets.update_size()
    for i, (point, normal, uv) in enumerate(zip(corners, [(0, 1, 0)] * 4 + [(1, 0, 0)] * 4,
                                                [(u0, v1), (u1, v1), (u1, v0), (u0, v0)] * 2)):
        data.vertices[i].x, data.vertices[i].y, data.vertices[i].z = point
        data.normals[i].x, data.normals[i].y, data.normals[i].z = normal
        data.uv_sets[0][i].u, data.uv_sets[0][i].v = uv
    data.num_triangles, data.num_triangle_points, data.has_triangles = 4, 12, True
    data.triangles.update_size()
    for t, (a, b, c) in zip(data.triangles, ((0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7))):
        t.v_1, t.v_2, t.v_3 = a, b, c
    points = np.array(corners, float)
    centre = (points.min(axis=0) + points.max(axis=0)) / 2
    data.center.x, data.center.y, data.center.z = centre
    data.radius = float(np.linalg.norm(points - centre, axis=1).max())
    return data


def card_nif(export_dir: Path, texture: str, rect: tuple, size: tuple) -> bytes:
    """An FNV-format crossed-card LOD mesh: the source game's CARD_TEMPLATES node and properties, diffuse `texture`
    (under textures) cut to `rect`, cards `size` (width, height)."""
    data = NifFormat.Data()
    with open(export_file(export_dir, CARD_TEMPLATES[source_game(export_dir)]), 'rb') as f:
        data.read(f)
    strips = next(b for b in data.blocks if isinstance(b, NifFormat.NiTriStrips))
    shape = NifFormat.NiTriShape()
    shape.name, shape.flags, shape.data = b'TreeLodCard', strips.flags, _card_data(rect, size)
    shape.num_properties = strips.num_properties
    shape.properties.update_size()
    for i, prop in enumerate(strips.properties):
        shape.properties[i] = prop
    _card_texture(export_dir, strips.properties, texture)
    data.roots[0].children[0] = shape
    out = io.BytesIO()
    data.write(out)
    return out.getvalue()


def _card_texture(export_dir: Path, props, texture: str) -> None:
    """Put diffuse `texture` on a card's shader: a lit one's texture set (its `_n` beside it or none), an unlit
    one's file and its NiTexturingProperty's base source."""
    path = f'textures\\{texture}'.encode()
    for prop in props:
        if isinstance(prop, NifFormat.BSShaderPPLightingProperty):
            normal = f'{texture[:-4]}_n.dds'
            prop.texture_set.textures[0] = path
            prop.texture_set.textures[1] = (f'textures\\{normal}'.encode()
                                            if export_file(export_dir, 'textures', normal).is_file() else b'')
        elif isinstance(prop, NifFormat.BSShaderNoLightingProperty):
            prop.file_name = path
        elif isinstance(prop, NifFormat.NiTexturingProperty) and prop.has_base_texture:
            prop.base_texture.source.file_name = path


def mnam(lod: str, across: int) -> tuple:
    """MNAM meshes of LOD mesh `lod` on a static `across` units at its widest."""
    return lod, lod, lod if across >= LOD16_MIN_SIZE else '', ''


def _degrees(angles: tuple) -> str:
    """Rotations in radians as LODGen's tab-separated degrees."""
    return '\t'.join(f'{math.degrees(a):.4f}' for a in angles)


class ObjectLod:
    """The LOD meshes of a build's flagged statics, and the LODGen rows of the worldspace being placed."""

    def __init__(self, builder):
        """For `builder` (spike.cell.CellBuilder): no bases, no worldspace."""
        self.builder, self.bases, self.rows, self.world, self.worlds = builder, {}, [], None, []

    def _converted(self, rel: str, source: Path) -> 'str | None':
        """FO4 path (under Meshes) of FNV-format LOD mesh `source` made for model `rel`, through the static path;
        None, no LOD mesh, for a source fault (counted)."""
        builder = self.builder
        files = without_fault(cached_files, source, builder.export_dir)
        if files is None:
            builder.counts['LOD meshes left out (a source fault)'] += 1
            return None
        builder.meshes[f'{rel}#lod'] = write_files(builder.export_dir, files, f'{rel[:-4]}_lod.nif', builder.data_dir)
        return builder.meshes[f'{rel}#lod'][0]

    def _shipped(self, rel: str) -> 'str | None':
        """FO4 path of `rel`'s converted `_lod.nif`; None: none shipped, or faulted."""
        lod = f'{rel[:-4]}_lod.nif'
        shipped = export_file(self.builder.export_dir, 'meshes', lod).is_file()
        return (self.builder.mesh(lod)[0] or None) if shipped else None

    def _lod_mesh(self, rec: dict) -> 'str | None':
        """FO4 path (under Meshes) of FNV static `rec`'s converted LOD mesh (module notes); None without one."""
        rel = model_rel(rec)
        shipped = self._shipped(rel)
        far = far_source(self.builder.export_dir, rel) if shipped is None and size(rec) >= LOD8_MIN_SIZE else None
        if far is None:
            return shipped
        self.builder.counts['object LOD meshes reduced from the model'] += 1
        return self._converted(rel, far)

    def _tree_lod(self, rec: dict) -> 'str | None':
        """FO4 path of Has Tree LOD static `rec`'s LOD mesh: its `_lod.nif`, else a TREE_CARDS card; None for
        neither."""
        rel = model_rel(rec)
        shipped, card = self._shipped(rel), TREE_CARDS.get(rel)
        if shipped is not None or card is None:
            return shipped
        return self._converted(rel, keep(rel, card_nif(self.builder.export_dir, TREE_ATLAS, *card)))

    def _named(self, fid: int, edid: str, model: str, lod: str, across: float) -> tuple:
        """(record flags, MNAM meshes) of a static on `fid` with LOD mesh `lod`, `across` units at its widest;
        noted for rows."""
        lods = mnam(lod, across)
        named = '\t'.join(f'meshes\\{m}'.lower() if m else '' for m in (model, *lods))
        self.bases[fid] = f'{edid}\t{VISIBLE_DISTANT:08X}\t\t{named}'
        return VISIBLE_DISTANT, lods

    def stat(self, fid: int, rec: dict, edid: str, model: str) -> tuple:
        """(record flags, MNAM meshes) of FNV static `rec` written on `fid` as `edid` with `model`; noted for rows.
        A Has Tree LOD static gets _tree_lod's, flagged only with one."""
        flags = int(rec.get('RecordFlags', 0))
        if flags & VISIBLE_DISTANT:
            lod = self._lod_mesh(rec)
            self.builder.counts['flagged statics with an LOD mesh' if lod else 'flagged statics without one'] += 1
        else:
            lod = self._tree_lod(rec) if flags & HAS_TREE_LOD else None
            if lod is None:
                return 0, ()
            self.builder.counts['tree LOD statics with an LOD mesh'] += 1
        return (VISIBLE_DISTANT, ()) if lod is None else self._named(fid, edid, model, lod, size(rec))

    def tree(self, fid: int, rec: dict, edid: str, model: str) -> tuple:
        """(record flags, MNAM meshes) of FNV TREE `rec` written as a static on `fid`: a card of its SpeedTree
        billboard (textures\\trees\\billboards\\<.spt name>.dds) at its billboard size; (0, ()) without one."""
        stem = Path(rec['Model.MODL'].replace('\\', '/')).stem.lower()
        texture = f'trees\\billboards\\{stem}.dds'
        if not export_file(self.builder.export_dir, 'textures', texture).is_file():
            return 0, ()
        card = (float(rec['BNAM.BillboardWidth']), float(rec['BNAM.BillboardHeight']))
        rel = f'trees\\{stem}.nif'
        lod = self._converted(rel, keep(rel, card_nif(self.builder.export_dir, texture, WHOLE, card)))
        if lod is None:
            return 0, ()
        self.builder.counts['TREE with a billboard LOD card'] += 1
        return self._named(fid, edid, model, lod, max(card))

    def begin(self, world: str) -> None:
        """Collect rows for FO4 worldspace `world`."""
        self.world, self.rows = world, []

    def add(self, record: bytes, fnv_flags: int) -> None:
        """Row of placed REFR `record`, read back as written, while a worldspace is being placed and its base has
        LOD meshes; one starting disabled only when FNV flags (`fnv_flags`) it Visible When Distant."""
        if self.world is None:
            return
        flags, fid = struct.unpack_from('<2I', record, 8)
        fields = dict(subrecords(record[RECORD_HEADER:]))
        entry = self.bases.get(struct.unpack('<I', fields.get(b'NAME', bytes(4)))[0])
        if entry is None or flags & INITIALLY_DISABLED and not fnv_flags & VISIBLE_DISTANT:
            return
        x, y, z, *rotation = struct.unpack('<6f', fields[b'DATA'])
        scale = struct.unpack('<f', fields[b'XSCL'])[0] if b'XSCL' in fields else 1.0
        self.rows.append(f'{fid:08X}\t{flags:08X}\t{x:.4f}\t{y:.4f}\t{z:.4f}\t{_degrees(rotation)}\t{scale:.4f}\t'
                         f'{entry}{ROW_TAIL}')

    def write(self, data_dir: Path) -> int:
        """Write the worldspace's rows as its input list (pipeline.object_lod.list_path) and stop collecting; how
        many."""
        path = list_path(data_dir, self.world)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(f'{row}\n' for row in self.rows), encoding='utf-8')
        self.worlds.append(self.world)
        self.world = None
        return len(self.rows)
