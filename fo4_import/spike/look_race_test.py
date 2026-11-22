"""F3NV_LookRaceTest.esl: the in-game check of a raider look race (a HumanRace copy) wearing dirty skin in outfits.

    py -3.14 -m fo4_import.spike.look_race_test --nv <built FalloutNV.esm> --export <FNV export> --out <folder>

F3NV_RaiderRace is HumanRace on its own skin, copies of SkinNakedDirty's addons drawing on it with new texture
sets: FO4's clean body and hands darkened by FNV's raider grime (race_body). FNV's raider armor 04 (converted,
bare arms) is overridden to list an addon on the race ahead of its own: the same models, naming the new body
sets. Two converted raiders, a man and a woman, are copied (same EditorIDs, so the faces stage pairs them with
FNV's) onto the race wearing that armor. Every Fallout4.esm idle conditioned on GetIsRace HumanRace also
accepts the race, and every form list naming HumanRace (the head part lists) names it too.

See: docs/fork/fo4_look_races_plan.md#test-plugin
"""

import argparse
import struct
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.face import hair, race_body
from fo4_import.face.own_facegen import template_tones
from fo4_import.face.texture import dds_like
from fo4_import.face.tint import skin_tone_layers
from fo4_import.nif.outfit import body_fit
from fo4_import.spike.child_race_test import COMPRESSED, addon, armor, object_id, pack, renamed
from fo4_import.spike.fnv_npc import asset
from fo4_import.spike.skin_swap_test import read
from tes5_import.base.tes5_reader import subrecords, walk

PLUGIN, MASTERS = 'F3NV_LookRaceTest.esl', ['Fallout4.esm', 'FalloutHelpers.esl', 'FalloutNV.esm']
RACE, SKIN, OUTFIT = 'F3NV_RaiderRace', 'F3NV_SkinRaiderNaked', 'F3NV_LookRaceTestOutfit'
#: Fallout4.esm's human race, dirty skin and its addons (copied onto the race), and the dirty body textures.
HUMAN, DIRTY = 'HumanRace', 'SkinNakedDirty'
SKIN_ADDONS = {'NakedTorsoDirty': 'F3NV_NakedTorsoRaider', 'NakedHandsDirty': 'F3NV_NakedHandsRaider'}
#: New texture set: (clean set it copies, diffuse darkened; sex, None for hands; FNV raider and stock textures).
SETS = {
    'F3NV_SkinBodyMaleRaider': ('SkinBodyMale_1', 'male',
                                'characters/raider/upperbodymale.dds', 'characters/male/upperbodymale.dds'),
    'F3NV_SkinBodyFemaleRaider': ('SkinBodyFemale_1', 'female', 'characters/raiderfemale/upperbodyfemale.dds',
                                  'characters/female/upperbodyfemale.dds'),
    'F3NV_SkinHandMaleRaider': ('SkinHandMale_1', None, 'characters/raider/handmale.dds',
                                'characters/male/handmale.dds'),
    'F3NV_SkinHandFemaleRaider': ('SkinHandFemale_1', None, 'characters/raiderfemale/handfemale.dds',
                                  'characters/female/handfemale.dds')}
#: The folder under Textures the new diffuses go in.
TEXTURES = 'F3NV\\LookRaceTest'
#: The new sets per addon slot (NAM0 male, NAM1 female): body for the torso and armor addons, hands for hands.
BODY = {b'NAM0': 'F3NV_SkinBodyMaleRaider', b'NAM1': 'F3NV_SkinBodyFemaleRaider'}
HANDS = {b'NAM0': 'F3NV_SkinHandMaleRaider', b'NAM1': 'F3NV_SkinHandFemaleRaider'}
SKIN_SETS = {'NakedTorsoDirty': BODY, 'NakedHandsDirty': HANDS}
#: Skin addon subrecords not copied: its races (MODL) and the male model's swap to the dirty skin material (MO2S).
UNCOPIED = {b'MODL', b'MO2S'}
#: FalloutNV.esm's armor with bare arms, its addon, the race's addon on it, and the raiders put on the race.
ARMOR, ARMOR_AA, RACE_AA = 'FNV_ArmorRaider04', 'FNV_AA_ArmorRaider04', 'F3NV_AA_ArmorRaider04Raider'
RAIDERS = ('FNV_VFSFreesideThugCM02', 'FNV_VFSFreesideResidentAAF03')
#: Condition function GetIsRace, the CTDA flag OR, and record subrecords a raider override drops.
GET_IS_RACE, OR = 69, 0x01
DROPPED = {b'WNAM', b'DOFT'}


def own(edid: str) -> int:
    """The FormID of this plugin's record `edid`."""
    return len(MASTERS) << 24 | object_id(edid)


def fid(data: bytes) -> int:
    """The FormID in 4-byte field `data`."""
    return struct.unpack('<I', data)[0]


def race_or(subs: list, human: int, race: int) -> 'list | None':
    """`subs` with each GetIsRace `human` condition ORed with GetIsRace `race` after it; None when it has none."""
    out, hit = [], False
    for tag, data in subs:
        if tag == b'CTDA' and struct.unpack_from('<H', data, 8)[0] == GET_IS_RACE and fid(data[12:16]) == human:
            hit = True
            out += [(tag, bytes([data[0] | OR]) + data[1:]), (tag, data[:12] + struct.pack('<I', race) + data[16:])]
        else:
            out.append((tag, data))
    return out if hit else None


def vanilla(fo4: bytes, human: int, race: int) -> list:
    """[(signature, record)] overriding each Fallout4.esm IDLE testing GetIsRace `human` and each FLST naming it."""
    out = []
    for rec, _ in walk(fo4, b'IDLE', b'FLST'):
        subs = list(subrecords(rec.body))
        if rec.sig == b'IDLE':
            subs = race_or(subs, human, race)
        elif any(t == b'LNAM' and fid(d) == human for t, d in subs):
            subs = subs + [(b'LNAM', struct.pack('<I', race))]
        else:
            subs = None
        if subs:
            edid = dict(subs).get(b'EDID', b'\0').rstrip(b'\0').decode('cp1252')
            out.append((rec.sig.decode(), pack_fo4_record(rec.sig.decode(), rec.form_id, rec.flags & ~COMPRESSED,
                                                          pack(renamed(subs, edid)))))
    return out


def race_addon(subs: list, edid: str, race: int, body: dict) -> list:
    """Addon `subs` as `edid` on `race` alone, skin textures `body` {tag: TXST}."""
    kept = [(t, struct.pack('<I', race) if t == b'RNAM' else d) for t, d in subs
            if t not in (b'MODL', b'NAM0', b'NAM1')]
    return renamed(kept + [(t, struct.pack('<I', v)) for t, v in body.items()], edid)


def skin_sets(subs: list, sets: dict) -> list:
    """Addon `subs` with its skin textures (NAM0/NAM1) set to `sets` {tag: TXST}."""
    return [(t, struct.pack('<I', sets[t]) if t in sets else d) for t, d in subs]


def texture_set(subs: list, edid: str) -> list:
    """Vanilla TXST `subs` as `edid`, its diffuse (TX00) ours of that name."""
    path = f'{TEXTURES}\\{edid}_d.dds'.encode() + b'\0'
    return renamed([(t, path if t == b'TX00' else d) for t, d in subs], edid)


def diffuse(fo4: Archives, export_dir: Path, base: dict, edid: str) -> bytes:
    """New set `edid`'s diffuse (DDS, its clean set's format and size): the clean diffuse under FNV's raider dirt
    as the sex's tint basis template draws it (race_body.drawn_dirt), carried onto a body, its median on hands."""
    clean_set, sex, race, stock = SETS[edid]
    clean = fo4.read('textures\\' + dict(base[clean_set][3])[b'TX00'].rstrip(b'\0').decode())
    fnv = [hair.image(asset(export_dir, 'textures', p)).astype(float) for p in (race, stock)]
    female = 'Female' in clean_set
    qnam = template_tones(FALLOUT4_ESM.read_bytes(), skin_tone_layers(FALLOUT4_ESM.read_bytes()))[female][0]
    tint = np.array(struct.unpack('<4f', qnam)[:3])
    if sex is None:
        return dds_like(race_body.drawn_dirt(hair.image(clean), race_body.hand_dirt(*fnv, 1.0), 1.0, tint), clean)
    fit = body_fit(export_dir, sex, fo4)
    dirt = race_body.carried(fit, race_body.fnv_body(export_dir, sex, fit), race_body.dirt(*fnv, 1.0))
    return dds_like(race_body.drawn_dirt(hair.image(clean), dirt, 1.0, tint), clean)


def write_textures(out_dir: Path, export_dir: Path, base: dict) -> None:
    """Write every new set's diffuse under <out_dir>/Textures/TEXTURES."""
    fo4 = Archives(FALLOUT4_DIR / 'Data')
    folder = Path(out_dir) / 'Textures' / TEXTURES.replace('\\', '/')
    folder.mkdir(parents=True, exist_ok=True)
    for edid in SETS:
        (folder / f'{edid}_d.dds').write_bytes(diffuse(fo4, export_dir, base, edid))


def with_first_addon(subs: list, aa: int) -> list:
    """ARMO `subs` listing addon `aa` (INDX 0) ahead of its own."""
    at = next(i for i, (t, _) in enumerate(subs) if t == b'INDX')
    return subs[:at] + [(b'INDX', b'\0\0'), (b'MODL', struct.pack('<I', aa))] + subs[at:]


def raider(subs: list, race: int, outfit: int) -> list:
    """Converted raider NPC `subs` on `race` (its race's skin) wearing `outfit`."""
    kept = [(t, struct.pack('<I', race) if t == b'RNAM' else d) for t, d in subs if t not in DROPPED]
    at = next(i for i, (t, _) in enumerate(kept) if t in (b'CRIF', b'FTST', b'QNAM', b'DPLT'))
    return kept[:at] + [(b'DOFT', struct.pack('<I', outfit))] + kept[at:]


def records(fo4: bytes, nv: Path, base: dict) -> list:
    """[(signature, record)]: the race, its skin and texture sets, the armor's race addon and override, the
    outfit, the raiders (own copies) and the vanilla overrides; `base`: Fallout4.esm's records (read)."""
    ours = read(nv, (b'ARMO', b'ARMA', b'NPC_'), MASTERS.index('FalloutNV.esm'))
    race, human = own(RACE), base[HUMAN][1]
    made = [('RACE', own(RACE), base[HUMAN][2],
             [(t, struct.pack('<I', own(SKIN)) if t == b'WNAM' else d) for t, d in renamed(base[HUMAN][3], RACE)])]
    made += [('TXST', own(e), base[s[0]][2], texture_set(base[s[0]][3], e)) for e, s in SETS.items()]
    made += [('ARMA', own(c), base[v][2], skin_sets(addon([(t, d) for t, d in base[v][3] if t not in UNCOPIED], c, [],
                                                          race), {t: own(e) for t, e in SKIN_SETS[v].items()}))
             for v, c in SKIN_ADDONS.items()]
    skin = armor(base[DIRTY][3], SKIN, {base[v][1]: own(c) for v, c in SKIN_ADDONS.items()})
    made.append(('ARMO', own(SKIN), base[DIRTY][2], [(t, struct.pack('<I', race) if t == b'RNAM' else d)
                                                     for t, d in skin]))
    body = {t: own(e) for t, e in BODY.items()}
    made.append(('ARMA', own(RACE_AA), ours[ARMOR_AA][2], race_addon(ours[ARMOR_AA][3], RACE_AA, race, body)))
    made.append(('ARMO', ours[ARMOR][1], ours[ARMOR][2], with_first_addon(ours[ARMOR][3], own(RACE_AA))))
    made.append(('OTFT', own(OUTFIT), 0, [(b'EDID', OUTFIT.encode() + b'\0'),
                                          (b'INAM', struct.pack('<I', ours[ARMOR][1]))]))
    made += [('NPC_', own(n), ours[n][2], raider(ours[n][3], race, own(OUTFIT))) for n in RAIDERS]
    out = [(sig, pack_fo4_record(sig, form, flags & ~COMPRESSED, pack(subs))) for sig, form, flags, subs in made]
    return out + vanilla(fo4, human, race)


def build(out_dir: Path, nv: Path, export_dir: Path) -> Path:
    """Write <out_dir>/F3NV_LookRaceTest.esl from built FalloutNV.esm `nv` and the new diffuses from FNV's export
    `export_dir`; the plugin's path."""
    edids = [RACE, SKIN, OUTFIT, RACE_AA, *SKIN_ADDONS.values(), *SETS, *RAIDERS]
    assert len({object_id(e) for e in edids}) == len(edids), 'object id collision'
    base = read(FALLOUT4_ESM, (b'RACE', b'ARMO', b'ARMA', b'TXST'))
    write_textures(out_dir, export_dir, base)
    writer = FO4PluginWriter(masters=MASTERS, is_esm=True, is_esl=True, author='fo3fnv-in-fo4',
                             description='Raider look race: in-game check')
    for sig, rec in records(FALLOUT4_ESM.read_bytes(), nv, base):
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
    parser.add_argument('--out', type=Path, required=True, help='folder for F3NV_LookRaceTest.esl')
    parser.add_argument('--export', type=Path, required=True, help='the FalloutNV.esm export folder')
    args = parser.parse_args()
    print(build(args.out, args.nv, args.export))


if __name__ == '__main__':
    main()
