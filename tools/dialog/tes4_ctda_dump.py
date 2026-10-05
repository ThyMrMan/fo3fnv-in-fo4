#!/usr/bin/env python3
"""Dump decoded TES4 / FO3 / FNV CTDA conditions from the text export.

Usage:
    python tools/dialog/tes4_ctda_dump.py --dial Recommendation          # all INFOs of a topic
    python tools/dialog/tes4_ctda_dump.py --dial 00007B2F --export export/Knights.esp
    python tools/dialog/tes4_ctda_dump.py --quest MG00Join               # QUST's own conditions
    python tools/dialog/tes4_ctda_dump.py --info 0001C0E3                # one INFO
    python tools/dialog/tes4_ctda_dump.py --names fnv --export export/FalloutNV.esm --npc DocMitchell

Decodes each Condition[i].Raw: operator, comparison value, function
(by name), params (resolved to EditorIDs where possible), flags. --names reads
a Fallout game's function names and parameter types from xEdit's
wbDefinitions<GAME>.pas; the default is the built-in Oblivion table. --npc
lists every topic and line an NPC speaks (a GetIsID condition on it), with
prompts, responses, flags, choices and added topics.
"""
import argparse
import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from tes5_import.base.text_reader import parse_export_file
from tools.generators.gen_ctda_param_types import formid_types, parse_enum, parse_functions

#: TES4 condition function names (wbDefinitionsTES4.pas, the dialogue ones); others print as Func<N>.
FUNC_NAMES = {
    1: 'GetDistance', 5: 'GetLocked', 6: 'GetPos', 8: 'GetAngle',
    10: 'GetStartingPos', 12: 'GetSecondsPassed', 14: 'GetActorValue',
    18: 'GetCurrentTime', 24: 'GetScale', 27: 'GetLineOfSight',
    32: 'GetInSameCell', 35: 'GetDisabled', 36: 'MenuMode', 39: 'GetDisease',
    40: 'GetVampire', 41: 'GetClothingValue', 42: 'SameFaction',
    43: 'SameRace', 44: 'SameSex', 45: 'GetDetected', 46: 'GetDead',
    47: 'GetItemCount', 48: 'GetGold', 49: 'GetSleeping',
    50: 'GetTalkedToPC', 53: 'GetScriptVariable', 56: 'GetQuestRunning',
    58: 'GetStage', 59: 'GetStageDone', 60: 'GetFactionRankDifference',
    61: 'GetAlarmed', 62: 'IsRaining', 63: 'GetAttacked', 64: 'GetIsCreature',
    65: 'GetLockLevel', 66: 'GetShouldAttack', 67: 'GetInCell',
    68: 'GetIsClass', 69: 'GetIsRace', 70: 'GetIsSex', 71: 'GetInFaction',
    72: 'GetIsID', 73: 'GetFactionRank', 74: 'GetGlobalValue',
    75: 'IsSnowing', 76: 'GetDisposition', 77: 'GetRandomPercent',
    79: 'GetQuestVariable', 80: 'GetLevel', 81: 'GetArmorRating',
    84: 'GetDeadCount', 91: 'GetIsAlerted', 98: 'GetPlayerControlsDisabled',
    99: 'GetQuestCompleted', 101: 'IsWeaponOut', 102: 'IsTorchOut',
    103: 'IsShieldOut', 106: 'IsFacingUp', 107: 'GetKnockedState',
    108: 'GetWeaponAnimType', 109: 'GetWeaponSkillType',
    110: 'GetCurrentAIPackage', 111: 'IsWaiting', 112: 'IsIdlePlaying',
    116: 'GetCrimeGold', 122: 'GetCrime', 125: 'GetIsPlayableRace',
    126: 'GetOffersServicesNow', 127: 'CanPayCrimeGold',
    128: 'GetFatiguePercentage', 129: 'GetPCIsRace', 130: 'GetPCIsSex',
    131: 'GetPCInFaction', 132: 'SameFactionAsPC', 133: 'SameRaceAsPC',
    134: 'SameSexAsPC', 135: 'GetIsReference', 136: 'IsTalking',
    138: 'GetTimeDead', 139: 'GetPlayerTeammate', 149: 'GetCadence',
    153: 'IsSwimming', 161: 'GetWindSpeed', 163: 'GetCurrentAIProcedure',
    166: 'IsWeaponSkillType?', 167: 'GetInCellParam', 169: 'CanHaveFlames',
    170: 'HasFlames', 171: 'IsPlayerInJail', 172: 'GetTalkedToPCParam',
    175: 'GetPCSleepHours', 176: 'SameCell', 180: 'GetIsUsedItemType',
    182: 'GetEquipped', 185: 'IsSneaking', 186: 'IsRunning',
    189: 'GetFriendHit', 190: 'IsInCombat', 193: 'GetPCExpelled',
    195: 'GetPCFactionMurder', 197: 'GetPCEnemyofFaction',
    199: 'GetPCFactionAttack', 201: 'GetPCFactionSubmitAuthority',
    203: 'GetDestroyed', 214: 'HasMagicEffect', 215: 'GetDefaultOpen',
    223: 'IsSpellTarget', 224: 'GetIsPlayerBirthsign',
    225: 'GetPersuasionNumber', 227: 'HasVampireFed', 228: 'GetIsClassDefault',
    229: 'GetClassDefaultMatch', 230: 'GetInCellParam',
    237: 'GetIsGhost', 242: 'GetUnconscious', 244: 'GetRestrained',
    246: 'GetIsUsedItem', 247: 'GetIsUsedItemEquipType', 249: 'GetPCFame',
    251: 'GetPCInfamy', 254: 'GetIsPlayerGrabbedRef', 258: 'IsCarryable',
    259: 'GetConcussed', 264: 'GetBarterGold', 265: 'IsTimePassing',
    266: 'IsPleasant', 267: 'IsCloudy', 274: 'GetArmorRatingUpperBody',
    277: 'GetBaseActorValue', 278: 'IsOwner', 280: 'IsCellOwner',
    282: 'IsHorseStolen', 285: 'IsLeftUp', 286: 'IsSneakingParam?',
    305: 'GetInWorldspace', 306: 'GetPCMiscStat', 309: 'GetWalkSpeed',
    310: 'GetCurrentAIProcedure', 312: 'GetIsFlying', 313: 'IsFlying',
    323: 'GetIgnoreFriendlyHits', 327: 'IsPlayerLastRiddenHorse',
    329: 'GetIsInList?', 332: 'GetIsUsedItemType',
    353: 'IsActor', 354: 'IsEssential', 358: 'GetPlayerMovingIntoNewSpace',
    361: 'GetTimeDead', 362: 'GetPlayerHasLastRiddenHorse', 365: 'IsChild',
}

_OPS = {0x00: '==', 0x20: '!=', 0x40: '>', 0x60: '>=', 0x80: '<', 0xA0: '<='}

#: Oblivion functions whose param1 is a literal int/enum, not a FormID.
_NON_FORM_P1 = {14, 18, 36, 47, 50, 77, 80, 108, 109, 110, 125, 128, 130,
                163, 175, 225, 277, 306, 309}
#: Oblivion functions whose param1 prints even when it is 0.
_ALWAYS_P1 = (72, 71, 58, 59, 56, 79, 53, 74, 67, 68, 69, 73)
#: --names value -> xEdit definitions file.
_XEDIT_DEFS = {'fo3': 'wbDefinitionsFO3.pas', 'fnv': 'wbDefinitionsFNV.pas',
               'fo4': 'wbDefinitionsFO4.pas'}
#: FO3/FNV INFO DATA flag bits (wbDefinitionsFNV.pas: Flags 1, then Flags 2).
_INFO_FLAGS = ('Goodbye', 'Random', 'SayOnce', 'RunImmediately', 'InfoRefusal',
               'RandomEnd', 'RunForRumors', 'SpeechChallenge')
_INFO_FLAGS2 = ('SayOnceADay', 'AlwaysDarken', '', '', 'LowInt', 'HighInt')
#: FO3/FNV CTDA Run On values (bytes 20-23 of the 28-byte form).
_RUN_ON = ('Subject', 'Target', 'Reference', 'CombatTarget', 'LinkedRef')
#: FO3/FNV DIAL types.
_DIAL_TYPES = ('Topic', 'Conversation', 'Combat', 'Persuasion', 'Detection',
               'Service', 'Misc', 'Radio')


class FuncTable:
    """Condition function names and which params are FormIDs, for one game."""

    def __init__(self, names: dict, form_slots: dict = None):
        """form_slots: {func: {slot,...}} from xEdit; None keeps the Oblivion heuristics."""
        self.names = names
        self.form_slots = form_slots

    def name(self, func: int) -> str:
        """The function's name, or Func<N>."""
        return self.names.get(func, f'Func{func}')

    def index(self, name: str) -> int:
        """The index of a function by name, or -1."""
        return next((i for i, n in self.names.items() if n == name), -1)

    def args(self, func: int, p1: int, p2: int, idx: dict) -> list:
        """Formatted params: FormIDs resolved to EditorIDs, values as ints."""
        if self.form_slots is None:
            args = []
            if p1 or func in _ALWAYS_P1:
                args.append(fmt_fid(p1, idx) if func not in _NON_FORM_P1 else str(p1))
            if p2:
                args.append(fmt_fid(p2, idx) if p2 > 0xFFFF else str(p2))
            return args
        slots = self.form_slots.get(func, set())
        return [fmt_fid(p, idx) if slot in slots else str(p)
                for slot, p in ((1, p1), (2, p2)) if p or slot in slots]


def xedit_table(game: str) -> FuncTable:
    """FuncTable read from xEdit's definitions for fo3, fnv or fo4."""
    text = (_ROOT / 'references' / 'xEdit' / 'Core' / _XEDIT_DEFS[game]).read_text(
        encoding='utf-8', errors='replace')
    form_types = formid_types(parse_enum(text))
    funcs = parse_functions(text)
    return FuncTable({i: name for i, (name, _) in funcs.items()},
                     {i: {s for s, t in params.items() if t in form_types}
                      for i, (_, params) in funcs.items()})


OBLIVION = FuncTable(FUNC_NAMES)


def build_fid_index(export_dir: Path) -> dict:
    """FormID(hex str) -> 'EDID (SIG)' from every export file present."""
    idx = {}
    for txt in export_dir.glob('*.txt'):
        try:
            for rec in parse_export_file(str(txt)):
                fid = rec.get('FormID')
                if fid:
                    idx[fid.upper()] = (f"{rec.get('EditorID', '?') or '?'}"
                                        f" ({rec.get('Signature', txt.stem)})")
        except Exception:
            continue
    return idx


def fmt_fid(v: int, idx: dict) -> str:
    """A FormID with its EditorID and signature when known."""
    h = f'{v:08X}'
    name = idx.get(h)
    return f'{h}[{name}]' if name else h


def unpack(raw_hex: str) -> tuple:
    """(type byte, comparison float, comparison int, function, param1, param2)."""
    raw = bytes.fromhex(raw_hex)
    raw = raw + b'\0' * max(0, 24 - len(raw))
    return (raw[0], struct.unpack_from('<f', raw, 4)[0]) + struct.unpack_from('<IIII', raw, 4)


def _run_on(raw_hex: str, idx: dict) -> list:
    """FO3/FNV's 28-byte conditions: the Run On target when it isn't Subject."""
    raw = bytes.fromhex(raw_hex)
    if len(raw) < 28 or not (run_on := struct.unpack_from('<I', raw, 20)[0]):
        return []
    label = _RUN_ON[run_on] if run_on < len(_RUN_ON) else str(run_on)
    ref = struct.unpack_from('<I', raw, 24)[0]
    return [f'RunOn={label}' + (f':{fmt_fid(ref, idx)}' if run_on == 2 else '')]


def decode(raw_hex: str, idx: dict, table: FuncTable = OBLIVION) -> str:
    """One condition as 'Func(args) op value   [flags]'."""
    t, comp_f, comp_i, func, p1, p2 = unpack(raw_hex)
    op = _OPS.get(t & 0xE0, f'op{t >> 5}')
    flags = [label for bit, label in ((0x01, 'OR'), (0x02, 'RunOnTarget'), (0x04, 'UseGlobal'))
             if t & bit] + _run_on(raw_hex, idx)
    comp = (fmt_fid(comp_i, idx) if t & 0x04 else f'{comp_f:g}')
    text = f'{table.name(func)}({", ".join(table.args(func, p1, p2, idx))}) {op} {comp}'
    return text + (('   [' + ','.join(flags) + ']') if flags else '')


def dump_rec(rec: dict, idx: dict, prefix: str = '', table: FuncTable = OBLIVION):
    """Print a record's decoded conditions, one per line."""
    i = 0
    while True:
        raw_hex = rec.get(f'{prefix}Condition[{i}].Raw')
        if raw_hex is None:
            break
        try:
            print(f'    C{i}: {decode(raw_hex, idx, table)}')
        except Exception as e:
            print(f'    C{i}: <decode error {e}> {raw_hex}')
        i += 1


def _matches(rec: dict, want: str) -> bool:
    """True when want (upper case) is the record's EditorID or FormID."""
    return (rec.get('EditorID', '').upper() == want
            or rec.get('FormID', '').upper() == want.zfill(8))


def _first_line(script: str) -> str:
    """A result script's first line."""
    return script.split('\r\n')[0]


def show_dial(export_dir: Path, want: str, idx: dict, table: FuncTable):
    """--dial: a topic and every INFO under it."""
    dial_fid = None
    for d in parse_export_file(str(export_dir / 'DIAL.txt')):
        if _matches(d, want):
            dial_fid = d.get('FormID')
            print(f"DIAL {d.get('EditorID')} ({dial_fid}) "
                  f"FULL='{d.get('FULL', '')}' Type={d.get('DATA.Type')} "
                  f"quests={[d.get(f'Quest[{i}]') for i in range(int(d.get('QuestCount', 0) or 0))]}")
            break
    if not dial_fid:
        sys.exit(f'DIAL {want} not found')
    for rec in parse_export_file(str(export_dir / 'INFO.txt')):
        if rec.get('ParentDIAL') != dial_fid:
            continue
        print(f"\n  INFO {rec.get('FormID')} quest={fmt_fid(int(rec.get('QSTI.Quest', '0') or '0', 16), idx)} "
              f"flags={rec.get('DATA.Flags')}")
        print(f"    \"{rec.get('Response[0].ResponseText', '')[:100]}\"")
        dump_rec(rec, idx, table=table)
        if rec.get('ResultScript'):
            print(f"    Result: {_first_line(rec['ResultScript'])} ...")


def show_info(export_dir: Path, want: str, idx: dict, table: FuncTable):
    """--info: one INFO's text, conditions and result script."""
    want = want.zfill(8)
    for rec in parse_export_file(str(export_dir / 'INFO.txt')):
        if rec.get('FormID', '').upper() == want:
            print(f"INFO {want} dial={rec.get('ParentDIAL')} "
                  f"quest={rec.get('QSTI.Quest')}")
            print(f"  \"{rec.get('Response[0].ResponseText', '')[:120]}\"")
            dump_rec(rec, idx, table=table)
            if rec.get('ResultScript'):
                print('  Result: ' + rec['ResultScript'][:300])


def show_quest(export_dir: Path, want: str, idx: dict, table: FuncTable):
    """--quest: a quest's own conditions and its targets'."""
    for rec in parse_export_file(str(export_dir / 'QUST.txt')):
        if not _matches(rec, want):
            continue
        print(f"QUST {rec.get('EditorID')} ({rec.get('FormID')}) "
              f"flags={rec.get('DATA.Flags')} priority={rec.get('DATA.Priority')} "
              f"SCRI={rec.get('SCRI', '-')}")
        dump_rec(rec, idx, table=table)
        t = 0
        while rec.get(f'Target[{t}].FormID') is not None:
            print(f"  Target[{t}] -> {fmt_fid(int(rec.get(f'Target[{t}].FormID', '0') or '0', 16), idx)}")
            dump_rec(rec, idx, prefix=f'Target[{t}].', table=table)
            t += 1


def _find_npc(export_dir: Path, want: str) -> int:
    """The FormID of an NPC_ or CREA by EditorID or FormID."""
    for sig in ('NPC_', 'CREA'):
        path = export_dir / f'{sig}.txt'
        if path.exists():
            for rec in parse_export_file(str(path)):
                if _matches(rec, want):
                    return int(rec['FormID'], 16)
    sys.exit(f'NPC {want} not found')


def _speaks(rec: dict, npc: int, getisid: int) -> bool:
    """True when an INFO has a GetIsID(npc) == 1 condition."""
    i = 0
    while (raw := rec.get(f'Condition[{i}].Raw')) is not None:
        t, comp_f, _, func, p1, _ = unpack(raw)
        if func == getisid and p1 == npc and t & 0xE0 == 0 and comp_f == 1.0:
            return True
        i += 1
    return False


def _flag_names(rec: dict) -> str:
    """The INFO's DATA flags as names."""
    names = [n for b, n in enumerate(_INFO_FLAGS) if int(rec.get('DATA.Flags', 0) or 0) >> b & 1]
    names += [n for b, n in enumerate(_INFO_FLAGS2) if n and int(rec.get('DATA.Flags2', 0) or 0) >> b & 1]
    return ','.join(names) or '-'


def _fid_list(rec: dict, key: str, idx: dict) -> list:
    """A Key[i] FormID list, resolved."""
    return [fmt_fid(int(rec[f'{key}[{i}]'], 16), idx)
            for i in range(int(rec.get(f'{key}Count', 0) or 0))]


def _print_npc_info(rec: dict, idx: dict, table: FuncTable):
    """One INFO in the --npc view."""
    print(f"\n  INFO {rec.get('FormID')} flags={_flag_names(rec)} "
          f"next={rec.get('DATA.NextSpeaker')} quest={fmt_fid(int(rec.get('QSTI.Quest', '0') or '0', 16), idx)}")
    if rec.get('Prompt'):
        print(f"    Prompt: \"{rec['Prompt']}\"")
    for r in range(int(rec.get('ResponseCount', 0) or 0)):
        print(f"    R{r}: \"{rec.get(f'Response[{r}].ResponseText', '')}\"")
    dump_rec(rec, idx, table=table)
    for key in ('Choice', 'AddTopic', 'LinkFrom'):
        for fid in _fid_list(rec, key, idx):
            print(f'    {key}: {fid}')
    for key in ('ResultScript', 'ResultScriptEnd'):
        if rec.get(key):
            print(f'    {key}: {_first_line(rec[key])} ...')


def show_npc(export_dir: Path, want: str, idx: dict, table: FuncTable):
    """--npc: every topic with a line the NPC speaks, in export order."""
    npc = _find_npc(export_dir, want)
    getisid = table.index('GetIsID')
    by_dial = {}
    for rec in parse_export_file(str(export_dir / 'INFO.txt')):
        if _speaks(rec, npc, getisid):
            by_dial.setdefault(rec.get('ParentDIAL'), []).append(rec)
    dials = {d.get('FormID'): d for d in parse_export_file(str(export_dir / 'DIAL.txt'))}
    print(f'{fmt_fid(npc, idx)}: {sum(map(len, by_dial.values()))} lines in {len(by_dial)} topics')
    for dial_fid, infos in by_dial.items():
        d = dials.get(dial_fid, {})
        kind = int(d.get('DATA.Type', -1) or -1)
        print(f"\nDIAL {d.get('EditorID')} ({dial_fid}) "
              f"type={_DIAL_TYPES[kind] if 0 <= kind < 8 else kind} FULL='{d.get('FULL', '')}'")
        for rec in infos:
            _print_npc_info(rec, idx, table)


def main():
    """Parse the command line and run each requested view."""
    ap = argparse.ArgumentParser(description='Decode TES4/FO3/FNV CTDA conditions')
    ap.add_argument('--export', default=str(_ROOT / 'export' / 'Oblivion.esm'))
    ap.add_argument('--names', choices=sorted(_XEDIT_DEFS),
                    help='Read function names from xEdit for this game (default: built-in Oblivion)')
    ap.add_argument('--dial', help='DIAL EditorID or FormID: dump all its INFOs')
    ap.add_argument('--info', help='One INFO FormID')
    ap.add_argument('--quest', help='QUST EditorID or FormID (own conditions + targets)')
    ap.add_argument('--npc', help='NPC_/CREA EditorID or FormID: every topic and line it speaks')
    args = ap.parse_args()

    export_dir = Path(args.export)
    table = xedit_table(args.names) if args.names else OBLIVION
    print('Indexing EditorIDs...', file=sys.stderr)
    idx = build_fid_index(export_dir)
    views = ((args.dial, show_dial), (args.info, show_info),
             (args.quest, show_quest), (args.npc, show_npc))
    for want, view in views:
        if want:
            view(export_dir, want.upper(), idx, table)


if __name__ == '__main__':
    main()
