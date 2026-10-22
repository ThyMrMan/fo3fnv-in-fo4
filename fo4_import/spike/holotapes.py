"""FNV voice notes (audio logs) as Fallout 4 holotapes, for the cell spike.

FO4 plays a voice holotape (NOTE DNAM Voice) by starting its scene (SNAM).
The scene's Radio actions (type 6) say a topic with no actor (alias -2)
through the holotape's 2D sound output (SOMDialogue2D_Holotape), one line
per phase, as vanilla's 133 voice holotapes do (DN150_BonnieHolotape
001C037F in HolotapesQuest). Each line is a topic of its own whose INFO
names a speaker NPC (ANAM), whose voice type files the recording, as 535
of HolotapesQuest's 536 lines do. An FNV voice note names its topic (TNAM)
and speaker (SNAM); each of the topic's INFOs becomes a line, recorded under
the speaker's converted voice type (voice.py). The speaker is a copy of
vanilla's holotape speaker DN150_BonnieTournquist with FNV's name and voice
type. The holotape keeps the note's FormID; its quest, scene, topics and
speaker are hashed from it.

See: docs/fork/fo4_pipeline.md#holotapes
"""

import struct
from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.base.writer import pack_fo4_record, pack_quest, pack_topic
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.voice_types import with_voice
from tes5_import.base.tes5_reader import walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Vanilla holotapes' preview transform, model, bounds, pickup and drop sounds (DN150_HolotapeBonnie 00225D7B).
PREVIEW, MODEL, BOUNDS, PICKUP, DROP = 0x0995A5, 'Props\\Holotape_Prop.nif', (-3, -3, 0, 3, 3, 1), 0x0BBFA8, 0x0BBFA9
#: NOTE DNAM Voice; the speaker template (DN150_BonnieTournquist); the holotape sound output (SOMDialogue2D_Holotape).
VOICE, SPEAKER, OUTPUT = 1, 0x1C0380, 0x073265
#: A holotape line's topic: DATA (category Scene, subtype 0x11) and SNAM, as vanilla's (001C01F5).
TOPIC = (bytes([0, 2, 0x11, 0]), b'SCEN')
#: Holotape scene FNAM, scene action type Radio, and the actor id of none, as DN150_BonnieHolotape.
SCENE_FLAGS, RADIO, NO_ACTOR = 0x104, 6, -2
#: FNV NOTE DATA type of a voice note.
FNV_VOICE = 3


def _zstr(sig: str, text: str) -> bytes:
    """A null-terminated string subrecord."""
    return pack_string_subrecord(sig, text)


def _u32(sig: str, value: int) -> bytes:
    """A 4-byte subrecord."""
    return pack_subrecord(sig, struct.pack('<i' if value < 0 else '<I', value))


def radio_action(index: int, topic: int, alias: int = NO_ACTOR, output: int = OUTPUT, sound: int = 0) -> bytes:
    """Radio scene action `index` (1..n) in phase index - 1, on `alias`: saying `topic`, or playing `sound` (an
    SNDR, as DiamondCityRadioMusicScene's songs)."""
    subs = pack_subrecord('ANAM', struct.pack('<H', RADIO)) + _zstr('NAM0', '') + _u32('ALID', alias)
    subs += _u32('INAM', index) + _u32('SNAM', index - 1) + _u32('ENAM', index - 1) + _u32('DATA', topic)
    return subs + _u32('HTID', sound) + _u32('DMAX', output) + pack_subrecord('ANAM', b'')


def pack_scene(fid: int, edid: str, quest: int, topics: list, flags: int = SCENE_FLAGS, alias: int = NO_ACTOR,
               output: int = OUTPUT, sounds: list = (), conditions: list = ()) -> bytes:
    """A scene of Radio actions, one phase per topic of `topics`, on `alias` (none: a holotape's, as
    DN150_BonnieHolotape) through `output`, its `flags`; a phase's `sounds` entry plays that SNDR instead,
    its `conditions` entry (CTDA bytes) gates its start."""
    subs = _zstr('EDID', edid) + _u32('FNAM', flags)
    for i in range(len(topics)):
        subs += pack_subrecord('HNAM', b'') + _zstr('NAM0', '') + (conditions[i] if i < len(conditions) else b'')
        subs += pack_subrecord('NEXT', b'') + pack_subrecord('NEXT', b'') + _u32('WNAM', 350) + pack_subrecord('HNAM', b'')
    subs += _u32('ALID', alias) + _u32('LNAM', 0) + _u32('DNAM', 0)
    subs += b''.join(radio_action(i, topic, alias, output, sounds[i - 1] if i <= len(sounds) else 0)
                     for i, topic in enumerate(topics, 1))
    subs += _u32('PNAM', quest) + _u32('INAM', len(topics)) + pack_subrecord('VNAM', struct.pack('<4I', 3, 3, 3, 3))
    return pack_fo4_record('SCEN', fid, 0, subs + _u32('XNAM', 0))


def pack_holotape(fid: int, edid: str, name: str, look: tuple, scene: int) -> bytes:
    """A voice holotape: name, `look` (model, bounds) and its scene, on vanilla's holotape fields."""
    subs = _zstr('EDID', edid) + pack_subrecord('OBND', struct.pack('<6h', *look[1])) + _u32('PTRN', PREVIEW)
    subs += _zstr('FULL', name) + _zstr('MODL', look[0]) + _u32('YNAM', PICKUP) + _u32('ZNAM', DROP)
    subs += pack_subrecord('DNAM', bytes([VOICE])) + pack_subrecord('DATA', struct.pack('<If', 0, 0.0))
    return pack_fo4_record('NOTE', fid, 0, subs + _u32('SNAM', scene))


class Holotapes:
    """FO4 holotapes for FNV voice notes, each made once."""

    def __init__(self, builder, export_dir: Path, form_map):
        """Holotapes written through `builder`; `form_map()` gives the forms line conditions name."""
        self.builder, self.form_map = builder, form_map
        self.infos = {}
        for rec in export_records(export_dir, 'INFO'):
            self.infos.setdefault(rec['ParentDIAL'].upper(), []).append(rec)
        self.voices = {int(r['FormID'], 16): r for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}

    def holotape(self, rec: dict) -> 'int | None':
        """The FO4 holotape of FNV voice note `rec` (its FormID); None when its lines or speaker cannot convert."""
        key, speaker = rec['FormID'].upper(), self._speaker(rec)
        lines = self.infos.get(rec.get('TNAM.Topic', '').upper(), [])
        if speaker is None or not lines or self.builder.say is None:
            self.builder.counts['holotape left out (no speaker, lines or dialogue)'] += 1
            return None
        quest = self.builder.new_id(f'QUST holotape {key}')
        topics = [self._line(info, quest, speaker) for info in lines]
        topics = [t for t in topics if t]
        scene = self.builder.new_id(f'SCEN holotape {key}')
        edid = f'FNV_{rec["EditorID"]}'
        record = R.pack_fnv_quest(quest, f'{edid}Quest', '', 0, quest_fragments('', []), [], [], [], True)
        self.builder.writer.add_record('QUST', pack_quest(record, quest, [], [blob for _, blob in topics],
                                                          [pack_scene(scene, f'{edid}Scene', quest,
                                                                      [fid for fid, _ in topics])]))
        fid = self.builder.fnv_id(rec['FormID'])
        self.builder.writer.add_record('NOTE', pack_holotape(fid, edid, rec.get('FULL', ''), self._look(rec), scene))
        self.builder.counts['NOTE (holotape)'] += 1
        return fid

    def _look(self, rec: dict) -> tuple:
        """(model, bounds): FNV's mesh, else vanilla's holotape."""
        if not rec.get('Model.MODL'):
            return MODEL, BOUNDS
        model, bounds = self.builder.mesh(rec['Model.MODL'])
        return model, bounds or BOUNDS

    def _line(self, info: dict, quest: int, speaker: int) -> 'tuple | None':
        """(topic FormID, its pack_topic blob) of one FNV line; None when its conditions cannot convert."""
        made = self.builder.say.info(info, self.form_map(), speaker=speaker)
        if not made:
            return None
        topic = self.builder.new_id(f'DIAL holotape {info["FormID"]}')
        dial = R.pack_dial(topic, f'FNV_Holotape{info["FormID"].upper()}', quest, TOPIC, 1)
        return topic, pack_topic(dial, topic, [made])

    def _speaker(self, rec: dict) -> 'int | None':
        """A speaker NPC carrying the voice type of the note's FNV speaker (SNAM), made once per note."""
        fnv = self.voices.get(int(rec.get('SNAM', '0'), 16))
        if fnv is None:
            return None
        return speaker_npc(self.builder, f'NPC_ holotape {rec["FormID"].upper()}', f'FNV_{fnv["EditorID"]}Holotape',
                           fnv.get('FULL', ''), int(fnv.get('VTCK.Voice', '0'), 16))


def speaker_npc(builder, key: str, edid: str, name: str, fnv_voice: int) -> 'int | None':
    """A speaker NPC (a copy of vanilla's holotape speaker SPEAKER) named `name`, on FNV voice type `fnv_voice`
    converted; its FormID from `key`; None when the voice type does not convert."""
    voice = builder.creatures.voices.of(fnv_voice)
    if voice is None:
        return None
    template = next(r for r, _ in walk(builder.fo4, b'NPC_') if r.form_id == SPEAKER)
    fid = builder.new_id(key)
    builder.writer.add_record('NPC_', R.clone_npc(fid, template.body, template.flags, edid, name,
                                                  edit=with_voice(voice)))
    return fid
