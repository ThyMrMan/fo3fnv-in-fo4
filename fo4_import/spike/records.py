"""FO4 record packers for the dialogue spike, laid out from xEdit's wbDefinitionsFO4.pas.

Values xEdit cannot give (topic categories, subtype codes, scene action flags)
are copied from vanilla Fallout4.esm records named in each docstring.

See: docs/fork/fo4_spikes.md#spike-1
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.writer import pack_group, pack_string_subrecord, pack_subrecord

NO_STAGE = 0xFFFF
#: FO4 CTDA Run On values.
RUN_SUBJECT, RUN_TARGET, RUN_REFERENCE = 0, 1, 2
#: INFO ENAM flag bits (wbDefinitionsFO4.pas INFO 'Response flags'). Random is never written: see dialogue.random_chain.
INFO_SAY_ONCE, INFO_END_SCENE = 0x0004, 0x0040
#: DIAL DATA + SNAM. Scene topics: DialogueDiamondCity 001994FB; greetings: 000A7D2D.
TOPIC_SCENE = (bytes([0, 2, 0x10, 0]), b'SCEN')
TOPIC_GREETING = (bytes([0, 7, 0x74, 0]), b'GREE')
#: Player Dialogue action FNAM from CookeGreetScene 0003A63D: face target, headtrack, camera on speaker.
PLAYER_DIALOGUE_FLAGS = 0x228800
#: SCEN FNAM from CookeGreetScene: show all text, has player dialogue, no follower chatter.
SCENE_FLAGS = 0x1024
#: SCEN ACTV (Dialogue Distance Override); the menu scene also ends past it, as 127 vanilla phases end on GetDistance.
DIALOGUE_DISTANCE = 500.0
RUN_QUEST_ALIAS = 5
OP_GREATER = 0x40
FUNC_GET_DISTANCE = 1
PLAYER = 0x14


def _u32(sig: str, value: int) -> bytes:
    """A 4-byte unsigned subrecord."""
    return pack_subrecord(sig, struct.pack('<I', value & 0xFFFFFFFF))


def _s32(sig: str, value: int) -> bytes:
    """A 4-byte signed subrecord."""
    return pack_subrecord(sig, struct.pack('<i', value))


def _zstr(sig: str, text: str) -> bytes:
    """A null-terminated cp1252 string subrecord."""
    return pack_string_subrecord(sig, text)


def pack_ctda(op_flags: int, value: float, func: int, p1: int = 0, p2: int = 0,
              run_on: int = RUN_SUBJECT, ref: int = 0, param3: int = -1) -> bytes:
    """One FO4 condition (32 bytes; u16 function; param3 is the alias id when run on a quest alias)."""
    data = struct.pack('<B3xfH2xIIIIi', op_flags, value, func, p1, p2, run_on, ref, param3)
    return pack_subrecord('CTDA', data)


def pack_dial(fid: int, edid: str, quest: int, kind: tuple, info_count: int) -> bytes:
    """A topic: priority 50, its quest, DATA and subtype code from `kind`, and its INFO count."""
    data, code = kind
    subs = _zstr('EDID', edid) + pack_subrecord('PNAM', struct.pack('<f', 50.0))
    subs += _u32('QNAM', quest) + pack_subrecord('DATA', data) + pack_subrecord('SNAM', code)
    subs += _u32('TIFC', info_count)
    return pack_fo4_record('DIAL', fid, 0, subs)


def pack_info(fid: int, flags: int = 0, lines: tuple = (), conditions: bytes = b'',
              prompt: str = '', scene: int = 0, phase: str = '',
              stages: tuple = (NO_STAGE, NO_STAGE), notes: str = '', forced_alias: int = None,
              vmad: bytes = b'') -> bytes:
    """An INFO in vanilla's field order (DialogueDiamondCity 00199516).

    lines are response texts (none: an empty padding INFO); stages are the
    quest stages set on begin and on end (TIQS); scene/phase start a scene;
    forced_alias (ALFA) puts the speaker into that alias; vmad is its fragments.
    """
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + pack_subrecord('ENAM', struct.pack('<HH', flags, 0))
    for number, text in enumerate(lines, 1):
        subs += pack_subrecord('TRDA', struct.pack('<iBIBHii', -1, number, 0, 1, 0, -1, -1))
        subs += _zstr('NAM1', text) + _zstr('NAM2', notes) + _zstr('NAM3', '') + _zstr('NAM4', '')
    subs += conditions
    if prompt:
        subs += _zstr('RNAM', prompt)
    if scene:
        subs += _u32('TSCE', scene)
    if forced_alias is not None:
        subs += _s32('ALFA', forced_alias)
    if stages != (NO_STAGE, NO_STAGE):
        subs += pack_subrecord('TIQS', struct.pack('<HH', *stages))
    subs += _zstr('NAM0', phase) + _u32('INAM', 1)
    return pack_fo4_record('INFO', fid, 0, subs)


def pack_player_dialogue(index: int, alias: int, player_topics: tuple, npc_topics: tuple) -> bytes:
    """A Player Dialogue scene action in phase 0 (CookeGreetScene's flags), ending with ANAM."""
    subs = pack_subrecord('ANAM', struct.pack('<H', 3)) + _zstr('NAM0', '') + _s32('ALID', alias)
    subs += _u32('INAM', index) + _u32('FNAM', PLAYER_DIALOGUE_FLAGS) + _u32('SNAM', 0) + _u32('ENAM', 0)
    for sig, fid in zip(('PTOP', 'NTOP', 'NETO', 'QTOP'), player_topics):
        subs += _u32(sig, fid)
    for sig, fid in zip(('NPOT', 'NNGT', 'NNUT', 'NQUT'), npc_topics):
        subs += _u32(sig, fid)
    return subs + _s32('DTGT', alias) + pack_subrecord('ANAM', b'')


def pack_scen(fid: int, edid: str, quest: int, alias: int, action: bytes, keyword: int) -> bytes:
    """A one-phase scene ('Menu') with one actor and one action, tagged with the XDI keyword.

    The phase completes, ending the scene, once the alias is farther than DIALOGUE_DISTANCE from the player.
    """
    walked_off = pack_ctda(OP_GREATER, DIALOGUE_DISTANCE, FUNC_GET_DISTANCE, PLAYER,
                           run_on=RUN_QUEST_ALIAS, param3=alias)
    subs = _zstr('EDID', edid) + _u32('FNAM', SCENE_FLAGS)
    subs += pack_subrecord('HNAM', b'') + _zstr('NAM0', 'Menu') + pack_subrecord('NEXT', b'') + walked_off
    subs += pack_subrecord('NEXT', b'') + _u32('WNAM', 350) + pack_subrecord('HNAM', b'')
    subs += _s32('ALID', alias) + _u32('LNAM', 4) + _u32('DNAM', 10)
    subs += action + _u32('PNAM', quest) + _u32('INAM', 1)
    subs += pack_subrecord('VNAM', struct.pack('<4I', 3, 3, 3, 3)) + pack_subrecord('ACTV', struct.pack('<f', DIALOGUE_DISTANCE))
    subs += _u32('KSIZ', 1) + _u32('KWDA', keyword) + _u32('XNAM', 0)
    return pack_fo4_record('SCEN', fid, 0, subs)


def pack_qust(fid: int, edid: str, name: str, priority: int, stages: list,
              alias_name: str, alias_ref) -> bytes:
    """A start-game-enabled quest with plain stages and one alias (id 0).

    alias_ref None: an optional, empty alias that forced-alias lines fill, as
    vanilla DialogueGenericDoctors' 'Doctor' (FNAM 2).
    """
    subs = _zstr('EDID', edid) + _zstr('FULL', name)
    subs += pack_subrecord('DNAM', struct.pack('<HBxfB3x', 0x0011, priority, 0.0, 0))
    subs += pack_subrecord('NEXT', b'')
    for stage in sorted(stages):
        subs += pack_subrecord('INDX', struct.pack('<HBB', stage, 0, 0)) + pack_subrecord('QSDT', b'\x00')
    subs += _u32('ANAM', 1) + _u32('ALST', 0) + _zstr('ALID', alias_name)
    subs += _u32('FNAM', 2) if alias_ref is None else _u32('FNAM', 0) + _u32('ALFR', alias_ref)
    subs += pack_subrecord('ALED', b'')
    return pack_fo4_record('QUST', fid, 0, subs)


def pack_achr(fid: int, base: int, pos: tuple, rot: tuple, vmad: bytes = b'') -> bytes:
    """A persistent placed actor: scripts (VMAD), base, position, rotation."""
    data = struct.pack('<6f', *pos, *rot)
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + _u32('NAME', base)
    return pack_fo4_record('ACHR', fid, 0x400, subs + pack_subrecord('DATA', data))


def pack_refr(fid: int, base: int, pos: tuple, rot: tuple) -> bytes:
    """A persistent placed object: base, position, rotation."""
    data = pack_subrecord('DATA', struct.pack('<6f', *pos, *rot))
    return pack_fo4_record('REFR', fid, 0x400, _u32('NAME', base) + data)


def pack_stat(fid: int, edid: str, model: str, bounds: tuple) -> bytes:
    """A static: bounds, model under Meshes, ClutterGenShelfA's DNAM."""
    subs = _zstr('EDID', edid) + pack_subrecord('OBND', struct.pack('<6h', *bounds)) + _zstr('MODL', model)
    return pack_fo4_record('STAT', fid, 0, subs + pack_subrecord('DNAM', struct.pack('<fIff', 90.0, 0, 1.0, 1.0)))


def pack_interior_cell(cell_record: bytes, cell_fid: int, block: int, sub_block: int,
                       persistent: bytes) -> bytes:
    """An interior CELL override with its persistent children, inside its block/sub-block groups."""
    children = pack_group(6, struct.pack('<I', cell_fid), pack_group(8, struct.pack('<I', cell_fid), persistent))
    sub = pack_group(3, struct.pack('<i', sub_block), cell_record + children)
    return pack_group(2, struct.pack('<i', block), sub)
