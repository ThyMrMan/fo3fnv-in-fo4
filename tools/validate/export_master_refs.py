"""Check that a dependent plugin's export resolves every reference into its masters through the layered export.

An export whose plugin has masters (an FNV DLC on FalloutNV.esm) is read with its masters' exports behind it
(fo4_import.pipeline.export_index). This reads every field of the plugin's own export files whose value is an
8-digit hex FormID, and checks it names a record: a master's (master byte below the plugin's own index) in the
layered export, the plugin's own in its own files. It prints the counts and the unresolved by field, so a build
never silently drops a reference into a master. A FormID-looking value that is not a FormID shows here too, under
its field name. A master byte past the plugin's masters is the plugin's own, as the engine reads it; an object
id below 0x800 on the first master is an engine form (the player's 00000014), counted apart.

Usage:
  py -3.14 -m tools.validate.export_master_refs export/GunRunnersArsenal.esm [--show 20]

See: docs/fork/fo4_plugin_layout.md#dlc
"""

import argparse
import collections
import re
from pathlib import Path

from fo4_import.pipeline.export_index import export_masters, export_records, held_types, own_records

FORMID = re.compile(r'^[0-9A-Fa-f]{8}$')
#: Field-name parts of values that are not FormIDs though they look like one (raw bytes, flags as hex).
NOT_FORMID = ('.Raw', 'Flags', 'Hash')
#: (type, field) pairs whose 8-hex value is not a FormID: ADDN DNAM is a particle cap and flags.
NOT_FORMID_FIELDS = frozenset({('ADDN', 'DNAM')})
#: Object ids the engine defines itself (the player 00000014, its base 00000007).
ENGINE_IDS = 0x800


def check(export_dir: Path) -> dict:
    """{'master', 'own', 'engine': resolved counts, 'missing': Counter of (field, kind)} for `export_dir`."""
    own_index = len(export_masters(str(export_dir)))

    def owned(fid: int) -> int:
        """`fid` with a master byte past the masters read as the plugin's own index."""
        return fid if fid >> 24 < own_index else own_index << 24 | fid & 0xFFFFFF
    sigs = held_types(export_dir)
    known = {owned(int(r['FormID'], 16)) for sig in sigs for r in export_records(export_dir, sig)}
    for folder in export_masters(str(export_dir)):
        known |= {int(r['FormID'], 16) for sig in held_types(folder) for r in export_records(folder, sig)}
    out = {'master': 0, 'own': 0, 'engine': 0, 'missing': collections.Counter(), 'examples': {}}
    for sig in sigs:
        for rec in own_records(export_dir, sig):
            for key, value in rec.items():
                if key == 'FormID' or not isinstance(value, str) or not FORMID.match(value):
                    continue
                fid = owned(int(value, 16))
                if any(part in key for part in NOT_FORMID) or (sig, key) in NOT_FORMID_FIELDS or not fid:
                    continue
                kind = 'master' if fid >> 24 < own_index else 'own'
                if kind == 'master' and fid < ENGINE_IDS:
                    out['engine'] += 1
                    continue
                if fid in known:
                    out[kind] += 1
                    continue
                field = f'{sig} {re.sub(r"\[\d+\]", "[]", key)}'
                out['missing'][(field, kind)] += 1
                out['examples'].setdefault((field, kind), f'{rec.get("EditorID", rec["FormID"])} -> {value}')
    return out


def main():
    """Print the check's counts and unresolved fields."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('export_dir', type=Path)
    ap.add_argument('--show', type=int, default=20, help='unresolved fields to list')
    args = ap.parse_args()
    found = check(args.export_dir)
    missing = sum(found['missing'].values())
    print(f"{args.export_dir.name}: master references resolved {found['master']}, own {found['own']}, "
          f"engine forms {found['engine']}, unresolved {missing}")
    for (field, kind), count in found['missing'].most_common(args.show):
        print(f"  {count:6} {kind:6} {field}  e.g. {found['examples'][(field, kind)]}")


if __name__ == '__main__':
    main()
