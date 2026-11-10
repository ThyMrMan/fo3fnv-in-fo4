"""FNV radio programs as Fallout 4 station scenes, for the cell spike.

An FNV station says its quest's radio lines: RadioHello first, then each
line's Choices name the topics that may follow (Radio New Vegas: intro,
news, sign-off, song intro, songs; Black Mountain: a song, then a segment
whose lines run in order and end on a song). A line whose response plays a
sound is a song.

On Fallout 4 the program is a scene per step: a step is the set of topics a
line chooses from (RadioHello the first). Its scene has a Radio phase per
topic, each after the first tried only while nothing is said yet
(`Said`), so the first topic with a passing line speaks, then a phase per
song of those topics, gated on `CurrentSong` and playing the song's sound
record. Each line carries F3NV_RadioLine, which tells F3NV_RadioPlaylist as
it begins that it was said, its song and the step its Choices make (back to
the first without any). Each scene's end fragment (F3NV_RadioScene) starts
that step when a line was said; a step with nothing to say ends there, and
the playlist's timer starts the first step again (RadioFailsafeScript's
role). Lines are said by speaker NPCs on the FNV voice types their
recordings are filed under, named on the Host alias's Voice Types, as
RadioSubway's announcer.

See: docs/fork/fo4_radio.md#steps-model
"""

import functools
import struct
from collections import Counter, deque
from pathlib import Path, PurePosixPath

from fo4_import.base.install import source_walk
from fo4_import.base.support_records import pack_mesg
from fo4_import.base.vmad import scene_fragments
from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.holotapes import TOPIC, pack_scene, speaker_npc
from fo4_import.spike.say_topics import VM_QUEST_VARIABLE
from fo4_import.spike.voice import fnv_folders, index_recordings
from fo4_import.spike.voice_types import fnv_voice_types
from fo4_import.pipeline.export_index import export_file
from tes5_import.base.tes5_reader import first_sub
from tes5_import.base.writer import pack_string_subrecord

#: FNV's radio topic every station's program starts at (RadioHello).
RADIO_HELLO = '00000126'
#: FNV topic type Radio; INFO flags Random and Random End, which FO4's ENAM has at the same bits.
RADIO_TOPIC, RANDOM_FLAGS = '7', 0x22
#: FNV INFO flag Goodbye: the line ends its station's run.
GOODBYE = 0x01
#: The station quest's transmitter alias; step scene flags (RadioSilverShroudQuest_Music's, started by script).
HOST_ALIAS, PLAYLIST_FLAGS = 2000, 0x104
#: The station quest's script, a line's script, and the step scenes' end fragment script and function.
PLAYLIST_SCRIPT, LINE_SCRIPT, SCENE_SCRIPT, SCENE_END = 'F3NV_RadioPlaylist', 'F3NV_RadioLine', 'F3NV_RadioScene', \
    'Fragment_End'
#: The playlist's conditional properties, as GetVMQuestVariable names them.
CURRENT_SONG, SAID = '::CurrentSong_var', '::Said_var'
#: Byte offset of a response's sound in FNV TRDT.
TRDT_SOUND = 16
#: A song's file as FNV ships it when its sound names another: .ogg for the .mp3 named, its mono copy for 3D.
SONG_FILES = ('.ogg', '_mono.ogg')


@functools.cache
def recorded_voices(export_dir: Path) -> dict:
    """{FNV INFO FormID: the FNV voice type whose recordings folder holds its first response}."""
    out = {}
    for fnv, (edid, _) in fnv_voice_types().items():
        for info, number in index_recordings(fnv_folders(export_dir, edid)):
            if number == 1:
                out.setdefault(info, fnv)
    return out


def song_file(export_dir: Path, name: str) -> 'str | None':
    """FNV sound file `name` as the export holds it, under its sound folder: as named, else as FNV ships its
    songs (SONG_FILES); None if none exists."""
    if not name:
        return None
    rel = PurePosixPath(name.replace('\\', '/').lower())
    tried = [rel] + [rel.with_name(rel.stem + end) for end in SONG_FILES]
    return next((r.as_posix() for r in tried if export_file(export_dir, 'sound', r).is_file()), None)


@functools.cache
def song_sounds() -> dict:
    """{FNV INFO FormID: its first response's sound (TRDT Sound)} of FalloutNV.esm's lines playing one."""
    out = {}
    for rec, _ in source_walk(b'DIAL', b'INFO', bodies=(b'INFO',)):
        trdt = first_sub(rec.body, b'TRDT') if rec.sig == b'INFO' else None
        sound = struct.unpack_from('<I', trdt, TRDT_SOUND)[0] if trdt and len(trdt) >= TRDT_SOUND + 4 else 0
        if sound:
            out[rec.form_id] = sound
    return out


def quest_var(quest: int, variable: str, value: int) -> bytes:
    """A condition: the playlist property `variable` (CIS2) equals `value`."""
    return R.pack_ctda(0, float(value), C.FO4.index(VM_QUEST_VARIABLE), quest) + pack_string_subrecord('CIS2', variable)


def radio_lines(say, rec: dict) -> list:
    """FNV quest `rec`'s lines (in `say`, a SayTopics) whose topic is a Radio one.
    See: docs/fork/fo4_radio.md#stage-acts
    """
    return [r for r in say.infos.get(rec['FormID'].upper(), [])
            if say.dials.get(r['ParentDIAL'].upper(), {}).get('DATA.Type') == RADIO_TOPIC]


def ends_run(line: dict) -> bool:
    """Whether FNV radio `line` is flagged Goodbye (it ends its station's run)."""
    return bool(int(line.get('DATA.Flags', 0) or 0) & GOODBYE)


def choices(line: dict, topics: dict) -> tuple:
    """FNV `line`'s Choices the station has lines in; RadioHello for none."""
    picked = tuple(c for c in (line.get(f'Choice[{i}]', '').upper() for i in range(int(line.get('ChoiceCount', 0) or 0)))
                   if c in topics)
    return picked or (RADIO_HELLO,)


def steps(topics: dict) -> list:
    """The station's steps (tuples of FNV topics) along its lines' Choices, first-found order: from RadioHello, then
    from each topic no line chooses (one only a script starts) in line order; none without RadioHello lines.
    See: docs/fork/fo4_radio.md#script-topics
    """
    found = []
    for seed in [RADIO_HELLO, *topics] if RADIO_HELLO in topics else []:
        queue = deque([] if any(seed in step for step in found) else [(seed,)])
        while queue:
            step = queue.popleft()
            if step not in found:
                found.append(step)
                queue.extend(choices(line, topics) for topic in step for line in topics[topic])
    return found


class Speakers:
    """A station program's speaker NPCs, one per FNV voice type its lines are recorded under (made on first use)."""

    def __init__(self, builder, quest: dict, station: dict):
        """Speakers for station quest `quest`; `station`'s VNAM is the default voice."""
        self.builder, self.quest, self.name, self.made = builder, quest, station.get('FULL', ''), {}
        self.station_voice = int(station.get('VNAM', '0'), 16)

    def of(self, voice: int) -> 'int | None':
        """The speaker NPC on FNV voice type `voice`; None when it does not convert."""
        if voice not in self.made:
            key, edid = f'NPC_ radio {self.quest["FormID"]} {voice:08X}', f'FNV_{self.quest["EditorID"]}Speaker'
            self.made[voice] = speaker_npc(self.builder, key, f'{edid}{len(self.made) or ""}', self.name, voice)
        return self.made[voice]

    def voices(self) -> int:
        """The Host alias's voices (VTCK): the one speaker NPC, or a list of them; 0 with none."""
        made = [npc for npc in self.made.values() if npc]
        if len(made) < 2:
            return made[0] if made else 0
        fid = self.builder.new_id(f'FLST radio {self.quest["FormID"]} speakers')
        self.builder.writer.add_record('FLST', R.pack_flst(fid, f'FNV_{self.quest["EditorID"]}Speakers', made))
        return fid


class Program:
    """One FNV station quest's program on its FO4 quest: topics, lines, songs and step scenes."""

    def __init__(self, radio, rec: dict, quest: int, station: dict, lines: list, on_demand: bool = False):
        """Station `station`'s (its TACT record) radio `lines` on FO4 `quest`, through `radio` (a radio.Radio);
        `rec`'s FormID and EditorID name the program's forms; `on_demand`: only a script starts it. Its default
        voice is the station's VNAM, else its lines' most common recorded one (Black Mountain has none)."""
        self.radio, self.builder, self.rec, self.quest = radio, radio.builder, rec, quest
        self.on_demand = on_demand
        self.speakers, self.songs = Speakers(self.builder, rec, station), {}
        self.topics = {}
        for line in lines:
            self.topics.setdefault(line['ParentDIAL'].upper(), []).append(line)
        recorded = Counter(v for v in (recorded_voices(radio.export_dir).get(int(r['FormID'], 16)) for r in lines) if v)
        if not self.speakers.station_voice and recorded:
            self.speakers.station_voice = recorded.most_common(1)[0][0]
        self.steps = steps(self.topics)
        reached = {topic for step in self.steps for topic in step}
        self.builder.counts['radio line left out (topic not reached from RadioHello)'] += sum(
            len(v) for k, v in self.topics.items() if k not in reached)

    def build(self, form_map: dict, host: int, station: dict, receivers: tuple = ((), 0)) -> 'tuple | None':
        """(aliases, topic blobs, scenes, quest scripts): the Host alias, a topic per FNV topic reached, a scene per
        step and F3NV_RadioPlaylist; `receivers` is (references its on-demand program switches on, the receiver
        activator SetNPCRadio places or 0). None when no line converts."""
        ids = [self.builder.new_id(self._scene_key(step)) for step in self.steps]
        reached = list(dict.fromkeys(topic for step in self.steps for topic in step))
        made = {topic: blob for topic in reached for blob in [self._topic(topic, form_map)] if blob}
        if not made:
            return None
        scenes = [self._scene(fid, step, made) for fid, step in zip(ids, self.steps)]
        self.builder.scripts.used += [s for s in (PLAYLIST_SCRIPT, LINE_SCRIPT, SCENE_SCRIPT)
                                      if s not in self.builder.scripts.used]
        self.builder.counts['radio programs'] += 1
        host_alias = (HOST_ALIAS, 'Host', host, None, self._display(station), self.speakers.voices())
        names = [self.builder.say.dials.get(step[0], {}).get('EditorID', step[0]) for step in self.steps]
        values = {'Steps': ('objects', ids), 'StepTopics': ('strings', names)}
        placed, npc = receivers
        if self.on_demand:
            values.update(OnDemand=('bool', True), Receivers=('objects', list(placed)))
        runner = (PLAYLIST_SCRIPT, {'Program': ids[0], **({'NPCReceiver': npc} if npc else {})}, values)
        return [host_alias], [blob for blob, _ in made.values()], scenes, [runner]

    def _scene_key(self, step: tuple) -> str:
        """A step scene's FormID key; the first step keeps the first programs' key."""
        return f'SCEN radio {self.rec["FormID"]}' + ('' if step == (RADIO_HELLO,) else ' ' + ' '.join(step))

    def _topic(self, topic: str, form_map: dict) -> 'tuple | None':
        """(blob, FO4 topic FormID) of FNV `topic`'s lines; None when none converts. RadioHello keeps the key the
        first programs gave their topic."""
        infos = [made for line in self.topics[topic] for made in [self._line(line, form_map)] if made]
        if not infos:
            return None
        key = 'pick' if topic == RADIO_HELLO else topic
        fid = self.builder.new_id(f'DIAL radio {self.rec["FormID"]} {key}')
        name = f'FNV_{self.rec["EditorID"]}_{self.builder.say.dials.get(topic, {}).get("EditorID", topic)}'
        return pack_topic(R.pack_dial(fid, name, self.quest, TOPIC, len(infos)), fid, infos), fid

    def _line(self, line: dict, form_map: dict) -> bytes:
        """FNV radio `line` as an FO4 line said by the speaker of its voice (FNV's Random flags kept), telling the
        playlist its song and next step as it begins (F3NV_RadioLine); b'' with no recording or song (FO4 ends a
        line without audio at once), no speaker or a condition not converting."""
        recorded = recorded_voices(self.radio.export_dir).get(int(line['FormID'], 16))
        soun, path = self._song_file(line)
        if recorded is None and path is None:
            self.builder.counts['radio line left out (no recording or song)'] += 1
            return b''
        speaker = self.speakers.of(recorded or self.speakers.station_voice)
        if speaker is None:
            self.builder.counts['radio line left out (no voice type)'] += 1
            return b''
        song = self._song(line, soun, path) if path else 0
        tells = ((LINE_SCRIPT, {'Playlist': self.quest}, {'Song': ('int', song), 'NextStep': ('int', self.next_step(line))}),)
        return self.builder.say.info(line, form_map, flags=int(line.get('DATA.Flags', 0)) & RANDOM_FLAGS,
                                     speaker=speaker, owner=self.quest, place=f'radio {line["FormID"]}', helpers=tells)

    def next_step(self, line: dict) -> int:
        """The 1-based step `line` leads to; 0 for an on-demand Goodbye line."""
        return 0 if self.on_demand and ends_run(line) else self.steps.index(choices(line, self.topics)) + 1

    def _song_file(self, line: dict) -> tuple:
        """(SOUN, export file) of `line`'s song; the file None when spoken or missing."""
        soun = song_sounds().get(int(line['FormID'], 16), 0)
        return soun, song_file(self.radio.export_dir, self.radio.sounds.get(soun, ''))

    def _song(self, line: dict, soun: int, path: Path) -> int:
        """The station's number of FNV `line`'s song, its SNDR (`songs`) playing `path`."""
        sndr = self.builder.sounds.song(soun, path)
        self.songs[line['FormID']] = (len(self.songs) + 1, sndr)
        self.builder.counts['radio songs'] += 1
        return len(self.songs)

    def _scene(self, fid: int, step: tuple, made: dict) -> bytes:
        """A step's scene: a Radio phase per topic with lines (after the first, only while nothing is said), then a
        phase per song of those topics on its CurrentSong; its end fragment moves the playlist on."""
        topics = [made[t][1] for t in step if t in made]
        songs = [self.songs[line['FormID']] for t in step if t in made for line in self.topics[t]
                 if line['FormID'] in self.songs]
        gates = [b''] + [quest_var(self.quest, SAID, 0)] * (len(topics) - 1)
        gates += [quest_var(self.quest, CURRENT_SONG, number) for number, _ in songs]
        name = f'FNV_{self.rec["EditorID"]}Step{self.steps.index(step) + 1}'
        return pack_scene(fid, name, self.quest, topics + [0] * len(songs), PLAYLIST_FLAGS, HOST_ALIAS, 0,
                          sounds=[0] * len(topics) + [sndr for _, sndr in songs], conditions=gates,
                          vmad=scene_fragments(SCENE_SCRIPT, SCENE_END))

    def _display(self, station: dict) -> int:
        """The Host alias's display name: a message naming the station, the name the Pip-Boy lists."""
        fid = self.builder.new_id(f'MESG radio {self.rec["FormID"]}')
        name = station.get('FULL', '')
        self.builder.writer.add_record('MESG', pack_mesg(fid, f'FNV_{self.rec["EditorID"]}Display', name, name, 0, []))
        return fid
