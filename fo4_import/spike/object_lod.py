"""A build's distant object LOD: each flagged static's LOD meshes (STAT flag and MNAM), and per worldspace the
LODGenx64 rows of the references placed on them, written as the input list pipeline.object_lod bakes.

A static keeps FNV's Visible When Distant flag. Its LOD mesh is FNV's
`<model>_lod.nif`, else, for one at least LOD8_MIN_SIZE across, lod_far_gen's
reduction of its model; either goes through the static mesh path. MNAM
names it at levels 4 and 8, and 16 from LOD16_MIN_SIZE across. A row is
xEdit's FO4 reference line: the REFR as written (degrees), then the base.

See: docs/fork/fo4_pipeline.md#object-lod
"""

import math
import struct
import tempfile
from pathlib import Path

from asset_convert.lod.lod_far_gen import generate_far_nif
from asset_convert.lod.lod_gen import LOD8_MIN_SIZE, LOD16_MIN_SIZE
from fo4_import.pipeline.code_tag import ROOT
from fo4_import.pipeline.export_index import export_file
from fo4_import.pipeline.mesh_cache import cached_files
from fo4_import.pipeline.object_lod import list_path
from fo4_import.pipeline.work_cache import cached
from fo4_import.spike.statics import write_files
from tes5_import.base.tes5_reader import subrecords

#: STAT flag Has Distant LOD (FNV's Visible When Distant, the same bit), also a reference's.
VISIBLE_DISTANT = 0x8000
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
    if made is None:
        return None
    target = FAR_CACHE / f'{rel[:-4]}_lod.nif'
    if not target.is_file() or target.read_bytes() != made:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(made)
    return target


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

    def _lod_mesh(self, rec: dict) -> 'str | None':
        """FO4 path (under Meshes) of FNV static `rec`'s converted LOD mesh (module notes); None without one."""
        rel = model_rel(rec)
        lod = f'{rel[:-4]}_lod.nif'
        if export_file(self.builder.export_dir, 'meshes', lod).is_file():
            return self.builder.mesh(lod)[0]
        far = far_source(self.builder.export_dir, rel) if size(rec) >= LOD8_MIN_SIZE else None
        if far is None:
            return None
        builder = self.builder
        builder.meshes[f'{rel}#lod'] = write_files(builder.export_dir, cached_files(far, builder.export_dir),
                                                   f'{rel[:-4]}_lod.nif', builder.data_dir)
        builder.counts['object LOD meshes reduced from the model'] += 1
        return builder.meshes[f'{rel}#lod'][0]

    def stat(self, fid: int, rec: dict, edid: str, model: str) -> tuple:
        """(record flags, MNAM meshes) of FNV static `rec` written on `fid` as `edid` with `model`; noted for rows."""
        if not int(rec.get('RecordFlags', 0)) & VISIBLE_DISTANT:
            return 0, ()
        lod = self._lod_mesh(rec)
        self.builder.counts['flagged statics with an LOD mesh' if lod else 'flagged statics without one'] += 1
        if lod is None:
            return VISIBLE_DISTANT, ()
        lods = mnam(lod, size(rec))
        named = '\t'.join(f'meshes\\{m}'.lower() if m else '' for m in (model, *lods))
        self.bases[fid] = f'{edid}\t{VISIBLE_DISTANT:08X}\t\t{named}'
        return VISIBLE_DISTANT, lods

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
