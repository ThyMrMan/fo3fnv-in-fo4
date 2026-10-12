"""FNV's globals as Fallout 4's: every FNV global, on FNV's FormID, with its type, value and constant flag.

The six engine globals both games define (GameHour, GameDaysPassed, GameDay,
GameMonth, GameYear, TimeScale) stay Fallout4.esm's, as scripts already
bind them. The rest are written once a build, so script properties,
GetGlobalValue conditions and comparisons against a global all resolve.

See: docs/fork/fo4_pipeline.md#globals
"""

from pathlib import Path

from fo4_import.base.support_records import pack_global
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.script import fo4_forms

#: FNV GLOB record flag Constant, which FO4 keeps in the same bit.
CONSTANT = 0x40


def write_all(builder, export_dir: Path) -> dict:
    """Write every FNV global through `builder`; {FNV FormID: FO4 FormID}, engine globals as Fallout4.esm's."""
    engine = fo4_forms()['GlobalVariable']
    out = {}
    for rec in export_records(export_dir, 'GLOB'):
        fnv, edid = int(rec['FormID'], 16), rec.get('EditorID', '')
        if edid in engine:
            out[fnv] = engine[edid]
            continue
        out[fnv] = fid = builder.fnv_id(rec['FormID'])
        builder.writer.add_record('GLOB', pack_global(fid, f'FNV_{edid}', rec.get('FNAM.Type', 's'),
                                                      float(rec.get('FLTV.Value', 0.0)),
                                                      int(rec.get('RecordFlags', 0)) & CONSTANT))
        builder.counts['GLOB'] += 1
    return out
