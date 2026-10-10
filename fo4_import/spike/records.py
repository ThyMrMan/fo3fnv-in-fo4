"""FO4 record packers for the dialogue spike, laid out from xEdit's wbDefinitionsFO4.pas.

Values xEdit cannot give (topic categories, subtype codes, scene action flags)
are copied from vanilla Fallout4.esm records named in each docstring.

See: docs/fork/fo4_spikes.md#spike-1
"""

import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.face.sculpt import with_face_morphs
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_group, pack_string_subrecord, pack_subrecord

NO_STAGE = 0xFFFF
#: Record flag Initially Disabled, the same bit in FO3/FNV and FO4.
INITIALLY_DISABLED = 0x800
#: FO4 CTDA Run On values.
RUN_SUBJECT, RUN_TARGET, RUN_REFERENCE = 0, 1, 2
#: INFO ENAM flag bits (wbDefinitionsFO4.pas INFO 'Response flags'). Random is never written: see dialogue.random_chain.
INFO_START_ON_END, INFO_SAY_ONCE, INFO_END_SCENE = 0x0001, 0x0004, 0x0040
#: DIAL DATA + SNAM. Scene topics: DialogueDiamondCity 001994FB; greetings: 000A7D2D.
TOPIC_SCENE = (bytes([0, 2, 0x10, 0]), b'SCEN')
TOPIC_GREETING = (bytes([0, 7, 0x74, 0]), b'GREE')
#: A Custom topic a script Says (MS09LorenzoWeakenedTopic 001A8938: DATA 0, SNAM CUST, in its quest's branch).
TOPIC_CUSTOM = (bytes(4), b'CUST')
#: DLBR DNAM of 128 of vanilla's 132 branches: Top-Level.
BRANCH_FLAGS = 1
#: Player Dialogue action FNAM from CookeGreetScene 0003A63D: face target, headtrack, camera on speaker.
PLAYER_DIALOGUE_FLAGS = 0x228800
#: Dialogue action FNAM of PastorGreetScene 0001F74A's line that starts another scene (its INFO's TSCE).
DIALOGUE_ACTION_FLAGS = 0x28000
#: SCEN FNAM from CookeGreetScene: show all text, has player dialogue, no follower chatter.
SCENE_FLAGS = 0x1024
#: SCEN FNAM Prevent Player Exit Dialogue (84 vanilla player-dialogue scenes).
SCENE_NO_EXIT = 0x40
#: Object id in XDI.esm of the keyword that marks a scene's menu for XDI.
XDI_KEYWORD = 0x800
#: SCEN ACTV (Dialogue Distance Override); the menu scene also ends past it, as 127 vanilla phases end on GetDistance.
DIALOGUE_DISTANCE = 500.0
RUN_QUEST_ALIAS = 5
OP_GREATER = 0x40
FUNC_GET_DISTANCE = 1
PLAYER = 0x14
#: Fallout4.esm's MiscMod01 TRNS: the Pip-Boy preview transform (PTRN) of 1,128 vanilla misc items.
MISC_PREVIEW = 0x248769
#: Vanilla paper notes' model, bounds, preview transform (PTRN), pickup sound (YNAM) and inventory art (INAM).
NOTE_MODEL, NOTE_BOUNDS = 'Props\\Note_LowPoly.nif', (-6, -7, 0, 6, 7, 1)
NOTE_PREVIEW, NOTE_PICKUP, NOTE_INVENTORY_ART = 0x2488FF, 0x1D4C0F, 0x1B5EF1
#: PNAM of nearly every vanilla activator (its editor marker colour).
MARKER_COLOR = bytes.fromhex('cc4c3300')


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
    """One FO4 condition (32 bytes); param3 is the alias id run on a quest alias."""
    data = struct.pack('<B3xfH2xIIIIi', op_flags, value, func, p1, p2, run_on, ref, param3)
    return pack_subrecord('CTDA', data)


def pack_dial(fid: int, edid: str, quest: int, kind: tuple, info_count: int, branch: int = 0) -> bytes:
    """A topic: priority 50, its branch, its quest, DATA and subtype code from `kind`, and its INFO count."""
    data, code = kind
    subs = _zstr('EDID', edid) + pack_subrecord('PNAM', struct.pack('<f', 50.0))
    subs += (_u32('BNAM', branch) if branch else b'') + _u32('QNAM', quest)
    subs += pack_subrecord('DATA', data) + pack_subrecord('SNAM', code) + _u32('TIFC', info_count)
    return pack_fo4_record('DIAL', fid, 0, subs)


def pack_dlbr(fid: int, edid: str, quest: int, start_topic: int) -> bytes:
    """A dialogue branch: its quest, category Player, BRANCH_FLAGS, its starting topic."""
    subs = _zstr('EDID', edid) + _u32('QNAM', quest) + _u32('TNAM', 0) + _u32('DNAM', BRANCH_FLAGS)
    return pack_fo4_record('DLBR', fid, 0, subs + _u32('SNAM', start_topic))


def pack_cis1(text: str) -> bytes:
    """A condition's first string parameter (CIS1), written after its CTDA."""
    return _zstr('CIS1', text)


def pack_cis2(text: str) -> bytes:
    """A condition's string parameter (CIS2), written after its CTDA."""
    return _zstr('CIS2', text)


def pack_info(fid: int, flags: int = 0, lines: tuple = (), conditions: bytes = b'',
              prompt: str = '', scene: int = 0, phase: str = '', phase_index: int = 0,
              stages: tuple = (NO_STAGE, NO_STAGE), notes: str = '', forced_alias: int = None,
              vmad: bytes = b'', idle: int = 0) -> bytes:
    """An INFO in vanilla's field order (DialogueDiamondCity 00199516).

    lines are response texts (none: an empty padding INFO); stages are the
    quest stages set on begin and on end (TIQS); scene/phase start a scene,
    at phase_index (INTV, which the engine reads, not the NAM0 name);
    forced_alias (ALFA) puts the speaker into that alias; vmad is its fragments;
    idle is the first response's speaker idle (SNAM, as 00142444's DialogueGiveItem).
    """
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + pack_subrecord('ENAM', struct.pack('<HH', flags, 0))
    for number, text in enumerate(lines, 1):
        subs += pack_subrecord('TRDA', struct.pack('<iBIBHii', -1, number, 0, 1, 0, -1, -1))
        subs += _zstr('NAM1', text) + _zstr('NAM2', notes) + _zstr('NAM3', '') + _zstr('NAM4', '')
        subs += _u32('SNAM', idle) if idle and number == 1 else b''
    subs += conditions
    if prompt:
        subs += _zstr('RNAM', prompt)
    if scene:
        subs += _u32('TSCE', scene) + (_s32('INTV', phase_index) if phase_index else b'')
    if forced_alias is not None:
        subs += _s32('ALFA', forced_alias)
    if stages != (NO_STAGE, NO_STAGE):
        subs += pack_subrecord('TIQS', struct.pack('<HH', *stages))
    subs += _zstr('NAM0', phase) + _u32('INAM', 1)
    return pack_fo4_record('INFO', fid, 0, subs)


def pack_player_dialogue(index: int, alias: int, player_topics: tuple, npc_topics: tuple, phase: int = 0) -> bytes:
    """A Player Dialogue scene action in `phase` (CookeGreetScene's flags), ending with ANAM."""
    subs = pack_subrecord('ANAM', struct.pack('<H', 3)) + _zstr('NAM0', '') + _s32('ALID', alias)
    subs += _u32('INAM', index) + _u32('FNAM', PLAYER_DIALOGUE_FLAGS) + _u32('SNAM', phase) + _u32('ENAM', phase)
    for sig, fid in zip(('PTOP', 'NTOP', 'NETO', 'QTOP'), player_topics):
        subs += _u32(sig, fid)
    for sig, fid in zip(('NPOT', 'NNGT', 'NNUT', 'NQUT'), npc_topics):
        subs += _u32(sig, fid)
    return subs + _s32('DTGT', alias) + pack_subrecord('ANAM', b'')


def pack_dialogue_action(index: int, alias: int, topic: int, phase: int = 0) -> bytes:
    """A Dialogue scene action in `phase`: `alias` says `topic` (PastorGreetScene's flags and distances)."""
    subs = pack_subrecord('ANAM', struct.pack('<H', 0)) + _zstr('NAM0', '') + _s32('ALID', alias)
    subs += _u32('INAM', index) + _u32('FNAM', DIALOGUE_ACTION_FLAGS) + _u32('SNAM', phase) + _u32('ENAM', phase)
    subs += _u32('DATA', topic) + pack_subrecord('DMAX', struct.pack('<f', 10.0))
    return subs + pack_subrecord('DMIN', struct.pack('<f', 1.0)) + pack_subrecord('ANAM', b'')


def pack_scen(fid: int, edid: str, quest: int, alias: int, actions: list, keyword: int,
              phases: tuple = ('Menu',), flags: int = 0) -> bytes:
    """A scene of named `phases` in order with one actor and `actions` (indices 1..n), tagged with `keyword` (0: none),
    FNAM SCENE_FLAGS plus `flags`.

    A one-phase scene also completes once the alias is farther than
    DIALOGUE_DISTANCE from the player; with several phases each completes
    on its actions, as vanilla's do (a completion condition holds the phase
    until it is true).
    """
    walked_off = b'' if len(phases) > 1 else pack_ctda(OP_GREATER, DIALOGUE_DISTANCE, FUNC_GET_DISTANCE, PLAYER,
                                                       run_on=RUN_QUEST_ALIAS, param3=alias)
    subs = _zstr('EDID', edid) + _u32('FNAM', SCENE_FLAGS | flags)
    for phase in phases:
        subs += pack_subrecord('HNAM', b'') + _zstr('NAM0', phase) + pack_subrecord('NEXT', b'') + walked_off
        subs += pack_subrecord('NEXT', b'') + _u32('WNAM', 350) + pack_subrecord('HNAM', b'')
    subs += _s32('ALID', alias) + _u32('LNAM', 4) + _u32('DNAM', 10)
    subs += b''.join(actions) + _u32('PNAM', quest) + _u32('INAM', len(actions))
    subs += pack_subrecord('VNAM', struct.pack('<4I', 3, 3, 3, 3)) + pack_subrecord('ACTV', struct.pack('<f', DIALOGUE_DISTANCE))
    subs += (_u32('KSIZ', 1) + _u32('KWDA', keyword) if keyword else b'') + _u32('XNAM', 0)
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
    return pack_fo4_record('QUST', fid, 0, subs + _u32('ANAM', 1) + _alias(0, alias_name, alias_ref))


def _alias(alias: int, name: str, ref) -> bytes:
    """A reference alias forced to `ref`, or optional and empty when None."""
    subs = _u32('ALST', alias) + _zstr('ALID', name)
    subs += _u32('FNAM', 2) if ref is None else _u32('FNAM', 0) + _u32('ALFR', ref)
    return subs + pack_subrecord('ALED', b'')


def pack_achr(fid: int, base: int, pos: tuple, rot: tuple, vmad: bytes = b'') -> bytes:
    """A persistent placed actor: scripts (VMAD), base, position, rotation."""
    data = struct.pack('<6f', *pos, *rot)
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + _u32('NAME', base)
    return pack_fo4_record('ACHR', fid, 0x400, subs + pack_subrecord('DATA', data))


def pack_refr(fid: int, base: int, pos: tuple, rot: tuple, scale: float = 1.0, radius: float = None,
              teleport: tuple = None, persistent: bool = True, primitive: bytes = b'', disabled: bool = False,
              linked: int = 0, edid: str = '') -> bytes:
    """A placed object: base, trigger primitive (XPRM), light radius (XRDS), teleport (door, position, rotation), scale.

    `disabled` sets Initially Disabled (0x800), as FO3/FNV's flag; `linked` is its linked reference (XLKR, no keyword);
    `edid` names the reference.
    """
    subs = (_zstr('EDID', edid) if edid else b'') + _u32('NAME', base)
    subs += pack_subrecord('XPRM', primitive) if primitive else b''
    if radius is not None:
        subs += pack_subrecord('XRDS', struct.pack('<f', radius))
    if teleport:
        door, to_pos, to_rot = teleport
        subs += pack_subrecord('XTEL', struct.pack('<I6fII', door, *to_pos, *to_rot, 0, 0))
    if linked:
        subs += pack_subrecord('XLKR', struct.pack('<II', 0, linked))
    if scale != 1.0:
        subs += pack_subrecord('XSCL', struct.pack('<f', scale))
    subs += pack_subrecord('DATA', struct.pack('<6f', *pos, *rot))
    return pack_fo4_record('REFR', fid, (0x400 if persistent else 0) | (INITIALLY_DISABLED if disabled else 0), subs)


def _bounded(edid: str, bounds: tuple) -> bytes:
    """EDID and OBND, the start of every placeable base record."""
    return _zstr('EDID', edid) + pack_subrecord('OBND', struct.pack('<6h', *bounds))


def pack_stat(fid: int, edid: str, model: str, bounds: tuple) -> bytes:
    """A static: bounds, model under Meshes, ClutterGenShelfA's DNAM."""
    subs = _bounded(edid, bounds) + _zstr('MODL', model)
    return pack_fo4_record('STAT', fid, 0, subs + pack_subrecord('DNAM', struct.pack('<fIff', 90.0, 0, 1.0, 1.0)))


def pack_mstt(fid: int, edid: str, model: str, bounds: tuple) -> bytes:
    """A movable static (3D follows its Havok body): bounds, model, no flags."""
    return pack_fo4_record('MSTT', fid, 0, _bounded(edid, bounds) + _zstr('MODL', model) + pack_subrecord('DATA', b'\0'))


def pack_door(fid: int, edid: str, name: str, model: str, bounds: tuple, flags: int, vmad: bytes = b'',
              sounds: tuple = (0, 0)) -> bytes:
    """A door: scripts, bounds, name, model, open and close sounds (SNDRs, 0 for none), FNAM flags."""
    subs = _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + _zstr('FULL', name) + _zstr('MODL', model)
    subs += _sounds(('SNAM', 'ANAM'), sounds)
    return pack_fo4_record('DOOR', fid, 0, subs + pack_subrecord('FNAM', bytes([flags])))


def _sounds(sigs: tuple, sounds: tuple) -> bytes:
    """The sound subrecords `sigs` of SNDRs `sounds`, each left out when 0."""
    return b''.join(_u32(sig, sound) for sig, sound in zip(sigs, sounds) if sound)


def pack_fnv_quest(fid: int, edid: str, name: str, priority: int, vmad: bytes, stages: list, objectives: list,
                   aliases: list, start: bool = False) -> bytes:
    """A quest: scripts, stages [(index, log flags)], objectives [(index, text, [alias ids])], aliases.

    Aliases are [(alias id, name, reference or None)] (see _alias), as an
    objective targets an alias in FO4, not a reference. `start`: start game
    enabled, with pack_qust's flags.
    """
    subs = _zstr('EDID', edid) + pack_subrecord('VMAD', vmad) + _zstr('FULL', name)
    subs += pack_subrecord('DNAM', struct.pack('<HBxfB3x', 0x0011 if start else 0, priority, 0.0, 0))
    subs += pack_subrecord('NEXT', b'')
    for index, log_flags in sorted(stages):
        subs += pack_subrecord('INDX', struct.pack('<HBB', index, 0, 0)) + pack_subrecord('QSDT', bytes([log_flags]))
    for index, text, targets in objectives:
        subs += pack_subrecord('QOBJ', struct.pack('<H', index)) + _u32('FNAM', 0) + _zstr('NNAM', text)
        subs += b''.join(pack_subrecord('QSTA', struct.pack('<iII', alias, 0, 0)) for alias in targets)
    subs += _u32('ANAM', len(aliases)) + b''.join(_alias(*alias) for alias in aliases)
    return pack_fo4_record('QUST', fid, 0, subs)


def pack_misc(fid: int, edid: str, name: str, model: str, bounds: tuple, value: int, weight: float) -> bytes:
    """A misc item: bounds, Pip-Boy preview, name, model, DATA value and weight."""
    subs = _bounded(edid, bounds) + _u32('PTRN', MISC_PREVIEW) + _zstr('FULL', name) + _zstr('MODL', model)
    return pack_fo4_record('MISC', fid, 0, subs + pack_subrecord('DATA', struct.pack('<If', value, weight)))


def pack_book(fid: int, edid: str, name: str, text: str) -> bytes:
    """A paper note to read: name and text on vanilla's note fields (BoS302BIngramBackupNote 0024800F)."""
    subs = _bounded(edid, NOTE_BOUNDS) + _u32('PTRN', NOTE_PREVIEW) + _zstr('FULL', name) + _zstr('MODL', NOTE_MODEL)
    subs += _zstr('DESC', text) + _u32('YNAM', NOTE_PICKUP) + pack_subrecord('DATA', bytes(8))
    return pack_fo4_record('BOOK', fid, 0, subs + pack_subrecord('DNAM', bytes(13)) + _u32('CNAM', 0)
                           + _u32('INAM', NOTE_INVENTORY_ART))


def pack_acti(fid: int, edid: str, name: str, model: str, bounds: tuple, vmad: bytes, prompt: str,
              loop: int = 0) -> bytes:
    """An activator: scripts, bounds, name, model (none for a trigger), vanilla's marker colour, looping sound
    (an SNDR, 0 for none), activate prompt."""
    subs = _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + (_zstr('FULL', name) if name else b'')
    subs += (_zstr('MODL', model) if model else b'') + pack_subrecord('PNAM', MARKER_COLOR)
    subs += _sounds(('SNAM',), (loop,))
    subs += (_zstr('ATTX', prompt) if prompt else b'') + pack_subrecord('FNAM', bytes(2))
    return pack_fo4_record('ACTI', fid, 0, subs)


def pack_furn(fid: int, edid: str, name: str, model: str, bounds: tuple, keywords: list, record_flags: int,
              active: int, marker_model: str, markers: list) -> bytes:
    """A furniture: bounds, name, model, keywords, MNAM `active` markers and flags, SNAM `markers`.

    Each marker is (x, y, z, heading, entry byte); PNAM, FNAM and WBDT are
    vanilla's most common (zero).
    """
    subs = _bounded(edid, bounds) + _zstr('FULL', name) + _zstr('MODL', model) + _u32('KSIZ', len(keywords))
    subs += pack_subrecord('KWDA', struct.pack(f'<{len(keywords)}I', *keywords)) + pack_subrecord('PNAM', bytes(4))
    subs += pack_subrecord('FNAM', bytes(2)) + _u32('MNAM', active) + pack_subrecord('WBDT', bytes(1))
    subs += _zstr('XMRK', marker_model) if marker_model else b''
    subs += pack_subrecord('SNAM', b''.join(struct.pack('<4fIB3x', *m[:4], 0, m[4]) for m in markers))
    return pack_fo4_record('FURN', fid, record_flags, subs)


def pack_mswp(fid: int, edid: str, pairs: list) -> bytes:
    """A material swap of [(original, replacement)] (paths under Materials\\)."""
    subs = b''.join(_zstr('BNAM', original) + _zstr('SNAM', replacement) for original, replacement in pairs)
    return pack_fo4_record('MSWP', fid, 0, _zstr('EDID', edid) + subs)


def pack_flst(fid: int, edid: str, forms: list) -> bytes:
    """A form list: `forms` in order (LNAM each)."""
    return pack_fo4_record('FLST', fid, 0, _zstr('EDID', edid) + b''.join(_u32('LNAM', f) for f in forms))


def pack_perk(fid: int, edid: str, name: str, desc: str, trait: bool) -> bytes:
    """A playable one-rank perk without effects (a trait when `trait`)."""
    subs = _zstr('EDID', edid) + _zstr('FULL', name) + _zstr('DESC', desc)
    return pack_fo4_record('PERK', fid, 0, subs + pack_subrecord('DATA', bytes([int(trait), 0, 1, 1, 0])))


def pack_lvli(fid: int, edid: str, chance_none: int, flags: int, entries: list) -> bytes:
    """A leveled item: chance none, flags, entries [(level, item FormID, count)] (LVLO, 12 bytes each)."""
    subs = _bounded(edid, (0,) * 6) + pack_subrecord('LVLD', bytes([chance_none])) + pack_subrecord(
        'LVLM', b'\0') + pack_subrecord('LVLF', bytes([flags])) + pack_subrecord('LLCT', bytes([len(entries)]))
    subs += b''.join(pack_subrecord('LVLO', struct.pack('<HHIHBB', level, 0, item, count, 0, 0))
                     for level, item, count in entries)
    return pack_fo4_record('LVLI', fid, 0, subs)


def pack_cont(fid: int, edid: str, name: str, model: str, bounds: tuple, items: list, flags: int,
              weight: float, sounds: tuple = (0, 0)) -> bytes:
    """A container: bounds, name, model, items [(FormID, count)] (COCT, CNTO), DATA flags and weight, open and
    close sounds (SNDRs, 0 for none)."""
    subs = _bounded(edid, bounds) + _zstr('FULL', name) + _zstr('MODL', model)
    subs += _u32('COCT', len(items)) + b''.join(pack_subrecord('CNTO', struct.pack('<Ii', item, count))
                                                 for item, count in items)
    subs += pack_subrecord('DATA', struct.pack('<Bf', flags, weight)) + _sounds(('SNAM', 'QNAM'), sounds)
    return pack_fo4_record('CONT', fid, 0, subs)


def pack_ligh(fid: int, edid: str, bounds: tuple, model: str, light: tuple, fade: float) -> bytes:
    """A light; `light` is (radius, (r, g, b), flags), the rest of DATA vanilla's most common omni light.

    That light (604 of 801 in Fallout4.esm): falloff exponent 1, FOV 90,
    near clip 7.217, flicker period 1, constant 0, scalar 1, exponent 2.
    """
    radius, color, flags = light
    data = struct.pack('<iI4BI12f', -1, radius, *color, 0, flags, 1.0, 90.0, 7.217, 1.0, 0.0, 0.0, 0.0, 1.0, 2.0,
                       0.0, 0.0, 0.0)
    subs = _bounded(edid, bounds) + (_zstr('MODL', model) if model else b'')
    return pack_fo4_record('LIGH', fid, 0, subs + pack_subrecord('DATA', data) + pack_subrecord(
        'FNAM', struct.pack('<f', fade)))


def clone_npc(fid: int, body: bytes, flags: int, edid: str, name: str, drop: frozenset = frozenset(),
              morphs: bytes = b'', edit=None) -> bytes:
    """A vanilla NPC_ body as a new NPC: EDID, FULL (plain) replaced, `drop` left out, face `morphs` added.

    `edit`, if given, maps the finished subrecords to the ones written.
    """
    subs = b''
    for tag, data in subrecords(body):
        if tag in drop:
            continue
        if tag == b'EDID':
            subs += _zstr('EDID', edid)
        elif tag == b'FULL':
            subs += _zstr('FULL', name)
        else:
            subs += pack_subrecord(tag.decode(), data)
    subs = with_face_morphs(subs, morphs) if morphs else subs
    return pack_fo4_record('NPC_', fid, flags, edit(subs) if edit else subs)


def pack_cell(fid: int, edid: str, name: str, flags: int, lighting: bytes, template: int, imagespace: int) -> bytes:
    """An interior cell: name, DATA flags, XCLL lighting, lighting template, water height 0, imagespace."""
    subs = _zstr('EDID', edid) + _zstr('FULL', name) + pack_subrecord('DATA', struct.pack('<H', flags))
    subs += pack_subrecord('XCLL', lighting) + _u32('LTMP', template)
    subs += pack_subrecord('XCLW', struct.pack('<f', 0.0)) + _u32('XCIM', imagespace)
    return pack_fo4_record('CELL', fid, 0, subs)


def pack_interior_cells(cells: list) -> bytes:
    """Interior cells in their block and sub-block groups (object id mod 10, then tens digit).

    cells: (CELL record, its FormID, persistent children, temporary children).
    """
    blocks = {}
    for record, fid, persistent, temporary in sorted(cells, key=lambda c: c[1]):
        label = struct.pack('<I', fid)
        kids = (pack_group(8, label, persistent) if persistent else b'') + (
            pack_group(9, label, temporary) if temporary else b'')
        object_id = fid & 0xFFFFFF
        subs = blocks.setdefault(object_id % 10, {})
        subs[object_id // 10 % 10] = subs.get(object_id // 10 % 10, b'') + record + pack_group(6, label, kids)
    return b''.join(pack_group(2, struct.pack('<i', b), b''.join(pack_group(3, struct.pack('<i', s), body)
                                                                 for s, body in sorted(subs.items())))
                    for b, subs in sorted(blocks.items()))
