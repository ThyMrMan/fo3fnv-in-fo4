"""F3NV_NeckTest.esl: the in-game check of the face neck rule (face extras faded out by the race's neck mask).

    py -3.14 -m fo4_import.spike.neck_test --nv <built FalloutNV.esm> --out <folder>

Own copies of built FalloutNV.esm NPCs, kept as built (race, skin, outfit, head) but for their factions, packages
and scripts; each stands put. Their EditorIDs stay FNV's, so the faces stage pairs them with FNV's NPCs and writes
their FaceGen afresh in this plugin.

See: docs/fork/fo4_look_races_plan.md#order
"""

import argparse
from pathlib import Path

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike.child_race_test import COMPRESSED, object_id, pack
from fo4_import.spike.skin_swap_test import STAY, placed, read

PLUGIN, MASTERS = 'F3NV_NeckTest.esl', ['Fallout4.esm', 'FalloutHelpers.esl', 'FalloutNV.esm']
#: The NPCs copied: regular adults of three races, two old ones, and two raiders on step 1's dirty skin.
NPCS = ('FNV_GSSunnySmiles', 'FNV_GSRingo', 'FNV_GSJoeCobb', 'FNV_DocMitchell', 'FNV_GSEasyPete',
        'FNV_VFSFreesideThugCM02', 'FNV_VFSFreesideResidentAAF03')
#: NPC_ subrecords dropped from a copy: factions, packages, scripts.
DROPPED = {b'SNAM', b'PKID', b'VMAD'}


def own(edid: str) -> int:
    """The FormID of this plugin's record `edid`."""
    return len(MASTERS) << 24 | object_id(edid)


def records(nv: Path) -> list:
    """[(signature, record)]: a standing copy of each of NPCS."""
    ours = read(nv, (b'NPC_',), MASTERS.index('FalloutNV.esm'))
    out = []
    for edid in NPCS:
        _, _, flags, subs = ours[edid]
        kept = placed([(t, d) for t, d in subs if t not in DROPPED], b'PKID', STAY, (b'CNAM',))
        out.append(('NPC_', pack_fo4_record('NPC_', own(edid), flags & ~COMPRESSED, pack(kept))))
    return out


def build(out_dir: Path, nv: Path) -> Path:
    """Write <out_dir>/F3NV_NeckTest.esl from built FalloutNV.esm `nv`; its path."""
    assert len({object_id(e) for e in NPCS}) == len(NPCS), 'object id collision'
    writer = FO4PluginWriter(masters=MASTERS, is_esm=True, is_esl=True, author='fo3fnv-in-fo4',
                             description='Face neck rule: in-game check')
    for sig, rec in records(nv):
        writer.add_record(sig, rec)
    writer.next_object_id = max(map(object_id, NPCS)) + 1
    out = Path(out_dir) / PLUGIN
    out.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(out))
    return out


def main() -> None:
    """Command line: write the test plugin to --out."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--nv', type=Path, required=True, help='the built FalloutNV.esm')
    parser.add_argument('--out', type=Path, required=True, help='folder for F3NV_NeckTest.esl')
    args = parser.parse_args()
    print(build(args.out, args.nv))


if __name__ == '__main__':
    main()
