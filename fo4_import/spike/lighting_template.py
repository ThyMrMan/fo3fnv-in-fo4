"""An FNV interior's lighting as FNV renders it: each field its LNAM flags inherit taken from its lighting template.

The export writes a cell's XCLL and LTMP but not LNAM (the inherit flags),
so the flags are read from FalloutNV.esm once per build. A template's DATA
has XCLL's 40-byte layout. Doc's house inherits ambient, directional and
fog colour, fog near and far and clip distance (0x9F): its own XCLL fog
(100 to 1,500) is unused, the template's (64 to 5,000) shows.

See: docs/fork/fo4_pipeline.md#lighting-templates
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import source_walk
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import subrecords

#: (LNAM bit, XCLL export keys, DATA offset, struct format) of each inheritable field.
FIELDS = ((0x1, ('AmbientR', 'AmbientG', 'AmbientB'), 0, '3B'),
          (0x2, ('DirectionalR', 'DirectionalG', 'DirectionalB'), 4, '3B'),
          (0x4, ('FogR', 'FogG', 'FogB'), 8, '3B'),
          (0x8, ('FogNear',), 12, 'f'),
          (0x10, ('FogFar',), 16, 'f'),
          (0x20, ('DirectionalRotXY', 'DirectionalRotZ'), 20, '2i'),
          (0x40, ('DirectionalFade',), 28, 'f'),
          (0x80, ('FogClipDist',), 32, 'f'),
          (0x100, ('FogPower',), 36, 'f'))


@functools.cache
def inherit_flags() -> dict:
    """{FNV cell FormID: LNAM inherit flags} of FalloutNV.esm's cells that have them."""
    return {rec.form_id: struct.unpack('<I', s[b'LNAM'])[0] for rec, _ in source_walk(b'CELL')
            if b'LNAM' in (s := dict(subrecords(rec.body)))}


@functools.cache
def _templates(export_dir: Path) -> dict:
    """{FNV LGTM FormID hex: DATA bytes}."""
    return {r['FormID']: bytes.fromhex(r['DATA']) for r in export_records(export_dir, 'LGTM') if 'DATA' in r}


def resolved(export_dir: Path, cell: dict) -> dict:
    """`cell` with each XCLL field its inherit flags name replaced by its lighting template's value."""
    data = _templates(export_dir).get(cell.get('LTMP.LightingTemplate', ''))
    flags = inherit_flags().get(int(cell['FormID'], 16), 0)
    if not data:
        return cell
    out = dict(cell)
    for bit, keys, offset, fmt in FIELDS:
        if flags & bit:
            out.update({f'XCLL.{k}': str(v) for k, v in zip(keys, struct.unpack_from('<' + fmt, data, offset))})
    return out
