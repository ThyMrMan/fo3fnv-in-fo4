"""FNV music as Fallout 4's: media sets as music types, audio markers as cell music and music regions.

FNV plays music from audio markers (MMRK references): each names a media
location controller (CNAM, an ALOC) over a radius (XRDS). The controller
picks media sets (MSET) by the player's standing; a location set layers
low, mid and high stems by distance from the marker (outer, middle, inner),
day and night; a dungeon set has explore, suspense and battle loops. A cell's
own music type (XCMO, a MUSC) names a file, or one of the default folders
FNV ships no files for. FO4 plays a music type (MUSC) made of tracks (MUST):
single files, palettes, silence, picked by conditions.

- A controller takes its first location set, else its first neutral set;
  standing variants, battle and incidental sets are left out (FO4's own
  combat music plays). One with neither is silent.
- A location set becomes a music type of its outer layer, the stem heard
  across the whole radius: a day track and a night track (GetCurrentTime
  6 to 20, as Fallout4.esm's explore tracks). A dungeon set plays its
  explore loop. A MUSC naming a file plays it; one naming a folder, or none,
  is silence.
- An interior's music is its audio marker's, else its XCMO's. Outdoors each
  marker becomes a music region (a 16-sided polygon of its radius, priority
  rising as radii shrink, so a town's zone wins over the desert around it),
  listed by the cells it reaches; the worldspace's own music is silence.

Music files convert to Data\\Music\\FNV with the sound jobs. Media sets,
controllers and markers are read from FalloutNV.esm (the export decodes none).

See: docs/fork/fo4_pipeline.md#music
"""

import math
import struct

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: FO4 MUST track types (CNAM).
SINGLE, SILENT = 0x6ED7E048, 0xA1A9C4D5
#: FNV media set types (NAM1): location, dungeon.
LOCATION, DUNGEON = 1, 2
#: A location set's outer layers (day, night) and their enable flags (PNAM); a dungeon set's explore loop.
OUTER = ((b'NAM2', 0x01), (b'NAM5', 0x08))
EXPLORE = b'NAM3'
#: A controller's location sets, then its neutral sets.
SET_TAGS = (b'LNAM', b'HNAM')
#: Day and night as Fallout4.esm's explore tracks test them: (operator and OR flags, hour) pairs.
DAY = ((0x60, 6.0), (0xA0, 20.0))
NIGHT = ((0x81, 6.0), (0x41, 20.0))
#: FO4 MUSC defaults (Fallout4.esm's MUSDungeonA): cycle tracks, priority 80, fade 4 s.
MUSC_FLAGS, PRIORITY, FADE = 0x04, 80, 4.0
#: A music region's sides, its RDAT type (sound) and the priority of the widest zone.
SIDES, SOUND, BASE_PRIORITY = 16, 7, 10
#: FNV's audio marker (an engine form) and an exterior cell's size.
AUDIO_MARKER, CELL_UNITS = 0x23, 4096.0
#: ledger sites: a music type (key: FNV MSET, MUSC or 'silence'), a track (key: its file), a zone (key: the marker).
MUSIC_SITE, TRACK_SITE, ZONE_SITE = 'FNV music', 'FNV music track', 'FNV music zone'


def music_of(builder) -> 'Music':
    """`builder`'s Music, made on first use."""
    builder.music = builder.music or Music(builder)
    return builder.music


def _cell_of(stack) -> 'int | None':
    """The FormID of the cell a walk's group stack is in."""
    label = next((g.label for g in reversed(stack.groups) if g.type in (6, 8, 9, 10)), None)
    return int.from_bytes(label, 'little') if isinstance(label, bytes) else label


def polygon(x: float, y: float, radius: float) -> bytes:
    """RPLD points of a SIDES-gon of `radius` around (x, y)."""
    return b''.join(struct.pack('<2f', x + radius * math.cos(2 * math.pi * i / SIDES),
                                y + radius * math.sin(2 * math.pi * i / SIDES)) for i in range(SIDES))


def reaches(grid: tuple, x: float, y: float, radius: float) -> bool:
    """Whether exterior cell `grid` comes within `radius` of (x, y)."""
    nx = min(max(x, grid[0] * CELL_UNITS), (grid[0] + 1) * CELL_UNITS)
    ny = min(max(y, grid[1] * CELL_UNITS), (grid[1] + 1) * CELL_UNITS)
    return math.hypot(nx - x, ny - y) <= radius


class Music:
    """FO4 music types, tracks and music regions for FNV's, each written once, through a cell builder."""

    def __init__(self, builder):
        """Read FalloutNV.esm's media sets, controllers and audio markers, and the export's music types."""
        self.builder, self.made, self.tracks = builder, {}, {}
        self.fnv = {r.form_id: list(subrecords(r.body)) for r, _ in source_walk(b'MSET', b'ALOC')}
        self.musc = {int(r['FormID'], 16): r for r in export_records(builder.export_dir, 'MUSC')}
        self.markers = {}
        for rec, stack in source_walk(b'REFR'):
            subs = dict(subrecords(rec.body))
            if b'MMRK' in subs and struct.unpack('<I', subs[b'NAME'])[0] == AUDIO_MARKER:
                x, y = struct.unpack_from('<2f', subs[b'DATA'])
                radius = struct.unpack('<f', subs[b'XRDS'])[0] if b'XRDS' in subs else 0.0
                self.markers.setdefault(_cell_of(stack), []).append(
                    (rec.form_id, x, y, radius, struct.unpack('<I', subs[b'CNAM'])[0]))

    def silence(self) -> int:
        """The silent music type, written once."""
        if 'silence' not in self.made:
            track = self._track('silence', SILENT, '', ())
            self.made['silence'] = self._musc(self.builder.writer.derive_formid(MUSIC_SITE, 'silence'),
                                              'FNV_MusicSilence', [track])
        return self.made['silence']

    def interior(self, fnv_cell: int, xcmo: int) -> bytes:
        """FNV interior `fnv_cell`'s XCMO: its audio marker's music, else MUSC `xcmo`'s."""
        markers = self.markers.get(fnv_cell)
        music = self.controller(markers[0][4]) if markers else self.music_type(xcmo)
        return R.pack_u32('XCMO', music)

    def music_type(self, fnv: int) -> int:
        """FNV MUSC `fnv`'s FO4 music type: its file as a track, else silence."""
        rec = self.musc.get(fnv, {})
        name = rec.get('FNAM.FileName', '')
        if not name or name.endswith('\\'):
            return self.silence()
        if fnv not in self.made:
            track = self._file_track(name, ())
            self.made[fnv] = self._musc(self.builder.fnv_id(fnv), f'FNV_{rec["EditorID"]}', [track])
        return self.made[fnv]

    def controller(self, fnv: int) -> int:
        """FNV ALOC `fnv`'s music: its first location or neutral set, else silence."""
        subs = self.fnv.get(fnv, [])
        sets = [struct.unpack('<I', v)[0] for tag in SET_TAGS for t, v in subs if t == tag]
        return self.media_set(sets[0]) if sets else self.silence()

    def media_set(self, fnv: int) -> int:
        """FNV MSET `fnv`'s FO4 music type, written once (module docstring); silence when it has no track."""
        if fnv not in self.made:
            subs = dict(self.fnv.get(fnv, []))
            kind = struct.unpack('<i', subs[b'NAM1'])[0] if b'NAM1' in subs else -1
            tracks = self._layers(subs) if kind == LOCATION else self._explore(subs) if kind == DUNGEON else []
            edid = 'FNV_' + subs.get(b'EDID', b'').rstrip(b'\0').decode('cp1252')
            self.made[fnv] = self._musc(self.builder.fnv_id(fnv), edid, tracks) if tracks else self.silence()
        return self.made[fnv]

    def _layers(self, subs: dict) -> list:
        """A location set's outer day and night tracks (when enabled), each under its time of day."""
        enabled = subs.get(b'PNAM', b'\0')[0]
        files = [(subs.get(tag, b'').rstrip(b'\0').decode('cp1252'), when)
                 for (tag, flag), when in zip(OUTER, (DAY, NIGHT)) if enabled & flag]
        return [self._file_track(name, when) for name, when in files if name]

    def _explore(self, subs: dict) -> list:
        """A dungeon set's explore loop as its one track (none without it)."""
        name = subs.get(EXPLORE, b'').rstrip(b'\0').decode('cp1252')
        return [self._file_track(name, ())] if name else []

    def _file_track(self, name: str, when: tuple) -> int:
        """The single track playing FNV music file `name` (under Data\\Music) under conditions `when`."""
        stem = name.rsplit('.', 1)[0].replace('/', '\\')
        source = export_file(self.builder.export_dir, 'music', name.replace('\\', '/'))
        self.builder.sounds.jobs.append((source, self.builder.data_dir / 'Music' / 'FNV' / f'{stem}.xwm', None))
        return self._track(f'{stem}|{when}', SINGLE, f'data\\Music\\FNV\\{stem}.wav', when)

    def _track(self, key: str, kind: int, path: str, when: tuple) -> int:
        """A MUST of type `kind` playing `path` ('' for none) under conditions `when`, written once per `key`."""
        if key not in self.tracks:
            fid = self.builder.writer.derive_formid(TRACK_SITE, key)
            edid = f'FNV_Track_{fid & 0xFFFFFF:06X}'
            subs = pack_subrecord('EDID', edid.encode() + b'\0') + R.pack_u32('CNAM', kind)
            subs += pack_subrecord('ANAM', path.encode('cp1252') + b'\0') if path else b''
            subs += R.pack_u32('CITC', len(when)) if when else b''
            subs += b''.join(R.pack_ctda(op, hour, C.FO4.index('GetCurrentTime')) for op, hour in when)
            self.builder.writer.add_record('MUST', pack_fo4_record('MUST', fid, 0, subs))
            self.builder.counts['music tracks'] += 1
            self.tracks[key] = fid
        return self.tracks[key]

    def _musc(self, fid: int, edid: str, tracks: list) -> int:
        """Write a music type `edid` cycling `tracks` on `fid`; `fid`."""
        subs = pack_subrecord('EDID', edid.encode('cp1252') + b'\0') + R.pack_u32('FNAM', MUSC_FLAGS)
        subs += pack_subrecord('PNAM', struct.pack('<HH', PRIORITY, 0)) + pack_subrecord('WNAM', struct.pack('<f', FADE))
        subs += pack_subrecord('TNAM', struct.pack(f'<{len(tracks)}I', *tracks))
        self.builder.writer.add_record('MUSC', pack_fo4_record('MUSC', fid, 0, subs))
        self.builder.counts['music types'] += 1
        return fid

    def zones(self, world: int, persistent_cell: int, cells: dict) -> dict:
        """{FNV cell: [FO4 music regions]} of exterior `cells` {grid: FNV cell} of FO4 worldspace `world`, each
        outdoor audio marker written as a music region; persistent ones (in `persistent_cell`) by position."""
        markers = [m for c in (*cells.values(), persistent_cell) for m in self.markers.get(c, [])
                   if any(reaches(g, m[1], m[2], m[3]) for g in cells)]
        out = {}
        for rank, (ref, x, y, radius, aloc) in enumerate(sorted(markers, key=lambda m: -m[3])):
            region = self._zone(world, ref, (x, y, radius), self.controller(aloc), BASE_PRIORITY + rank)
            for grid, cell in cells.items():
                if reaches(grid, x, y, radius):
                    out.setdefault(cell, []).append(region)
        return out

    def _zone(self, world: int, ref: int, circle: tuple, music: int, priority: int) -> int:
        """Write the music region of audio marker `ref`: `circle` (x, y, radius) playing `music`; its FormID."""
        fid = self.builder.writer.derive_formid(ZONE_SITE, f'{ref:08X}')
        subs = pack_subrecord('EDID', f'FNV_MusicZone{ref:08X}'.encode() + b'\0') + R.pack_u32('RCLR', 0x00C80F0A)
        subs += R.pack_u32('WNAM', world) + R.pack_u32('RPLI', 0) + pack_subrecord('RPLD', polygon(*circle))
        subs += pack_subrecord('RDAT', struct.pack('<IBB2x', SOUND, 1, min(priority, 255))) + R.pack_u32('RDMO', music)
        self.builder.writer.add_record('REGN', pack_fo4_record('REGN', fid, 0, subs))
        self.builder.counts['music regions'] += 1
        return fid
