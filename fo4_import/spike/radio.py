"""FNV radio stations as Fallout 4 transmitters and receivers, for the cell spike.

An FNV station is a talking activator (TACT) flagged Radio Station, placed
once; the Pip-Boy lists those not flagged Non-Pipboy, which only placed
radios play (the casino and Tops lounges). Its reference's XRDO (dropped by
the export, read from FalloutNV.esm) gives its reach: Everywhere, or a
radius around the reference or its position reference, static over the
last part of it. Fallout 4's Pip-Boy lists the transmitters in reach:
references of an activator like Fallout4.esm's RadioTransmitter, with XRDO
(frequency, weak-signal distances, Ignores Distance Checks).

Each station becomes a copy of RadioTransmitter named for it, on FNV's
FormID. A Pip-Boy station's references are placed persistent in the built
worldspace's persistent cell (one in an interior or past the build too, the
first world built taking interior ones), at the position reference when
there is one, on a free Pip-Boy frequency (FREQUENCIES, in station FormID
order); a Non-Pipboy station's stay where FNV places them, on a frequency
outside the Pip-Boy's band (LOUNGE_FREQUENCIES). F3NV_RadioStation names
the frequency on the base. Everywhere is Ignores Distance Checks, a radius
a weak signal from where FNV's static begins out to the radius. An FNV
activator naming a station (RNAM) is a receiver on its frequency. Programs
are radio_program's.

See: docs/fork/fo4_radio.md#transmitters
"""

import functools
import re
import struct
from pathlib import Path

from fo4_import.base.install import source_walk
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.base.writer import pack_fo4_record, pack_quest
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.activators import fnv_links
from fo4_import.spike.quest import START_GAME
from fo4_import.spike.radio_program import Program, ends_run, radio_lines
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
#: Non-Pipboy frequencies: off the 80-110 band, 1.0 or more from vanilla's (0-4, 11, 22, 31-32, 42-44, 60-77, 303).
LOUNGE_FREQUENCIES = (5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 13.0, 13.5, 14.0, 14.5)
#: The script a transmitter base carries, naming its frequency for F3NV_Radio.Heard.
STATION_SCRIPT = 'F3NV_RadioStation'
#: A receiver's volume (RADR), as RadioDiamondCityReceiverOff's.
RECEIVER_VOLUME = 1.0
#: A receiver's sound model: SOMMonoWorldRadio_02500_Jukebox (full to 350, silent at 2500), not the default 150 to 1600.
RECEIVER_OUTPUT = 0x23E390
#: Exported reference position keys.
POSITION = ('PosX', 'PosY', 'PosZ')
#: FNV condition GetIsID (a station quest's own condition names its talking activator).
GET_IS_ID = 72
#: `<ref>.StartRadioConversation` in a script line's code (before any `;` comment).
START_CALL = re.compile(r'^[^;\n]*?\b(\w+)\.startradioconversation\b', re.I | re.M)
#: `SetNPCRadio <flag> <station ref>` in a script line's code: an NPC plays the station.
NPC_RADIO_CALL = re.compile(r'^[^;\n]*?\bsetnpcradio\s+\S+\s+(\w+)', re.I | re.M)
#: The receiver SetNPCRadio places at an actor: DN070_JamaicaPlainDummyRadio's invisible marker model and bounds.
NPC_RECEIVER_MODEL, NPC_RECEIVER_BOUNDS = 'markers\\MarkerDummy01.nif', (-66, -66, -66, 66, 66, 66)


def radio_stations(export_dir: Path) -> dict:
    """{FNV FormID: TACT record} of FNV's radio stations, Pip-Boy and Non-Pipboy."""
    return {int(r['FormID'], 16): r for r in export_records(export_dir, 'TACT')
            if int(r.get('RecordFlags', 0)) & RADIO_STATION}


def pipboy(rec: dict) -> bool:
    """Whether FNV station `rec` is one the Pip-Boy lists (not Non-Pipboy)."""
    return not int(rec.get('RecordFlags', 0)) & NON_PIPBOY


def pipboy_stations(export_dir: Path) -> dict:
    """{FNV FormID: TACT record} of FNV's Pip-Boy radio stations."""
    return {fid: r for fid, r in radio_stations(export_dir).items() if pipboy(r)}


@functools.cache
def radio_data() -> dict:
    """{FNV reference: (radius, range type, static %, position ref)}: FNV XRDO."""
    return {rec.form_id: struct.unpack_from('<fIfI', data)
            for rec, _ in source_walk(b'REFR') for data in [first_sub(rec.body, b'XRDO')] if data}


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


def frequency_of(fnv_station: int, stations: dict, slots: tuple = FREQUENCIES) -> 'float | None':
    """`fnv_station`'s `slots` entry, in `stations`' FormID order; None past them."""
    order = sorted(stations).index(fnv_station)
    return slots[order] if order < len(slots) else None


def xrdo_data(frequency: float, radio: tuple) -> bytes:
    """FO4 XRDO of a station reference on `frequency` with FNV `radio` data (radio_data)."""
    radius, kind, static, _ = radio
    if kind != RADIUS or radius <= 0:
        return struct.pack('<3fI', frequency, 0.0, 0.0, IGNORES_DISTANCE)
    return struct.pack('<3fI', frequency, radius * (1.0 - static / 100.0), radius, 0)


def _named_stations(rec: dict, stations: dict) -> list:
    """The stations FNV record `rec`'s GetIsID conditions name, in order."""
    out, i = [], 0
    while f'Condition[{i}].Raw' in rec:
        raw = bytes.fromhex(rec[f'Condition[{i}].Raw'])
        i += 1
        func, form = struct.unpack_from('<II', raw, 8) if len(raw) >= 16 else (0, 0)
        out += [form] if func == GET_IS_ID and form in stations else []
    return out


def lines_by_station(lines: list, stations: dict) -> dict:
    """{station: its lines} of radio `lines` whose GetIsID conditions name exactly one of `stations`."""
    out = {}
    for line in lines:
        named = set(_named_stations(line, stations))
        if len(named) == 1:
            out.setdefault(named.pop(), []).append(line)
    return out


def station_of(quest: dict, stations: dict, lines: list = ()) -> 'int | None':
    """The station whose lines FNV quest `quest` holds: its quest condition GetIsID's talking activator, else the
    one station its radio `lines` name (Hanlon's recording, Lily's grandkids').
    See: docs/fork/fo4_radio.md#line-stations
    """
    own = _named_stations(quest, stations)
    named = {form for line in lines for form in _named_stations(line, stations)}
    return own[0] if own else (named.pop() if len(named) == 1 else None)


class Radio:
    """FO4 transmitters, receivers and programs for FNV's radio stations, written through a cell builder.

    See: docs/fork/fo4_radio.md#programming
    """

    def __init__(self, builder, export_dir: Path):
        """Stations of `export_dir` and Fallout4.esm's transmitter template, for `builder`."""
        self.builder, self.stations, self.made = builder, radio_stations(export_dir), set()
        self.template = next(subrecords(r.body) for r, _ in walk(builder.fo4, b'ACTI')
                             if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == TRANSMITTER)
        self.refs, self.receivers, named = {}, {}, {}
        self.export_dir, self.stations_of = export_dir, fnv_links(None, b'ACTI', b'RNAM')
        for ref in export_records(export_dir, 'REFR'):
            base = int(ref.get('NAME', '0'), 16)
            if base in self.stations:
                self.refs.setdefault(base, []).append(ref['FormID'])
                named[(ref.get('EditorID') or '').lower()] = base
            elif base in self.stations_of:
                self.receivers.setdefault(self.stations_of[base], []).append(ref['FormID'])
        texts = [r.get('SCTX', '') for r in export_records(export_dir, 'SCPT')]
        self.started, self.npc_radios = ({named[m.lower()] for text in texts for m in call.findall(text)
                                          if m.lower() in named} for call in (START_CALL, NPC_RADIO_CALL))
        self.sounds = {int(r['FormID'], 16): r.get('FNAM.Filename', '') for r in export_records(export_dir, 'SOUN')}

    def frequency(self, station: int) -> 'float | None':
        """A placed station's frequency: Pip-Boy slot, or a lounge one off the band."""
        kind = pipboy(self.stations[station])
        placed = {fid: refs for fid, refs in self.refs.items() if pipboy(self.stations[fid]) == kind}
        return frequency_of(station, placed, FREQUENCIES if kind else LOUNGE_FREQUENCIES)

    def receiver(self, fnv: int) -> bytes:
        """The RADR data of FNV activator `fnv` when it names a placed station (RNAM): a receiver on that station's
        frequency, off until activated, on vanilla's jukebox sound model; b'' otherwise, or when the station got
        no free frequency (base)."""
        station = self.stations_of.get(fnv)
        if station not in self.refs or self.frequency(station) is None:
            return b''
        self.builder.counts['radio receivers'] += 1
        return self._radr(station)

    def _radr(self, station: int) -> bytes:
        """RADR on `station`'s frequency (one it has), off until switched on, jukebox sound."""
        return struct.pack('<IffBB', RECEIVER_OUTPUT, self.frequency(station), RECEIVER_VOLUME, 0, 0)

    def npc_receiver(self, station: int) -> int:
        """The receiver activator a script's SetNPCRadio places at an actor to play placed `station` (an invisible
        marker, as vanilla's dummy radios); 0 when no script names the station so, or it got no free frequency.
        See: docs/fork/fo4_radio.md#npc-radio
        """
        if station not in self.npc_radios or station not in self.refs or self.frequency(station) is None:
            return 0
        rec = self.stations[station]
        fid = self.builder.new_id(f'ACTI radio npc receiver {station:08X}')
        if fid in self.made:
            return fid
        self.made.add(fid)
        self.builder.writer.add_record('ACTI', R.pack_acti(
            fid, f'FNV_{rec["EditorID"]}NPCReceiver', '', NPC_RECEIVER_MODEL, NPC_RECEIVER_BOUNDS, b'', '', 0,
            self._radr(station)))
        self.builder.counts['radio NPC receivers'] += 1
        return fid

    def form_map(self) -> dict:
        """{FNV station: its FO4 transmitter base} for the lines' GetIsID on their station."""
        return {fnv: self.builder.fnv_id(fnv) for fnv in self.stations if self.builder.fnv_id(fnv) in self.made}

    def program(self, rec: dict, quest: int, form_map: dict, ref_ids: dict) -> 'tuple | None':
        """(aliases, topic blobs, scenes, quest scripts) adding FNV quest `rec`'s radio program (radio_program) to its
        FO4 quest `quest` when it is a built station's; None otherwise. A quest whose lines name several stations
        writes each its own quest instead (_acts)."""
        lines = radio_lines(self.builder.say, rec)
        station = station_of(rec, self.stations, lines)
        if station is None:
            self._acts(rec, lines, form_map, ref_ids)
            return None
        return self._built(rec, quest, station, lines, form_map, ref_ids)

    def _built(self, rec: dict, quest: int, station: int, lines: list, form_map: dict, ref_ids: dict):
        """Program.build of `station`'s `lines` on FO4 `quest`, hosted by its built reference; None without one.
        It is on demand, with its built receivers, when a script starts the station, the Pip-Boy does not list it
        and a line ends its run; it has an NPC receiver when a script's SetNPCRadio names the station.
        See: docs/fork/fo4_radio.md#start-radio-conversation
        """
        host = next((ref_ids[r] for r in self.refs.get(station, ()) if r in ref_ids), None)
        if host is None:
            return None
        on_demand = (station in self.started and not pipboy(self.stations[station])
                     and any(ends_run(line) for line in lines))
        receivers = [ref_ids[r] for r in self.receivers.get(station, ()) if r in ref_ids] if on_demand else []
        self.builder.counts['radio programs on demand'] += on_demand
        return Program(self, rec, quest, self.stations[station], lines, on_demand).build(
            form_map, host, self.stations[station], (receivers, self.npc_receiver(station)))

    def _acts(self, rec: dict, lines: list, form_map: dict, ref_ids: dict) -> None:
        """A start-enabled quest per station FNV quest `rec`'s radio `lines` name (the Tops stage acts), its forms
        keyed by the quest's FormID and the station's.
        See: docs/fork/fo4_radio.md#stage-acts
        """
        for station, own in sorted(lines_by_station(lines, self.stations).items()):
            act = {**rec, 'FormID': f'{rec["FormID"]} {station:08X}',
                   'EditorID': f'{rec["EditorID"]}_{self.stations[station]["EditorID"]}'}
            quest = self.builder.new_id(f'QUST radio {act["FormID"]}')
            built = self._built(act, quest, station, own, form_map, ref_ids)
            if built:
                aliases, topics, scenes, runners = built
                vmad = quest_fragments('', [], scripts=list(runners))
                record = R.pack_fnv_quest(quest, f'FNV_{act["EditorID"]}', '', 0, vmad, [], [], aliases,
                                          start=bool(int(rec.get('DATA.Flags', 0)) & START_GAME))
                self.builder.writer.add_record('QUST', pack_quest(record, quest, [], topics, scenes))
                self.builder.counts['radio act quests'] += 1

    def base(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 transmitter of FNV station `rec` (FormID `fnv`), written once; None, counted, for another
        talking activator."""
        frequency = self.frequency(fnv) if fnv in self.refs else None
        if frequency is None:
            self.builder.counts['talking activator left out (not a radio station, or no frequency free)'] += 1
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
        return pack_subrecord('XRDO', xrdo_data(self.frequency(station), radio))
