"""FNV add-on nodes as FO4's: a BSValueNode naming an ADDN by index, mapped to Fallout4.esm's ADDN of the same name.

FNV attaches particle effects (the fire on a burning barrel's light) by a
BSValueNode whose value is an ADDN record's DATA index; FO4 does the same.
The indices differ (FNV's MPSFireSmall01 is 14, FO4's is 4), so the FNV
index's ADDN EditorID picks Fallout4.esm's ADDN of that name and its index.
An add-on with no same-named FO4 ADDN is left out.

See: docs/fork/fo4_pipeline.md#addons
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk


@functools.cache
def _fo4_by_name() -> dict:
    """{EditorID: DATA index} of Fallout4.esm's ADDN records."""
    out = {}
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), b'ADDN'):
        data, edid = first_sub(rec.body, b'DATA'), first_sub(rec.body, b'EDID')
        if data and edid:
            out.setdefault(edid.rstrip(b'\0').decode(), struct.unpack('<i', data[:4])[0])
    return out


@functools.cache
def _fnv_names(export_dir: str) -> dict:
    """{DATA index: EditorID} of the FNV export's ADDN records."""
    return {int(r['DATA.Index']): r['EditorID'] for r in export_records(Path(export_dir), 'ADDN')}


def fo4_index(fnv_index: int, export_dir: str) -> 'int | None':
    """Fallout4.esm's ADDN index of FNV add-on `fnv_index`'s EditorID, or None."""
    return _fo4_by_name().get(_fnv_names(export_dir).get(fnv_index, ''))
