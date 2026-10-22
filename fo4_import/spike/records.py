"""FO4 record packers for the dialogue spike, laid out from xEdit's wbDefinitionsFO4.pas.

Values xEdit cannot give (topic categories, subtype codes, scene action flags)
are copied from vanilla Fallout4.esm records named in each docstring.

See: docs/fork/fo4_spikes.md#spike-1
"""

import re
import struct

from fo4_import.base.writer import pack_fo4_record
from fo4_import.face.sculpt import with_face_morphs
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_group, pack_string_subrecord, pack_subrecord

NO_STAGE = 0xFFFF
#: FNV direction notes in dialogue text ({Apologetic}), which its subtitles leave out.
_DIRECTION = re.compile(r"{[^}]*}")
#: Text of a line that says nothing: silent greetings, [Leave] exits, FNV lines without text (fo4_spikes.md#silent-line).
SILENT_LINE = ''
#: Record flag Initially Disabled, the same bit in FO3/FNV and FO4.
INITIALLY_DISABLED = 0x800
#: Quest alias flag Uses Stored Text: the alias's display name (ALDN) names it, as a radio station's Host.
USES_STORED_TEXT = 0x4000
#: ACTI FNAM flag Is a Radio: a receiver, its RADR naming the frequency.
IS_A_RADIO = 0x10
#: FO4 CTDA Run On values.
RUN_SUBJECT, RUN_TARGET, RUN_REFERENCE = 0, 1, 2
#: INFO ENAM flag bits (wbDefinitionsFO4.pas INFO 'Response flags'). Random is never written: see dialogue.random_chain.
INFO_START_ON_END, INFO_SAY_ONCE, INFO_END_SCENE = 0x0001, 0x0004, 0x0040
#: DIAL DATA + SNAM. Scene topics: DialogueDiamondCity 001994FB; greetings: 000A7D2D.
TOPIC_SCENE = (bytes([0, 2, 0x10, 0]), b'SCEN')
TOPIC_GREETING = (bytes([0, 7, 0x74, 0]), b'GREE')
#: The player's Hello before an NPC greets (DialogueGenericPlayer's 00018184: DATA 0 7 0x49 0, SNAM HELO).
TOPIC_PLAYER_HELLO = (bytes([0, 7, 0x49, 0]), b'HELO')
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
#: Dialogue action FNAM Face Target of 1,031 vanilla actions in scenes of NPCs only; the target is its HTID actor.
NPC_ACTION_FLAGS = 0x8000
#: SCEN FNAM of NPC-only scenes: Show All Text, Interruptible (the 256 vanilla 0x17 less their quest start/stop).
NPC_SCENE_FLAGS = 0x14
#: SCEN actor LNAM Optional: the scene runs with the alias empty (a monologue's listener).
ACTOR_OPTIONAL = 0x2
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
#: Fallout4.esm KeyChainsAlt: the Pip-Boy preview transform of 71 of vanilla's 177 keys, the most common.
KEY_PREVIEW = 0x248894
#: Vanilla paper notes' model, bounds, preview transform (PTRN), pickup sound (YNAM) and inventory art (INAM).
NOTE_MODEL, NOTE_BOUNDS = 'Props\\Note_LowPoly.nif', (-6, -7, 0, 6, 7, 1)
NOTE_PREVIEW, NOTE_PICKUP, NOTE_INVENTORY_ART = 0x2488FF, 0x1D4C0F, 0x1B5EF1
#: PNAM of nearly every vanilla activator (its editor marker colour).
MARKER_COLOR = bytes.fromhex('cc4c3300')


def pack_u32(sig: str, value: int) -> bytes:
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
    subs += (pack_u32('BNAM', branch) if branch else b'') + pack_u32('QNAM', quest)
    subs += pack_subrecord('DATA', data) + pack_subrecord('SNAM', code) + pack_u32('TIFC', info_count)
    return pack_fo4_record('DIAL', fid, 0, subs)


def pack_dlbr(fid: int, edid: str, quest: int, start_topic: int) -> bytes:
    """A dialogue branch: its quest, category Player, BRANCH_FLAGS, its starting topic."""
    subs = _zstr('EDID', edid) + pack_u32('QNAM', quest) + pack_u32('TNAM', 0) + pack_u32('DNAM', BRANCH_FLAGS)
    return pack_fo4_record('DLBR', fid, 0, subs + pack_u32('SNAM', start_topic))


def pack_cis1(text: str) -> bytes:
    """A condition's first string parameter (CIS1), written after its CTDA."""
    return _zstr('CIS1', text)


def pack_cis2(text: str) -> bytes:
    """A condition's string parameter (CIS2), written after its CTDA."""
    return _zstr('CIS2', text)


def shown(text: str) -> str:
    """FNV dialogue text as shown: `{...}` direction notes left out."""
    return _DIRECTION.sub('', text).strip() or text


def pack_info(fid: int, flags: int = 0, lines: tuple = (), conditions: bytes = b'',
              prompt: str = '', scene: int = 0, phase: str = '', phase_index: int = 0,
              stages: tuple = (NO_STAGE, NO_STAGE), notes: str = '', forced_alias: int = None,
              vmad: bytes = b'', idles: tuple = (), speaker: int = 0) -> bytes:
    """An INFO in vanilla's field order (DialogueDiamondCity 00199516).

    lines: response texts (none: padding), shown() as the prompt; stages are the
    quest stages set on begin and on end (TIQS); scene/phase start a scene,
    at phase_index (INTV, which the engine reads, not the NAM0 name);
    forced_alias (ALFA) puts the speaker into that alias; vmad is its fragments;
    idles: per response (speaker, listener) idle (SNAM, LNAM); speaker (ANAM)
    is the NPC whose voice speaks it (001C01F8).
    """
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + pack_subrecord('ENAM', struct.pack('<HH', flags, 0))
    for number, text in enumerate(lines, 1):
        subs += pack_subrecord('TRDA', struct.pack('<iBIBHii', -1, number, 0, 1, 0, -1, -1))
        subs += _zstr('NAM1', shown(text)) + _zstr('NAM2', notes) + _zstr('NAM3', '') + _zstr('NAM4', '')
        said, heard = idles[number - 1] if number <= len(idles) else (0, 0)
        subs += (pack_u32('SNAM', said) if said else b'') + (pack_u32('LNAM', heard) if heard else b'')
    subs += conditions
    if prompt:
        subs += _zstr('RNAM', shown(prompt))
    if scene:
        subs += pack_u32('TSCE', scene) + (_s32('INTV', phase_index) if phase_index else b'')
    if forced_alias is not None:
        subs += _s32('ALFA', forced_alias)
    if stages != (NO_STAGE, NO_STAGE):
        subs += pack_subrecord('TIQS', struct.pack('<HH', *stages))
    subs += (pack_u32('ANAM', speaker) if speaker else b'') + _zstr('NAM0', phase) + pack_u32('INAM', 1)
    return pack_fo4_record('INFO', fid, 0, subs)


def pack_player_dialogue(index: int, alias: int, player_topics: tuple, npc_topics: tuple, phase: int = 0) -> bytes:
    """A Player Dialogue scene action in `phase` (CookeGreetScene's flags), ending with ANAM."""
    subs = pack_subrecord('ANAM', struct.pack('<H', 3)) + _zstr('NAM0', '') + _s32('ALID', alias)
    subs += pack_u32('INAM', index) + pack_u32('FNAM', PLAYER_DIALOGUE_FLAGS) + pack_u32('SNAM', phase) + pack_u32('ENAM', phase)
    for sig, fid in zip(('PTOP', 'NTOP', 'NETO', 'QTOP'), player_topics):
        subs += pack_u32(sig, fid)
    for sig, fid in zip(('NPOT', 'NNGT', 'NNUT', 'NQUT'), npc_topics):
        subs += pack_u32(sig, fid)
    return subs + _s32('DTGT', alias) + pack_subrecord('ANAM', b'')


def pack_dialogue_action(index: int, alias: int, topic: int, phase: int = 0, listener: 'int | None' = None) -> bytes:
    """A Dialogue scene action in `phase`: `alias` says `topic` (PastorGreetScene's flags and distances); facing
    and headtracking alias `listener` instead of the player when given (NPC_ACTION_FLAGS, HTID)."""
    flags = DIALOGUE_ACTION_FLAGS if listener is None else NPC_ACTION_FLAGS
    subs = pack_subrecord('ANAM', struct.pack('<H', 0)) + _zstr('NAM0', '') + _s32('ALID', alias)
    subs += pack_u32('INAM', index) + pack_u32('FNAM', flags) + pack_u32('SNAM', phase) + pack_u32('ENAM', phase)
    subs += pack_u32('DATA', topic) + pack_subrecord('DMAX', struct.pack('<f', 10.0))
    subs += pack_subrecord('DMIN', struct.pack('<f', 1.0)) + (b'' if listener is None else _s32('HTID', listener))
    return subs + pack_subrecord('ANAM', b'')


def pack_scen(fid: int, edid: str, quest: int, alias: int, actions: list, keyword: int,
              phases: tuple = ('Menu',), flags: int = 0, listener: 'int | None' = None) -> bytes:
    """A scene of named `phases` in order with actor `alias` and `actions` (indices 1..n), tagged with `keyword`
    (0: none), FNAM SCENE_FLAGS plus `flags`; with a `listener` actor too, an NPC-only scene (NPC_SCENE_FLAGS).

    A one-phase scene also completes once the alias is farther than
    DIALOGUE_DISTANCE from the player; with several phases each completes
    on its actions, as vanilla's do (a completion condition holds the phase
    until it is true).
    """
    walked_off = b'' if len(phases) > 1 else pack_ctda(OP_GREATER, DIALOGUE_DISTANCE, FUNC_GET_DISTANCE, PLAYER,
                                                       run_on=RUN_QUEST_ALIAS, param3=alias)
    subs = _zstr('EDID', edid) + pack_u32('FNAM', (SCENE_FLAGS if listener is None else NPC_SCENE_FLAGS) | flags)
    for phase in phases:
        subs += pack_subrecord('HNAM', b'') + _zstr('NAM0', phase) + pack_subrecord('NEXT', b'') + walked_off
        subs += pack_subrecord('NEXT', b'') + pack_u32('WNAM', 350) + pack_subrecord('HNAM', b'')
    for actor, optional in ((alias, 0),) if listener is None else ((alias, 0), (listener, ACTOR_OPTIONAL)):
        subs += _s32('ALID', actor) + pack_u32('LNAM', 4 | optional) + pack_u32('DNAM', 10)
    subs += b''.join(actions) + pack_u32('PNAM', quest) + pack_u32('INAM', len(actions))
    subs += pack_subrecord('VNAM', struct.pack('<4I', 3, 3, 3, 3)) + pack_subrecord('ACTV', struct.pack('<f', DIALOGUE_DISTANCE))
    subs += (pack_u32('KSIZ', 1) + pack_u32('KWDA', keyword) if keyword else b'') + pack_u32('XNAM', 0)
    return pack_fo4_record('SCEN', fid, 0, subs)


def pack_qust(fid: int, edid: str, name: str, priority: int, stages: list,
              alias_name: str, alias_ref, vmad: bytes = b'') -> bytes:
    """A start-game-enabled quest with plain stages and one alias (id 0), scripts and fragments in `vmad`.

    alias_ref None: an optional, empty alias that forced-alias lines fill, as
    vanilla DialogueGenericDoctors' 'Doctor' (FNAM 2).
    """
    subs = _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'') + _zstr('FULL', name)
    subs += pack_subrecord('DNAM', struct.pack('<HBxfB3x', 0x0011, priority, 0.0, 0))
    subs += pack_subrecord('NEXT', b'')
    for stage in sorted(stages):
        subs += pack_subrecord('INDX', struct.pack('<HBB', stage, 0, 0)) + pack_subrecord('QSDT', b'\x00')
    return pack_fo4_record('QUST', fid, 0, subs + pack_u32('ANAM', 1) + _alias(0, alias_name, alias_ref))


def _alias(alias: int, name: str, ref, packages: 'tuple | None' = None, display: int = 0, voices: int = 0) -> bytes:
    """A reference alias forced to `ref`, or optional and empty when None; given `packages`, an empty collection
    alias running them (ALPC), in vanilla's order (CZ_Arena's Crowd); a `display` name message (ALDN) sets Uses
    Stored Text, as RadioDiamondCity's Host; `voices` (VTCK: an NPC or list) voices a non-actor, as RadioSubway's."""
    collection = packages is not None
    subs = (pack_u32('ALCS', alias) + pack_subrecord('ALMI', b'\0') if collection else b'') + pack_u32('ALST', alias)
    flags = 2 if ref is None else USES_STORED_TEXT if display else 0
    subs += _zstr('ALID', name) + pack_u32('FNAM', flags) + (b'' if ref is None else pack_u32('ALFR', ref))
    subs += pack_u32('ALDN', display) if display else b''
    subs += b''.join(pack_u32('ALPC', package) for package in packages or ())
    subs += pack_u32('VTCK', voices) if voices or collection else b''
    return subs + pack_subrecord('ALED', b'')


def pack_achr(fid: int, base: int, pos: tuple, rot: tuple, vmad: bytes = b'', extra: bytes = b'',
              flags: int = 0x400) -> bytes:
    """A placed actor: scripts (VMAD), base, `extra` subrecords (parents, links), position, rotation; record
    `flags` (persistent 0x400, initially disabled 0x800: the same bits as FNV's)."""
    data = struct.pack('<6f', *pos, *rot)
    subs = (pack_subrecord('VMAD', vmad) if vmad else b'') + pack_u32('NAME', base) + extra
    return pack_fo4_record('ACHR', fid, flags, subs + pack_subrecord('DATA', data))


def pack_refr(fid: int, base: int, pos: tuple, rot: tuple, scale: float = 1.0, radius: float = None,
              teleport: tuple = None, persistent: bool = True, placement: bytes = b'', disabled: bool = False,
              linked: int = 0, edid: str = '', door_link: tuple = None, sig: str = 'REFR') -> bytes:
    """A placed object: base, `placement` (packed XMBO/XPRM/XPOD/XRGD, spike.placement), light radius (XRDS),
    teleport (door, position, rotation), scale.

    `disabled` sets Initially Disabled (0x800), as FO3/FNV's flag; `linked` is its linked reference (XLKR, no keyword);
    `edid` names the reference; `door_link` is a teleport door's (navmesh, triangle) (XNDP); `sig` is the record
    type (PGRE for a placed projectile).
    """
    subs = (_zstr('EDID', edid) if edid else b'') + pack_u32('NAME', base) + placement
    if radius is not None:
        subs += pack_subrecord('XRDS', struct.pack('<f', radius))
    if teleport:
        door, to_pos, to_rot = teleport
        subs += pack_subrecord('XTEL', struct.pack('<I6fII', door, *to_pos, *to_rot, 0, 0))
    if teleport and door_link:
        subs += pack_subrecord('XNDP', struct.pack('<Ih2x', *door_link))
    if linked:
        subs += pack_subrecord('XLKR', struct.pack('<II', 0, linked))
    if scale != 1.0:
        subs += pack_subrecord('XSCL', struct.pack('<f', scale))
    subs += pack_subrecord('DATA', struct.pack('<6f', *pos, *rot))
    return pack_fo4_record(sig, fid, (0x400 if persistent else 0) | (INITIALLY_DISABLED if disabled else 0), subs)


def _bounded(edid: str, bounds: tuple, vmad: bytes = b'') -> bytes:
    """EDID, scripts (VMAD, if any) and OBND: every placeable base record's start."""
    return _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'') + pack_subrecord(
        'OBND', struct.pack('<6h', *bounds))


def pack_stat(fid: int, edid: str, model: str, bounds: tuple) -> bytes:
    """A static: bounds, model under Meshes, ClutterGenShelfA's DNAM."""
    subs = _bounded(edid, bounds) + _zstr('MODL', model)
    return pack_fo4_record('STAT', fid, 0, subs + pack_subrecord('DNAM', struct.pack('<fIff', 90.0, 0, 1.0, 1.0)))


def pack_mstt(fid: int, edid: str, model: str, bounds: tuple, sound: int = 0) -> bytes:
    """A movable static: bounds, model, looping sound (SNDR, 0: none)."""
    subs = _bounded(edid, bounds) + _zstr('MODL', model) + pack_subrecord('DATA', b'\0')
    return pack_fo4_record('MSTT', fid, 0, subs + (pack_u32('SNAM', sound) if sound else b''))


def pack_door(fid: int, edid: str, name: str, model: str, bounds: tuple, flags: int, vmad: bytes = b'',
              sounds: tuple = (0, 0, 0)) -> bytes:
    """A door: scripts, bounds, name, model, open, close and loop sounds (SNDRs, 0 for none), FNAM flags."""
    subs = _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + _zstr('FULL', name) + (_zstr('MODL', model) if model else b'')
    subs += _sounds(('SNAM', 'ANAM', 'BNAM'), sounds)
    return pack_fo4_record('DOOR', fid, 0, subs + pack_subrecord('FNAM', bytes([flags])))


def _sounds(sigs: tuple, sounds: tuple) -> bytes:
    """The sound subrecords `sigs` of SNDRs `sounds`, each left out when 0."""
    return b''.join(pack_u32(sig, sound) for sig, sound in zip(sigs, sounds) if sound)


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
        subs += pack_subrecord('QOBJ', struct.pack('<H', index)) + pack_u32('FNAM', 0) + _zstr('NNAM', text)
        subs += b''.join(pack_subrecord('QSTA', struct.pack('<iII', alias, 0, 0)) for alias in targets)
    subs += pack_u32('ANAM', max((alias[0] for alias in aliases), default=-1) + 1)
    subs += b''.join(_alias(*alias) for alias in aliases)
    return pack_fo4_record('QUST', fid, 0, subs)


def pack_misc(fid: int, edid: str, name: str, model: str, bounds: tuple, value: int, weight: float,
              vmad: bytes = b'') -> bytes:
    """A misc item: scripts, bounds, preview, name, model, DATA value and weight."""
    subs = _bounded(edid, bounds, vmad) + pack_u32('PTRN', MISC_PREVIEW) + _zstr('FULL', name) + (_zstr('MODL', model) if model else b'')
    return pack_fo4_record('MISC', fid, 0, subs + pack_subrecord('DATA', struct.pack('<If', value, weight)))


def pack_keym(fid: int, edid: str, name: str, model: str, bounds: tuple, value: int, weight: float,
              vmad: bytes = b'') -> bytes:
    """A key (vanilla's commonest layout, preview KeyChainsAlt), laid out as pack_misc."""
    subs = _bounded(edid, bounds, vmad) + pack_u32('PTRN', KEY_PREVIEW) + _zstr('FULL', name) + (_zstr('MODL', model) if model else b'')
    return pack_fo4_record('KEYM', fid, 0, subs + pack_subrecord('DATA', struct.pack('<If', value, weight)))


def pack_book(fid: int, edid: str, name: str, text: str, look: tuple = (NOTE_MODEL, NOTE_BOUNDS),
              worth: tuple = (0, 0.0), vmad: bytes = b'', flags: int = 0) -> bytes:
    """A book to read: name, `look` (model, bounds), text, `worth` (value, weight), scripts and DNAM `flags` on
    vanilla's paper note fields (BoS302BIngramBackupNote 0024800F)."""
    subs = _bounded(edid, look[1], vmad) + pack_u32('PTRN', NOTE_PREVIEW) + _zstr('FULL', name) + _zstr('MODL', look[0])
    subs += _zstr('DESC', text) + pack_u32('YNAM', NOTE_PICKUP) + pack_subrecord('DATA', struct.pack('<If', *worth))
    return pack_fo4_record('BOOK', fid, 0, subs + pack_subrecord('DNAM', bytes([flags]) + bytes(12)) + pack_u32('CNAM', 0)
                           + pack_u32('INAM', NOTE_INVENTORY_ART))


def pack_acti(fid: int, edid: str, name: str, model: str, bounds: tuple, vmad: bytes, prompt: str,
              loop: int = 0, receiver: bytes = b'') -> bytes:
    """An activator: scripts, bounds, name, model (none for a trigger), vanilla's marker colour, looping sound
    (an SNDR, 0 for none), activate prompt; a `receiver` (RADR data) makes it a radio (FNAM Is a Radio), as
    RadioDiamondCityReceiverOff."""
    subs = _zstr('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + (_zstr('FULL', name) if name else b'')
    subs += (_zstr('MODL', model) if model else b'') + pack_subrecord('PNAM', MARKER_COLOR)
    subs += _sounds(('SNAM',), (loop,))
    subs += (_zstr('ATTX', prompt) if prompt else b'') + pack_subrecord('FNAM', struct.pack('<H', IS_A_RADIO if receiver else 0))
    return pack_fo4_record('ACTI', fid, 0, subs + (pack_subrecord('RADR', receiver) if receiver else b''))


def pack_furn(fid: int, edid: str, name: str, model: str, bounds: tuple, keywords: list, record_flags: int,
              active: int, marker_model: str, markers: list) -> bytes:
    """A furniture: bounds, name, model, keywords, MNAM `active` markers and flags, SNAM `markers`.

    Each marker is (x, y, z, heading, entry byte); PNAM, FNAM and WBDT are
    vanilla's most common (zero).
    """
    subs = _bounded(edid, bounds) + _zstr('FULL', name) + _zstr('MODL', model) + pack_u32('KSIZ', len(keywords))
    subs += pack_subrecord('KWDA', struct.pack(f'<{len(keywords)}I', *keywords)) + pack_subrecord('PNAM', bytes(4))
    subs += pack_subrecord('FNAM', bytes(2)) + pack_u32('MNAM', active) + pack_subrecord('WBDT', bytes(1))
    subs += _zstr('XMRK', marker_model) if marker_model else b''
    subs += pack_subrecord('SNAM', b''.join(struct.pack('<4fIB3x', *m[:4], 0, m[4]) for m in markers))
    return pack_fo4_record('FURN', fid, record_flags, subs)


def pack_kywd(fid: int, edid: str, kind: int, name: str = '') -> bytes:
    """A keyword of TNAM `kind` (9: recipe filter), white CNAM, `name` if given."""
    subs = _zstr('EDID', edid) + pack_subrecord('CNAM', b'\xff\xff\xff\x00') + pack_u32('TNAM', kind)
    return pack_fo4_record('KYWD', fid, 0, subs + (_zstr('FULL', name) if name else b''))


def pack_cobj(fid: int, edid: str, parts: list, made: tuple, bench: int, filters: list, conditions: bytes) -> bytes:
    """A constructible object: `parts` [(item, count)] (FVPA), `conditions`, `made` (item, count), the `bench`
    keyword and recipe `filters` keywords."""
    subs = _zstr('EDID', edid) + pack_subrecord('FVPA', b''.join(struct.pack('<II', *p) for p in parts))
    subs += conditions + pack_u32('CNAM', made[0]) + pack_u32('BNAM', bench)
    subs += pack_subrecord('FNAM', struct.pack(f'<{len(filters)}I', *filters)) if filters else b''
    return pack_fo4_record('COBJ', fid, 0, subs + pack_subrecord('INTV', struct.pack('<HH', made[1], 0)))


def pack_mswp(fid: int, edid: str, pairs: list) -> bytes:
    """A material swap of [(original, replacement)] (paths under Materials\\)."""
    subs = b''.join(_zstr('BNAM', original) + _zstr('SNAM', replacement) for original, replacement in pairs)
    return pack_fo4_record('MSWP', fid, 0, _zstr('EDID', edid) + subs)


def pack_flst(fid: int, edid: str, forms: list) -> bytes:
    """A form list: `forms` in order (LNAM each)."""
    return pack_fo4_record('FLST', fid, 0, _zstr('EDID', edid) + b''.join(pack_u32('LNAM', f) for f in forms))


def pack_leveled(sig: str, fid: int, edid: str, chance_none: int, flags: int, entries: list) -> bytes:
    """A leveled list `sig` (LVLI, LVLN): chance none, flags, entries [(level, FormID, count)] (LVLO, 12 bytes)."""
    subs = _bounded(edid, (0,) * 6) + pack_subrecord('LVLD', bytes([chance_none])) + pack_subrecord(
        'LVLM', b'\0') + pack_subrecord('LVLF', bytes([flags])) + pack_subrecord('LLCT', bytes([len(entries)]))
    subs += b''.join(pack_subrecord('LVLO', struct.pack('<HHIHBB', level, 0, item, count, 0, 0))
                     for level, item, count in entries)
    return pack_fo4_record(sig, fid, 0, subs)


def pack_cont(fid: int, edid: str, name: str, model: str, bounds: tuple, items: list, flags: int,
              weight: float, sounds: tuple = (0, 0), vmad: bytes = b'') -> bytes:
    """A container: scripts, bounds, name, model, items [(FormID, count)] (COCT, CNTO), DATA flags and weight,
    open and close sounds (SNDRs, 0 for none)."""
    subs = _bounded(edid, bounds, vmad) + _zstr('FULL', name) + (_zstr('MODL', model) if model else b'')
    subs += pack_u32('COCT', len(items)) + b''.join(pack_subrecord('CNTO', struct.pack('<Ii', item, count))
                                                 for item, count in items)
    subs += pack_subrecord('DATA', struct.pack('<Bf', flags, weight)) + _sounds(('SNAM', 'QNAM'), sounds)
    return pack_fo4_record('CONT', fid, 0, subs)


def pack_ligh(fid: int, edid: str, bounds: tuple, model: str, light: tuple, fade: float, sound: int = 0) -> bytes:
    """A light; `light` is (radius, (r, g, b), flags, falloff exponent, FOV, flicker (period, intensity and
    movement amplitudes)), the rest of DATA vanilla's most common omni light; `sound` its SNDR (SNAM, 0: none).

    That light (604 of 801 in Fallout4.esm): near clip 7.217, constant 0, scalar 1, exponent 2.
    """
    radius, color, flags, falloff, fov, flicker = light
    data = struct.pack('<iI4BI12f', -1, radius, *color, 0, flags, falloff, fov, 7.217, *flicker, 0.0, 1.0, 2.0,
                       0.0, 0.0, 0.0)
    subs = _bounded(edid, bounds) + (_zstr('MODL', model) if model else b'')
    subs += pack_subrecord('DATA', data) + pack_subrecord('FNAM', struct.pack('<f', fade))
    return pack_fo4_record('LIGH', fid, 0, subs + (pack_u32('SNAM', sound) if sound else b''))


def packages_edit(packages: list):
    """A clone edit putting FO4 `packages` (PKID) in place of the stand-in's, right after AIDT as all 1,120 vanilla
    NPCs with packages place them."""
    def edit(subs: bytes) -> bytes:
        """The subrecords without the stand-in's PKIDs, ours after AIDT."""
        ours = b''.join(pack_subrecord('PKID', struct.pack('<I', p)) for p in packages)
        out = b''
        for tag, data in subrecords(subs):
            if tag != b'PKID':
                out += pack_subrecord(tag.decode(), data) + (ours if tag == b'AIDT' else b'')
        return out
    return edit


def with_sub(tag: bytes, payload: bytes, before: tuple):
    """A record edit putting subrecord `tag` (`payload`) in place of any it has, before the first of tags `before`
    (else last); None for an empty `payload`."""
    if not payload:
        return None

    def edit(subs: bytes) -> bytes:
        """The subrecords with `tag` placed."""
        out, placed = b'', False
        for other, data in subrecords(subs):
            if other in before and not placed:
                out, placed = out + pack_subrecord(tag.decode(), payload), True
            out += pack_subrecord(other.decode(), data) if other != tag else b''
        return out if placed else out + pack_subrecord(tag.decode(), payload)
    return edit


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


def pack_cell(fid: int, edid: str, name: str, flags: int, lighting: bytes, template: int, imagespace: int,
              water: float = 0.0, owner: int = 0, place: tuple = (0, 0), extra: bytes = b'') -> bytes:
    """An interior cell: name, DATA flags, XCLL lighting, lighting template, water height, owner (a faction or
    NPC), `place` (location, encounter zone), imagespace; 0 for none; then `extra` subrecords (XCAS)."""
    subs = _zstr('EDID', edid) + _zstr('FULL', name) + pack_subrecord('DATA', struct.pack('<H', flags))
    subs += pack_subrecord('XCLL', lighting) + pack_u32('LTMP', template)
    subs += pack_subrecord('XCLW', struct.pack('<f', water)) + (pack_u32('XLCN', place[0]) if place[0] else b'')
    subs += pack_subrecord('XOWN', struct.pack('<I', owner) + bytes(8)) if owner else b''
    subs += (pack_u32('XEZN', place[1]) if place[1] else b'') + pack_u32('XCIM', imagespace) + extra
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
