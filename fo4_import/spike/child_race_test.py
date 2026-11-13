"""F3NV_ChildRaceTest.esl: the in-game check of a child race on the player, mastering Fallout4.esm only.

    py -3.14 -m fo4_import.spike.child_race_test --out D:/scratch/child_race_test

Two copies of HumanChildRace: F3NV_PlayerChildRace without tint templates and with HumanRace's face morph
regions (as PowerArmorRace has), and F3NV_PlayerChildRaceTints, a plain copy. Both wear a copy of the child skin
and take a Pip-Boy addon and a child vault suit drawing on them; the vanilla Pip-Boy is overridden to list the
addon. Object ids come from the EditorIDs.

See: docs/fork/fo4_fo3_child_player.md#spike-test
"""

import argparse
import struct
import zlib
from pathlib import Path

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.strings import as_text
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

PLUGIN, MASTERS = 'F3NV_ChildRaceTest.esl', ['Fallout4.esm']
RACE, TINTED = 'F3NV_PlayerChildRace', 'F3NV_PlayerChildRaceTints'
NAMES = {RACE: 'Player Child (no tints)', TINTED: 'Player Child (tints)'}
SKIN, PIPBOY_AA, SUIT = 'F3NV_SkinChildNaked', 'F3NV_PipboyChildAA', 'F3NV_ChildRaceTestVaultSuit'
#: Fallout4.esm EditorID -> its copy's EditorID (ARMA and ARMO the races wear or carry).
COPIES = {'NakedChildTorso': 'F3NV_NakedChildTorso', 'NakedChildHands': 'F3NV_NakedChildHands',
          'AAVault81SuitChild': 'F3NV_Vault81SuitChildAA', 'PipboyAA': PIPBOY_AA,
          'SkinChildNaked': SKIN, 'Armor_Vault81_UnderwearChild': SUIT}
CHILD_RACE, HUMAN_RACE, PIPBOY = 'HumanChildRace', 'HumanRace', 'Pipboy'
#: A RACE's tint template subrecords, and its face morph regions.
TINTS = {b'TINL', b'TTGP', b'TETI', b'TTEF', b'TTET', b'TTEC', b'TTED', b'TTEB', b'TTGE', b'CTDA'}
REGIONS = {b'FMRI', b'FMRN'}
#: A RACE's per-sex head data subrecords (after its NAM0), and the localized ones in it.
HEAD_DATA = TINTS | REGIONS | {b'NAM0', b'MNAM', b'FNAM', b'NNAM', b'INDX', b'HEAD', b'RPRM', b'RPRF', b'AHCM',
                               b'AHCF', b'FTSM', b'FTSF', b'DFTM', b'DFTF', b'MPGN', b'MPPC', b'MPPI', b'MPPN',
                               b'MPPM', b'MPPT', b'MPPF', b'MPPK', b'MPGS'}
LOCALIZED = (b'FULL', b'DESC', b'TTGP', b'MPPN', b'FMRN')
#: ARMA subrecords that follow its additional races (MODL).
AFTER_RACES = (b'SNDD', b'ONAM', b'BSMP', b'BSMB', b'BSMS')
#: Light plugin object ids, and the record flag Compressed (a copy is written raw).
LIGHT_IDS, COMPRESSED = (0x800, 0x1000), 0x40000


def object_id(edid: str) -> int:
    """`edid`'s object id in the light range, from its CRC-32."""
    low, high = LIGHT_IDS
    return low + zlib.crc32(edid.encode()) % (high - low)


def own(edid: str) -> int:
    """The FormID of this plugin's record `edid`."""
    return len(MASTERS) << 24 | object_id(edid)


def sections(subs: list) -> list:
    """`subs` cut into [top, male head data, female head data, rest] at the head data's NAM0s."""
    out, part = [[], [], [], []], 0
    for tag, data in subs:
        part = part + 1 if tag == b'NAM0' else 3 if part == 2 and tag not in HEAD_DATA else part
        out[part].append((tag, data))
    return out


def child_race(child: list, human: list, edid: str, tints: bool) -> list:
    """HumanChildRace's subrecords as `edid` wearing SKIN: its tints kept when `tints`, else dropped and HumanRace's
    face morph regions added to each sex's head data."""
    parts = sections(child)
    if not tints:
        theirs = sections(human)
        for sex in (1, 2):
            parts[sex] = [s for s in parts[sex] if s[0] not in TINTS] + [s for s in theirs[sex] if s[0] in REGIONS]
        parts[0] = [s for s in parts[0] if s[0] != b'TINL']
    subs = [(tag, struct.pack('<I', own(SKIN)) if tag == b'WNAM' else data) for tag, data in sum(parts, [])]
    return [(t, NAMES[edid].encode() + b'\0' if t == b'FULL' else d) for t, d in renamed(subs, edid)]


def renamed(subs: list, edid: str) -> list:
    """`subs` as record `edid`, with its string IDs as text."""
    return [(tag, edid.encode() + b'\0' if tag == b'EDID' else as_text(tag, data, LOCALIZED)) for tag, data in subs]


def addon(subs: list, edid: str, races: list, primary: 'int | None' = None) -> list:
    """ARMA `subs` as `edid` also drawing on `races` (its primary race `primary` when given)."""
    extra = [(b'MODL', struct.pack('<I', race)) for race in races]
    at = next((i for i, (tag, _) in enumerate(subs) if tag in AFTER_RACES), len(subs))
    subs = subs[:at] + extra + subs[at:]
    return renamed([(t, struct.pack('<I', primary) if t == b'RNAM' and primary else d) for t, d in subs], edid)


def armor(subs: list, edid: str, addons: dict) -> list:
    """ARMO `subs` as `edid`, its addons (MODL) mapped by `addons`."""
    swap = lambda d: struct.pack('<I', addons.get(struct.unpack('<I', d)[0], struct.unpack('<I', d)[0]))
    return renamed([(t, swap(d) if t == b'MODL' else d) for t, d in subs], edid)


def pipboy(subs: list, ours: int) -> list:
    """The vanilla Pip-Boy's subrecords with addon `ours` listed after its own."""
    at = max(i for i, (tag, _) in enumerate(subs) if tag == b'MODL') + 1
    index = next(d for t, d in subs if t == b'INDX')
    return subs[:at] + [(b'INDX', index), (b'MODL', struct.pack('<I', ours))] + subs[at:]


def fallout4_records(fo4: bytes) -> dict:
    """{EditorID: (signature, FormID, flags, [(tag, data)])} of the Fallout4.esm records the plugin copies."""
    want, out = set(COPIES) | {CHILD_RACE, HUMAN_RACE, PIPBOY}, {}
    for rec, _ in walk(fo4, b'RACE', b'ARMA', b'ARMO'):
        subs = list(subrecords(rec.body))
        edid = dict(subs).get(b'EDID', b'').rstrip(b'\0').decode('cp1252')
        if edid in want:
            out[edid] = (rec.sig.decode(), rec.form_id, rec.flags & ~COMPRESSED, subs)
    return out


def records(fo4: bytes) -> list:
    """[(signature, record)]: the two races, the skin, Pip-Boy and suit copies, and the Pip-Boy override."""
    src = fallout4_records(fo4)
    races = [own(RACE), own(TINTED)]
    sub = lambda edid: src[edid][3]
    addons = {src[e][1]: own(c) for e, c in COPIES.items() if src[e][0] == 'ARMA'}
    made = {RACE: child_race(sub(CHILD_RACE), sub(HUMAN_RACE), RACE, False),
            TINTED: child_race(sub(CHILD_RACE), sub(HUMAN_RACE), TINTED, True),
            PIPBOY_AA: addon([(t, d) for t, d in sub('PipboyAA') if t != b'MODL'], PIPBOY_AA, races[1:], races[0])}
    for theirs, ours in COPIES.items():
        if ours not in made:
            made[ours] = (addon(sub(theirs), ours, races) if src[theirs][0] == 'ARMA'
                          else armor(sub(theirs), ours, addons))
    out = [(src[t][0], pack_fo4_record(src[t][0], own(e), src[t][2], _pack(made[e])))
           for t, e in [(CHILD_RACE, RACE), (CHILD_RACE, TINTED)] + list(COPIES.items())]
    sig, fid, flags, subs = src[PIPBOY]
    return out + [(sig, pack_fo4_record(sig, fid, flags, _pack(renamed(pipboy(subs, own(PIPBOY_AA)), PIPBOY))))]


def _pack(subs: list) -> bytes:
    """Subrecords as bytes."""
    return b''.join(pack_subrecord(tag.decode(), data) for tag, data in subs)


def build(out_dir: Path, fo4: bytes = None) -> Path:
    """Write <out_dir>/F3NV_ChildRaceTest.esl; its path. `fo4` is Fallout4.esm's bytes (read when None)."""
    edids = [RACE, TINTED, *COPIES.values()]
    assert len({object_id(e) for e in edids}) == len(edids), 'object id collision'
    writer = FO4PluginWriter(masters=MASTERS, is_esm=True, is_esl=True, author='fo3fnv-in-fo4',
                             description='Child race on the player: in-game check')
    for sig, rec in records(fo4 or FALLOUT4_ESM.read_bytes()):
        writer.add_record(sig, rec)
    writer.next_object_id = max(map(object_id, edids)) + 1
    out = Path(out_dir) / PLUGIN
    out.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(out))
    return out


def main() -> None:
    """Command line: write the test plugin to --out."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True, help='folder for F3NV_ChildRaceTest.esl')
    print(build(parser.parse_args().out))


if __name__ == '__main__':
    main()
