"""FNV radio stations as Fallout 4 transmitters the Pip-Boy lists, for the cell spike.

An FNV station is a talking activator (TACT) flagged Radio Station, placed
once; the Pip-Boy lists those not flagged Non-Pipboy. Its reference's XRDO
(dropped by the export, read from FalloutNV.esm) gives its reach:
Everywhere, or a radius around the reference or its position reference,
static over the last part of it. Fallout 4's Pip-Boy lists the
transmitters in reach: references of an activator like Fallout4.esm's
RadioTransmitter, with XRDO (frequency, weak-signal distances, Ignores
Distance Checks).

Each Pip-Boy station becomes a copy of RadioTransmitter named for it, on
FNV's FormID, its references placed persistent in the built worldspace's
persistent cell (one in an interior or past the build too, the first world
built taking interior ones), at the position reference when there is one.
Its frequency is a free Pip-Boy slot (FREQUENCIES, in station FormID
order), named on the base by TES4_RadioStation; Everywhere is Ignores Distance Checks,
a radius a weak signal from where FNV's static begins out to the radius.

See: docs/fork/fo4_radio.md#transmitters
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import source_esm
from fo4_import.base.support_records import pack_mesg
from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import pack_fo4_record, pack_topic
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.holotapes import TOPIC, pack_scene, speaker_npc
from fo4_import.spike.voice import fnv_folder, index_recordings
from fo4_import.spike.say_topics import VM_QUEST_VARIABLE
from fo4_import.spike.voice_types import fnv_voice_types
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: FNV TACT record flags: Radio Station, and Non-Pipboy (a station only its placed radios play); FNV persistent.
RADIO_STATION, NON_PIPBOY, PERSISTENT = 0x20000, 0x10000000, 0x400
#: FNV XRDO broadcast range type Radius; FO4 XRDO flag Ignores Distance Checks.
RADIUS, IGNORES_DISTANCE = 0, 0x1
#: Fallout4.esm's transmitter activator each station copies.
TRANSMITTER = 'RadioTransmitter'
#: Pip-Boy frequencies (exe defaults 80 to 110) at least 1.0 from every Fallout4.esm and DLC transmitter.
FREQUENCIES = (80.0, 80.5, 81.0, 84.0, 84.5, 85.0, 90.0, 93.0, 96.0, 101.0, 108.5, 109.0, 109.5, 110.0)
#: The script a transmitter base carries, naming its frequency for TES4_Radio.Heard.
STATION_SCRIPT = 'TES4_RadioStation'
#: Exported reference position keys.
POSITION = ('PosX', 'PosY', 'PosZ')
#: FNV dialog type Radio; INFO flags Random and Random End, which FO4's ENAM has at the same bits.
RADIO_LINE, RANDOM_FLAGS = '7', 0x22
#: The station quest's transmitter alias; playlist scene flags (RadioSilverShroudQuest_Music's, started by script).
HOST_ALIAS, PLAYLIST_FLAGS = 2000, 0x104
#: The station quest's playlist script, and the script a pick line sets its song with.
PLAYLIST_SCRIPT, SONG_SCRIPT = 'TES4_RadioPlaylist', 'TES4_RadioSong'
#: The playlist script's conditional song property, as GetVMQuestVariable names it.
CURRENT_SONG = '::CurrentSong_var'
#: FNV condition GetIsID (a station quest's own condition names its talking activator).
GET_IS_ID = 72
#: Byte offset of a response's sound in FNV TRDT.
TRDT_SOUND = 16
#: A song's file as FNV ships it when its sound names another: .ogg for the .mp3 named, its mono copy for 3D.
SONG_FILES = ('.ogg', '_mono.ogg')


def pipboy_stations(export_dir: Path) -> dict:
    """{FNV FormID: TACT record} of FNV's Pip-Boy radio stations."""
    return {int(r['FormID'], 16): r for r in export_records(export_dir, 'TACT')
            if int(r.get('RecordFlags', 0)) & (RADIO_STATION | NON_PIPBOY) == RADIO_STATION}


@functools.cache
def radio_data() -> dict:
    """{FNV reference: (radius, range type, static %, position ref)}: FNV XRDO."""
    return {rec.form_id: struct.unpack_from('<fIfI', data)
            for rec, _ in walk(source_esm(), b'REFR') for data in [first_sub(rec.body, b'XRDO')] if data}


def placements(export_dir: Path, all_refs: list, world, interiors: bool) -> list:
    """Copies of FNV's Pip-Boy station references for `world`'s (an Exterior) persistent cell: those in its
    worldspace not yet in it and, when `interiors`, those in an interior; persistent, at their position reference
    when they have one."""
    stations = pipboy_stations(export_dir)
    cells = {r['FormID']: r for r in export_records(export_dir, 'CELL')}
    placed = {r['FormID'] for r in world.refs}
    out = []
    for ref in all_refs:
        cell = cells.get(ref.get('ParentCELL'), {})
        own = cell.get('ParentWRLD') == world.world['FormID']
        if int(ref.get('NAME', '0'), 16) not in stations or ref['FormID'] in placed or not (own or interiors
                                                                                            and 'ParentWRLD' not in cell):
            continue
        at = _position_ref(export_dir, all_refs, radio_data().get(int(ref['FormID'], 16), (0, 0, 0, 0))[3])
        out.append({**ref, **(at or {}), 'ParentCELL': world.persistent_cell,
                    'RecordFlags': str(int(ref['RecordFlags']) | PERSISTENT)})
    return out


def _position_ref(export_dir: Path, all_refs: list, fid: int) -> 'dict | None':
    """{PosX, PosY, PosZ} of FNV reference `fid`; None for none or one not exported."""
    if not fid:
        return None
    key = f'{fid:08X}'
    found = next((r for r in all_refs if r['FormID'] == key), None) or next(
        (r for sig in ('ACHR', 'ACRE') for r in export_records(export_dir, sig) if r['FormID'] == key), None)
    return {k: found[k] for k in POSITION} if found else None


def frequency_of(fnv_station: int, stations: dict) -> 'float | None':
    """`fnv_station`'s FREQUENCIES slot, in station FormID order; None past them."""
    order = sorted(stations).index(fnv_station)
    return FREQUENCIES[order] if order < len(FREQUENCIES) else None


def xrdo_data(frequency: float, radio: tuple) -> bytes:
    """FO4 XRDO of a station reference on `frequency` with FNV `radio` data (radio_data)."""
    radius, kind, static, _ = radio
    if kind != RADIUS or radius <= 0:
        return struct.pack('<3fI', frequency, 0.0, 0.0, IGNORES_DISTANCE)
    return struct.pack('<3fI', frequency, radius * (1.0 - static / 100.0), radius, 0)


def station_of(quest: dict, stations: dict) -> 'int | None':
    """The station whose lines FNV quest `quest` holds: its quest condition GetIsID's talking activator."""
    i = 0
    while f'Condition[{i}].Raw' in quest:
        raw = bytes.fromhex(quest[f'Condition[{i}].Raw'])
        i += 1
        func, form = struct.unpack_from('<II', raw, 8) if len(raw) >= 16 else (0, 0)
        if func == GET_IS_ID and form in stations:
            return form
    return None


@functools.cache
def recorded_voices(export_dir: Path) -> dict:
    """{FNV INFO FormID: the FNV voice type whose recordings folder holds its first response}."""
    out = {}
    for fnv, (edid, _) in fnv_voice_types().items():
        folder = fnv_folder(export_dir, edid)
        for info, number in index_recordings(folder) if folder.is_dir() else ():
            if number == 1:
                out.setdefault(info, fnv)
    return out


def song_file(export_dir: Path, name: str) -> 'Path | None':
    """The export's file of FNV sound file `name`: as named, else as FNV ships its songs (SONG_FILES); None if
    none exists."""
    if not name:
        return None
    path = export_dir / 'sound' / name.replace('\\', '/').lower()
    return next((p for p in [path] + [path.with_name(path.stem + end) for end in SONG_FILES] if p.is_file()), None)


@functools.cache
def song_sounds() -> dict:
    """{FNV INFO FormID: its first response's sound (TRDT Sound)} of FalloutNV.esm's lines playing one."""
    out = {}
    for rec, _ in walk(source_esm(), b'DIAL', b'INFO', bodies=(b'INFO',)):
        trdt = first_sub(rec.body, b'TRDT') if rec.sig == b'INFO' else None
        sound = struct.unpack_from('<I', trdt, TRDT_SOUND)[0] if trdt and len(trdt) >= TRDT_SOUND + 4 else 0
        if sound:
            out[rec.form_id] = sound
    return out


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


class Radio:
    """FO4 transmitters and programs for FNV's Pip-Boy stations, written through a cell builder.

    See: docs/fork/fo4_radio.md#programming
    """

    def __init__(self, builder, export_dir: Path):
        """Stations of `export_dir` and Fallout4.esm's transmitter template, for `builder`."""
        self.builder, self.stations, self.made = builder, pipboy_stations(export_dir), set()
        self.template = next(subrecords(r.body) for r, _ in walk(builder.fo4, b'ACTI')
                             if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == TRANSMITTER)
        self.refs = {}
        for ref in export_records(export_dir, 'REFR'):
            if int(ref.get('NAME', '0'), 16) in self.stations:
                self.refs.setdefault(int(ref['NAME'], 16), []).append(ref['FormID'])
        self.sounds = {int(r['FormID'], 16): r.get('FNAM.Filename', '') for r in export_records(export_dir, 'SOUN')}
        self.export_dir = export_dir

    def form_map(self) -> dict:
        """{FNV station: its FO4 transmitter base} for the lines' GetIsID on their station."""
        return {fnv: self.builder.fnv_id(fnv) for fnv in self.stations if self.builder.fnv_id(fnv) in self.made}

    def program(self, rec: dict, quest: int, form_map: dict, ref_ids: dict) -> 'tuple | None':
        """(aliases, topic blobs, scenes, quest scripts) adding FNV quest `rec`'s radio program to its FO4 quest
        `quest`, when it is a built station's whose lines are all songs (playlist); None, counted, otherwise."""
        station = station_of(rec, self.stations)
        host = next((ref_ids[r] for r in self.refs.get(station, ()) if r in ref_ids), None) if station else None
        lines = [r for r in self.builder.say.infos.get(rec['FormID'].upper(), []) if r.get('DATA.DialogType') == RADIO_LINE]
        if host is None or not lines:
            return None
        songs = [self._song_of(line) for line in lines]
        if not all(songs):
            self.builder.counts['radio program left out (spoken lines; FNV method off)'] += 1
            return None
        return self._playlist(rec, quest, form_map, (station, host), list(zip(lines, songs)))

    def _playlist(self, rec: dict, quest: int, form_map: dict, where: tuple, songs: list) -> 'tuple | None':
        """program() of a songs-only station on vanilla's music scene: a phase saying the pick topic (FNV's lines,
        each setting CurrentSong), then a phase per song gated on it playing its SNDR; TES4_RadioPlaylist starts
        the scene and restarts it on a timer."""
        station, host = where
        speakers = Speakers(self.builder, rec, self.stations[station])
        picks, sounds, gates = [], [], []
        for line, (soun, file) in songs:
            made = self._line(line, form_map, speakers, quest, len(picks) + 1)
            if made:
                picks.append(made)
                sounds.append(self.builder.sounds.song(soun, file))
                gates.append(playing(quest, len(picks)))
        if not picks:
            return None
        topic, scene = self.builder.new_id(f'DIAL radio {rec["FormID"]} pick'), self.builder.new_id(f'SCEN radio {rec["FormID"]}')
        blob = pack_topic(R.pack_dial(topic, f'FNV_{rec["EditorID"]}_Pick', quest, TOPIC, len(picks)), topic, picks)
        record = pack_scene(scene, f'FNV_{rec["EditorID"]}Playlist', quest, [topic] + [0] * len(sounds), PLAYLIST_FLAGS,
                            HOST_ALIAS, 0, sounds=[0] + sounds, conditions=[b''] + gates)
        self.builder.scripts.used += [s for s in (PLAYLIST_SCRIPT, SONG_SCRIPT) if s not in self.builder.scripts.used]
        self.builder.counts['radio playlists'] += 1
        self.builder.counts['radio songs'] += len(sounds)
        return ([(HOST_ALIAS, 'Host', host, None, self._display(rec, self.stations[station]))], [blob], [record],
                [(PLAYLIST_SCRIPT, {'Program': scene}, {})])

    def _song_of(self, line: dict) -> 'tuple | None':
        """(FNV SOUN, its file under Data\\Sound) of a song line; None for a spoken one."""
        soun = song_sounds().get(int(line['FormID'], 16), 0)
        path = song_file(self.export_dir, self.sounds.get(soun, ''))
        return (soun, path.relative_to(self.export_dir / 'sound').as_posix()) if path else None

    def _display(self, quest: dict, station: dict) -> int:
        """The Host alias's display name: a message naming the station, the name the Pip-Boy lists."""
        fid = self.builder.new_id(f'MESG radio {quest["FormID"]}')
        name = station.get('FULL', '')
        self.builder.writer.add_record('MESG', pack_mesg(fid, f'FNV_{quest["EditorID"]}Display', name, name, 0, []))
        return fid

    def _line(self, line: dict, form_map: dict, speakers, quest: int, song: int) -> bytes:
        """FNV radio `line` as an FO4 pick line said by the speaker of its voice (Speakers; FNV's Random flags
        kept), setting the playlist's CurrentSong to `song` as it begins; b'' with no speaker or a condition not
        converting."""
        voice = recorded_voices(self.export_dir).get(int(line['FormID'], 16), speakers.station_voice)
        speaker = speakers.of(voice)
        if speaker is None:
            self.builder.counts['radio line left out (no voice type)'] += 1
            return b''
        sets = (SONG_SCRIPT, {'Playlist': quest}, {'Song': ('int', song)})
        return self.builder.say.info(line, form_map, flags=int(line.get('DATA.Flags', 0)) & RANDOM_FLAGS,
                                     speaker=speaker, owner=quest, place=f'radio {line["FormID"]}', helpers=(sets,))

    def base(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 transmitter of FNV station `rec` (FormID `fnv`), written once; None, counted, for another
        talking activator."""
        frequency = frequency_of(fnv, self.refs) if fnv in self.refs else None
        if frequency is None:
            self.builder.counts['talking activator left out (not a Pip-Boy station, or no frequency free)'] += 1
            return None
        fid = self.builder.fnv_id(fnv)
        if fid not in self.made:
            self.made.add(fid)
            own = {b'EDID': f'FNV_{rec["EditorID"]}', b'FULL': rec.get('FULL', '')}
            script = pack_subrecord('VMAD', object_scripts([(STATION_SCRIPT, {}, {'Frequency': ('float', frequency)})]))
            body = pack_string_subrecord('EDID', own[b'EDID']) + script + b''.join(
                pack_string_subrecord(t.decode(), own[t]) if t in own else pack_subrecord(t.decode(), d)
                for t, d in self.template if t != b'EDID')
            self.builder.writer.add_record('ACTI', pack_fo4_record('ACTI', fid, 0, body))
            self.builder.counts['radio transmitters'] += 1
        return fid

    def xrdo(self, ref: dict) -> bytes:
        """The XRDO subrecord of a placed FNV station reference; b'' for any other reference."""
        station = int(ref['NAME'], 16)
        radio = radio_data().get(int(ref['FormID'], 16))
        if station not in self.stations or radio is None or self.builder.fnv_id(station) not in self.made:
            return b''
        return pack_subrecord('XRDO', xrdo_data(frequency_of(station, self.refs), radio))


def playing(quest: int, song: int) -> bytes:
    """A playlist phase's start condition: the station quest's CurrentSong is `song`."""
    return R.pack_ctda(0, float(song), C.FO4.index(VM_QUEST_VARIABLE), quest) + pack_string_subrecord('CIS2', CURRENT_SONG)
