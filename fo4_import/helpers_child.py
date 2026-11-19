"""FalloutHelpers.esl's child race for the player (FO3's AgeRace), and the addons that draw on it.

F3NV_PlayerChildRace is HumanChildRace without tint templates and with HumanRace's face morph regions, as
PowerArmorRace has (vanilla swaps the player to it and back). Vanilla names every race an addon draws on (408 of
HumanRace's 443 addons list GhoulRace), so each Fallout4.esm addon drawing on HumanChildRace (the child skin, suit,
clothes) is overridden to list the new race too. F3NV_PipboyChildAA is PipboyAA on it, listed on the vanilla Pip-Boy.

See: docs/fork/fo4_fo3_child_player.md#built
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import child_race_test as T
from fo4_import.spike.child_race_test import CHILD_RACE, COMPRESSED, HUMAN_RACE, PIPBOY, PIPBOY_AA, RACE
from script_convert.constants import FALLOUT4_HELPER_CHILD_PIPBOY, FALLOUT4_HELPER_CHILD_RACE
from tes5_import.base.tes5_reader import subrecords, walk


def addon_races(subs: list) -> set:
    """The races an ARMA draws on: its race (RNAM) and additional races (MODL FormIDs)."""
    return {struct.unpack('<I', d)[0] for t, d in subs if t in (b'RNAM', b'MODL') and len(d) == 4}


def child_addons(fo4: bytes, child: int, race: int) -> list:
    """[(signature, record)] overriding each Fallout4.esm ARMA that draws on `child` to also draw on `race`."""
    out = []
    for rec, _ in walk(fo4, b'ARMA'):
        subs = list(subrecords(rec.body))
        if child in addon_races(subs):
            edid = dict(subs)[b'EDID'].rstrip(b'\0').decode('cp1252')
            out.append(('ARMA', pack_fo4_record('ARMA', rec.form_id, rec.flags & ~COMPRESSED,
                                                T.pack(T.addon(subs, edid, [race])))))
    return out


def child_records(fo4: bytes, own_id) -> list:
    """[(signature, record)]: the child race, its Pip-Boy addon, the vanilla Pip-Boy listing it, and the child
    addons (child_addons); `own_id` maps an object id to its FormID in the helper plugin."""
    src = T.fallout4_records(fo4)
    race, addon = own_id(FALLOUT4_HELPER_CHILD_RACE), own_id(FALLOUT4_HELPER_CHILD_PIPBOY)
    child = src[CHILD_RACE]
    skin = struct.unpack('<I', dict(child[3])[b'WNAM'])[0]
    made = T.child_race(child[3], src[HUMAN_RACE][3], RACE, False, skin)
    pip_aa = T.addon([(t, d) for t, d in src['PipboyAA'][3] if t != b'MODL'], PIPBOY_AA, [], race)
    sig, fid, flags, subs = src[PIPBOY]
    return [('RACE', pack_fo4_record('RACE', race, child[2], T.pack(made))),
            ('ARMA', pack_fo4_record('ARMA', addon, src['PipboyAA'][2], T.pack(pip_aa))),
            (sig, pack_fo4_record(sig, fid, flags, T.pack(T.renamed(T.pipboy(subs, addon), PIPBOY)))),
            *child_addons(fo4, child[1], race)]
