"""FNV add-on nodes as FO4's: a BSValueNode naming an ADDN by index, mapped to Fallout4.esm's ADDN of the same name.

FNV attaches particle effects (the fire on a burning barrel's light) by a
BSValueNode whose value is an ADDN record's DATA index; FO4 does the same.
The indices differ (FNV's MPSFireSmall01 is 14, FO4's is 4), so the FNV
index's ADDN EditorID picks Fallout4.esm's ADDN of that name and its index.
FNV's ambient smoke has no FO4 namesake and takes STAND_INS' (drift); any
other add-on with no same-named FO4 ADDN is left out. The mapping is data the
mesh cache keys on, passed into convert_static.convert.

See: docs/fork/fo4_pipeline.md#addons
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk


#: FNV ADDN EditorID -> the Fallout4.esm ADDN standing in: FO4's car damage stages smoke with MPSSmokeFireMed01.
STAND_INS = {'MPSSmokeMed01': 'MPSSmokeFireMed01', 'MPSSmokeSmall01': 'MPSSmokeFireMed01'}


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
def addon_map(export_dir: str) -> dict:
    """{FNV ADDN index: Fallout4.esm's ADDN index of the same EditorID, or of its STAND_INS entry}, if any."""
    fo4 = _fo4_by_name()
    names = {int(r['DATA.Index']): STAND_INS.get(r['EditorID'], r['EditorID'])
             for r in export_records(Path(export_dir), 'ADDN')}
    return {index: fo4[name] for index, name in sorted(names.items()) if name in fo4}
