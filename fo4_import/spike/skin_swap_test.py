"""F3NV_SkinSwapTest.esl: the in-game check of whether an outfit's bare skin takes its wearer's skin texture.

    py -3.14 -m fo4_import.spike.skin_swap_test --nv <built FalloutNV.esm> --out <folder>

Five copies of DoctorAmari, each standing where placed (`player.placeatme`), named for what they test:
1. clean skin, FNV's prewar negligee (converted); 2. SkinNakedDirty, the same negligee; 3. clean skin, a copy of
the negligee whose addon names the dirty body textures (ARMA NAM0/NAM1); 4. clean skin, vanilla's raider harness;
5. SkinNakedDirty, the harness. Both outfits draw their bare skin as a shader type 5 shape on the clean
FemaleBody_d.dds. Object ids come from the EditorIDs (child_race_test).

See: docs/fork/fo4_facegen_plan.md#skin-swap-test
"""

import argparse
import struct
from pathlib import Path

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike.child_race_test import COMPRESSED, object_id, pack, renamed
from tes5_import.base.tes5_reader import subrecords, walk

PLUGIN, MASTERS = 'F3NV_SkinSwapTest.esl', ['Fallout4.esm', 'FalloutHelpers.esl', 'FalloutNV.esm']
#: Fallout4.esm records read: the NPC copied, the dirty skin and its body textures, and the harness.
AMARI, DIRTY, HARNESS = 'DoctorAmari', 'SkinNakedDirty', 'Armor_GunnerRaider_Underwear2'
DIRTY_BODY = {b'NAM0': 'SkinBodyMaleDirty_1', b'NAM1': 'SkinBodyFemaleDirty_1'}
#: FalloutNV.esm's converted negligee and its addon, by EditorID.
NEGLIGEE, NEGLIGEE_AA = 'FNV_OutfitPrewarNegligee', 'FNV_AA_OutfitPrewarNegligee'
#: This plugin's negligee copy, its addon, and the NPCs: (EditorID, name, dirty skin, outfit's armor).
COPY, COPY_AA = 'F3NV_SkinTestNegligee', 'F3NV_SkinTestNegligeeAA'
NPCS = (('F3NV_SkinTest1', 'Skin test 1: clean, FNV negligee', False, NEGLIGEE),
        ('F3NV_SkinTest2', 'Skin test 2: dirty, FNV negligee', True, NEGLIGEE),
        ('F3NV_SkinTest3', 'Skin test 3: clean, negligee naming dirty textures', False, COPY),
        ('F3NV_SkinTest4', 'Skin test 4: clean, vanilla harness', False, HARNESS),
        ('F3NV_SkinTest5', 'Skin test 5: dirty, vanilla harness', True, HARNESS))
#: Fallout4.esm's DefaultStayAtEditorLocation package.
STAY = 0x3641
#: NPC_ subrecords dropped from the copy (factions, packages, scripts), and the tags WNAM and DOFT come before.
DROPPED = {b'SNAM', b'PKID', b'VMAD', b'DOFT', b'WNAM'}
SKIN_BEFORE, OUTFIT_BEFORE = (b'PRPS', b'COCT', b'CNTO', b'AIDT'), (b'CRIF', b'FTST', b'QNAM', b'DPLT')


def own(edid: str) -> int:
    """The FormID of this plugin's record `edid`."""
    return len(MASTERS) << 24 | object_id(edid)


def read(path: Path, sigs: tuple, renumber: int = 0) -> dict:
    """{EditorID: (signature, FormID, flags, [(tag, data)])} of `sigs` records in the plugin at `path`, FormIDs'
    load index replaced by `renumber` when given (a master's own records in this plugin's numbering)."""
    out = {}
    for rec, _ in walk(path.read_bytes(), *sigs):
        subs = list(subrecords(rec.body))
        fid = renumber << 24 | rec.form_id & 0xFFFFFF if renumber else rec.form_id
        out[dict(subs).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')] = (rec.sig.decode(), fid, rec.flags, subs)
    return out


def as_edid(subs: list, edid: str) -> list:
    """`subs` as record `edid` (its other strings as they are)."""
    return [(t, edid.encode() + b'\0' if t == b'EDID' else d) for t, d in subs]


def placed(subs: list, tag: bytes, value: int, before: tuple) -> list:
    """`subs` with subrecord `tag` = FormID `value` before the first of `before`."""
    at = next(i for i, (t, _) in enumerate(subs) if t in before)
    return subs[:at] + [(tag, struct.pack('<I', value))] + subs[at:]


def npc(amari: list, row: tuple, skin: int, outfit: int) -> list:
    """DoctorAmari's subrecords as test NPC `row`, standing put, wearing outfit `outfit` and skin `skin` (0: the
    race's)."""
    edid, name = row[:2]
    subs = [(t, name.encode() + b'\0' if t == b'FULL' else d) for t, d in renamed(amari, edid) if t not in DROPPED]
    subs = placed(subs, b'PKID', STAY, (b'CNAM',))
    subs = placed(subs, b'DOFT', outfit, OUTFIT_BEFORE)
    return placed(subs, b'WNAM', skin, SKIN_BEFORE) if skin else subs


def records(fo4: Path, nv: Path) -> list:
    """[(signature, record)]: the negligee copy and its addon, one outfit per armor, and the five NPCs."""
    base = read(fo4, (b'NPC_', b'ARMO', b'TXST'))
    ours = read(nv, (b'ARMO', b'ARMA'), MASTERS.index('FalloutNV.esm'))
    addon = as_edid(ours[NEGLIGEE_AA][3], COPY_AA)
    at = next(i for i, (t, _) in enumerate(addon) if t == b'MODL')
    addon[at:at] = [(t, struct.pack('<I', base[e][1])) for t, e in DIRTY_BODY.items()]
    swap = struct.pack('<I', ours[NEGLIGEE_AA][1])
    armor = [(t, struct.pack('<I', own(COPY_AA)) if t == b'MODL' and d == swap else d)
             for t, d in as_edid(ours[NEGLIGEE][3], COPY)]
    out = [('ARMA', pack_fo4_record('ARMA', own(COPY_AA), 0, pack(addon))),
           ('ARMO', pack_fo4_record('ARMO', own(COPY), 0, pack(armor)))]
    armors = {NEGLIGEE: ours[NEGLIGEE][1], COPY: own(COPY), HARNESS: base[HARNESS][1]}
    for name, fid in armors.items():
        body = pack([(b'EDID', f'F3NV_SkinTestOutfit_{name}\0'.encode()), (b'INAM', struct.pack('<I', fid))])
        out.append(('OTFT', pack_fo4_record('OTFT', own('outfit ' + name), 0, body)))
    amari = base[AMARI]
    for row in NPCS:
        subs = npc(amari[3], row, base[DIRTY][1] if row[2] else 0, own('outfit ' + row[3]))
        out.append(('NPC_', pack_fo4_record('NPC_', own(row[0]), amari[2] & ~COMPRESSED, pack(subs))))
    return out


def build(out_dir: Path, nv: Path) -> Path:
    """Write <out_dir>/F3NV_SkinSwapTest.esl from built FalloutNV.esm `nv`; its path."""
    edids = [COPY, COPY_AA, *(f'outfit {n}' for n in (NEGLIGEE, COPY, HARNESS)), *(row[0] for row in NPCS)]
    assert len({object_id(e) for e in edids}) == len(edids), 'object id collision'
    writer = FO4PluginWriter(masters=MASTERS, is_esm=True, is_esl=True, author='fo3fnv-in-fo4',
                             description='Outfit bare skin and the wearer\'s skin: in-game check')
    for sig, rec in records(FALLOUT4_ESM, nv):
        writer.add_record(sig, rec)
    writer.next_object_id = max(map(object_id, edids)) + 1
    out = Path(out_dir) / PLUGIN
    out.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(out))
    return out


def main() -> None:
    """Command line: write the test plugin to --out."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--nv', type=Path, required=True, help='the built FalloutNV.esm')
    parser.add_argument('--out', type=Path, required=True, help='folder for F3NV_SkinSwapTest.esl')
    args = parser.parse_args()
    print(build(args.out, args.nv))


if __name__ == '__main__':
    main()
