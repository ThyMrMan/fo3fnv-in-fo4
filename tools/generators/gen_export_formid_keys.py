"""Classify the export keys holding 8-digit hex values as FormIDs or not, over FO3/FNV exports.

A key is a FormID when every nonzero value it holds is a record FormID in the census exports (or an engine id
below 0x800); not one when none is; mixed otherwise, for a person to decide (a dangling reference, a condition
parameter that is a FormID only for some functions). Keys are normalized: `[n]` becomes `[]`.

    py -3.14 -m tools.generators.gen_export_formid_keys export/FalloutNV.esm export/Fallout3.esm ... \
        -o fo4_import/data/export_formid_keys.census.json

See: docs/fork/fo4_plugin_layout.md#multi-master
"""

import argparse
import collections
import json
import re
from pathlib import Path

from tes5_import.base.text_reader import parse_export_file

HEX = re.compile(r'^[0-9A-F]{8}$')
INDEX = re.compile(r'\[\d+\]')
#: FormIDs below this are the engine's own forms (player, hardcoded globals).
ENGINE_IDS = 0x800


def normalized(key: str) -> str:
    """`key` with each `[n]` index as `[]`."""
    return INDEX.sub('[]', key)


def census(exports: list) -> dict:
    """{normalized key: [values, values that are records]} over `exports`' 8-hex values."""
    records = [rec for folder in exports for f in sorted(Path(folder).glob('*.txt')) if not f.name.startswith('_')
               for rec in parse_export_file(str(f))]
    ids = {int(rec['FormID'], 16) & 0xFFFFFF for rec in records}
    out = collections.defaultdict(lambda: [0, 0])
    for rec in records:
        for key, value in rec.items():
            if key != 'FormID' and isinstance(value, str) and HEX.match(value) and int(value, 16):
                row = out[normalized(key)]
                row[0] += 1
                row[1] += int(value, 16) & 0xFFFFFF in ids or int(value, 16) < ENGINE_IDS
    return out


def classify(rows: dict) -> dict:
    """{'formid': [...], 'not_formid': [...], 'mixed': {key: [values, records]}} of census() `rows`."""
    out = {'formid': [], 'not_formid': [], 'mixed': {}}
    for key, (seen, hits) in sorted(rows.items()):
        if hits == seen:
            out['formid'].append(key)
        elif not hits:
            out['not_formid'].append(key)
        else:
            out['mixed'][key] = [seen, hits]
    return out


def main() -> None:
    """Write the classification of the given exports' keys."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('exports', nargs='+')
    ap.add_argument('-o', '--out', type=Path, required=True)
    args = ap.parse_args()
    result = classify(census(args.exports))
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print({k: len(v) for k, v in result.items()})


if __name__ == '__main__':
    main()
