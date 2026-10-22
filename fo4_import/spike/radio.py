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
outside the Pip-Boy's band (LOUNGE_FREQUENCIES). TES4_RadioStation names
the frequency on the base. Everywhere is Ignores Distance Checks, a radius
a weak signal from where FNV's static begins out to the radius. An FNV
activator naming a station (RNAM) is a receiver on its frequency. Programs
are radio_program's.

See: docs/fork/fo4_radio.md#transmitters
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import source_esm
from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.activators import fnv_links
from fo4_import.spike.radio_program import Program
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
#: The script a transmitter base carries, naming its frequency for TES4_Radio.Heard.
STATION_SCRIPT = 'TES4_RadioStation'
#: A receiver's volume (RADR), as RadioDiamondCityReceiverOff's.
RECEIVER_VOLUME = 1.0
#: A receiver's sound model: SOMMonoWorldRadio_02500_Jukebox (full to 350, silent at 2500), not the default 150 to 1600.
RECEIVER_OUTPUT = 0x23E390
#: Exported reference position keys.
POSITION = ('PosX', 'PosY', 'PosZ')
#: FNV condition GetIsID (a station quest's own condition names its talking activator).
GET_IS_ID = 72


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


class Radio:
    """FO4 transmitters, receivers and programs for FNV's radio stations, written through a cell builder.

    See: docs/fork/fo4_radio.md#programming
    """

    def __init__(self, builder, export_dir: Path):
        """Stations of `export_dir` and Fallout4.esm's transmitter template, for `builder`."""
        self.builder, self.stations, self.made = builder, radio_stations(export_dir), set()
        self.template = next(subrecords(r.body) for r, _ in walk(builder.fo4, b'ACTI')
                             if (first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode() == TRANSMITTER)
        self.refs = {}
        for ref in export_records(export_dir, 'REFR'):
            if int(ref.get('NAME', '0'), 16) in self.stations:
                self.refs.setdefault(int(ref['NAME'], 16), []).append(ref['FormID'])
        self.sounds = {int(r['FormID'], 16): r.get('FNAM.Filename', '') for r in export_records(export_dir, 'SOUN')}
        self.export_dir, self.stations_of = export_dir, fnv_links(source_esm(), b'ACTI', b'RNAM')

    def frequency(self, station: int) -> 'float | None':
        """A placed station's frequency: Pip-Boy slot, or a lounge one off the band."""
        kind = pipboy(self.stations[station])
        placed = {fid: refs for fid, refs in self.refs.items() if pipboy(self.stations[fid]) == kind}
        return frequency_of(station, placed, FREQUENCIES if kind else LOUNGE_FREQUENCIES)

    def receiver(self, fnv: int) -> bytes:
        """The RADR data of FNV activator `fnv` when it names a placed station (RNAM): a receiver on that station's
        frequency, off until activated, on vanilla's jukebox sound model; b'' otherwise."""
        station = self.stations_of.get(fnv)
        if station not in self.refs:
            return b''
        self.builder.counts['radio receivers'] += 1
        return struct.pack('<IffBB', RECEIVER_OUTPUT, self.frequency(station), RECEIVER_VOLUME, 0, 0)

    def form_map(self) -> dict:
        """{FNV station: its FO4 transmitter base} for the lines' GetIsID on their station."""
        return {fnv: self.builder.fnv_id(fnv) for fnv in self.stations if self.builder.fnv_id(fnv) in self.made}

    def program(self, rec: dict, quest: int, form_map: dict, ref_ids: dict) -> 'tuple | None':
        """(aliases, topic blobs, scenes, quest scripts) adding FNV quest `rec`'s radio program (radio_program) to its
        FO4 quest `quest` when it is a built station's; None otherwise."""
        station = station_of(rec, self.stations)
        host = next((ref_ids[r] for r in self.refs.get(station, ()) if r in ref_ids), None) if station else None
        if host is None:
            return None
        return Program(self, rec, quest, self.stations[station]).build(form_map, host, self.stations[station])

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
