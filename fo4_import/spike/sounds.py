"""FNV sounds (SOUN) as Fallout 4 sound descriptors and sound markers, for the cell spike.

An FNV SOUN names a sound file, or a folder from which one file is picked at
random, with its attenuation and flags; doors, containers and activators name
SOUNs, and placed SOUNs play ambience. Fallout 4 splits this: a sound
descriptor (SNDR) holds the files (one picked at random) and how they play;
doors (SNAM, ANAM), containers (SNAM, QNAM) and activators (SNAM) name SNDRs;
a sound marker (SOUN: EDID, OBND, SDSC, as 179 vanilla ones) places one.
Each FNV SOUN becomes an SNDR copied from the vanilla descriptor of its kind
(type, category, output model, playback flags, priority): a looping one
(FNV flag Loop) from AMBSteamVaultPipeA, any other from
DRSWoodSingleLightLoadAOpen. Its files are FNV's, converted to .xwm under
Sound\\FX\\FNV and named .wav, as vanilla names its .xwm files. FormIDs are
hashed from FNV's, so no record moves.

See: docs/fork/fo4_spikes.md#spike-4-sounds
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.text_reader import parse_export_file
from tes5_import.base.writer import pack_subrecord

#: FNV SOUN SNDD flag Loop.
LOOP = 0x10
#: Vanilla descriptors the converted ones copy: a looping one, and a one-shot (doors, containers, the rest).
LOOP_TEMPLATE, ONE_SHOT_TEMPLATE = 'AMBSteamVaultPipeA', 'DRSWoodSingleLightLoadAOpen'
#: The template fields an SNDR keeps: type, category, output model, playback flags, priority and attenuation.
KEPT = (b'CNAM', b'GNAM', b'ONAM', b'LNAM', b'BNAM')
#: derive_formid sites (key: the FNV SOUN's FormID).
SNDR_SITE, SOUN_SITE = 'FNV SNDR', 'FNV SOUN'
#: The bounds of vanilla's sound markers.
MARKER_BOUNDS = (-27, -27, -12, 27, 27, 12)
#: The folder under Data\Sound\FX holding the converted FNV sounds.
FOLDER = 'FNV'
AUDIO = ('.wav', '.ogg')


class Sounds:
    """FNV SOUNs made into FO4 SNDRs and sound markers once each; `jobs` are the audio conversions to run."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV's SOUNs; the templates come from `builder`'s Fallout4.esm."""
        self.builder, self.export_dir, self.jobs, self.made, self.markers = builder, export_dir, [], {}, {}
        self.records = {int(r['FormID'], 16): r for r in parse_export_file(str(export_dir / 'SOUN.txt'))}
        self.templates = {}
        for rec, _ in walk(builder.fo4, b'SNDR'):
            subs = dict(subrecords(rec.body))
            name = subs.get(b'EDID', b'').rstrip(b'\0').decode()
            if name in (LOOP_TEMPLATE, ONE_SHOT_TEMPLATE):
                self.templates[name] = subs

    def descriptor(self, fnv: int) -> int:
        """The FO4 SNDR of FNV SOUN `fnv`, made once; 0 when it is not an FNV SOUN or has no sound file."""
        if fnv not in self.made:
            rec = self.records.get(fnv)
            files = self._files(rec) if rec else []
            self.made[fnv] = self._write(fnv, rec, files) if files else 0
        return self.made[fnv]

    def marker(self, fnv: int) -> 'int | None':
        """The FO4 sound marker placing FNV SOUN `fnv`'s descriptor, made once; None without one."""
        if fnv not in self.markers:
            sndr = self.descriptor(fnv)
            fid = self.builder.writer.derive_formid(SOUN_SITE, f'{fnv:08X}') if sndr else None
            if fid:
                subs = pack_subrecord('EDID', f'FNV_{self.records[fnv]["EditorID"]}Marker'.encode() + b'\0')
                subs += pack_subrecord('OBND', struct.pack('<6h', *MARKER_BOUNDS)) + _u32('SDSC', sndr)
                self.builder.writer.add_record('SOUN', pack_fo4_record('SOUN', fid, 0, subs))
                self.builder.counts['SOUN marker'] += 1
            self.markers[fnv] = fid
        return self.markers[fnv]

    def field(self, rec: dict, key: str) -> int:
        """descriptor() of the FNV SOUN in field `key` of export record `rec` (0 when it has none)."""
        return self.descriptor(int(rec[key], 16)) if rec.get(key) else 0

    def _files(self, rec: dict) -> list:
        """The FNV sound files of SOUN `rec` (paths under Data\\Sound): its file, or every file of its folder."""
        name = rec.get('FNAM.Filename', '').replace('\\', '/').strip('/')
        source = self.export_dir / 'sound' / name.lower()
        if source.is_dir():
            return sorted(p.relative_to(self.export_dir / 'sound').as_posix() for p in source.iterdir()
                          if p.suffix.lower() in AUDIO)
        return [name.lower()] if source.is_file() else []

    def _write(self, fnv: int, rec: dict, files: list) -> int:
        """Write the SNDR of FNV SOUN `rec` playing `files`, queueing their conversion; its FormID."""
        loop = int(rec.get('SNDD.Flags', 0) or 0) & LOOP
        template = self.templates[LOOP_TEMPLATE if loop else ONE_SHOT_TEMPLATE]
        fid = self.builder.writer.derive_formid(SNDR_SITE, f'{fnv:08X}')
        subs = pack_subrecord('EDID', f'FNV_{rec["EditorID"]}'.encode() + b'\0')
        subs += b''.join(pack_subrecord(k.decode(), template[k]) for k in KEPT[:2] if k in template)
        for name in files:
            stem = str(Path(name).with_suffix('')).replace('/', '\\')
            subs += pack_subrecord('ANAM', f'data\\Sound\\FX\\{FOLDER}\\{stem}.wav'.encode('cp1252') + b'\0')
            self.jobs.append((self.export_dir / 'sound' / name,
                              self.builder.data_dir / 'Sound' / 'FX' / FOLDER / f'{stem}.xwm', None))
        subs += b''.join(pack_subrecord(k.decode(), template[k]) for k in KEPT[2:] if k in template)
        self.builder.writer.add_record('SNDR', pack_fo4_record('SNDR', fid, 0, subs))
        self.builder.counts['SNDR'] += 1
        return fid


def _u32(sig: str, value: int) -> bytes:
    """A 4-byte subrecord."""
    return pack_subrecord(sig, struct.pack('<I', value))
