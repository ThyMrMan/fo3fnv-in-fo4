"""Face fits in the work cache, and published: a file any user with the same fit version and bases installs
instead of fitting the game's faces (about 2,247) locally.

    py -3.14 -m fo4_import.spike.face_fits export --export export/FalloutNV.esm --out <file>
    py -3.14 -m fo4_import.spike.face_fits verify <file>
    py -3.14 -m fo4_import.spike.face_fits install <file>

A fit is a versioned work-cache entry (work_cache.versioned): its inputs
(fit_key) are the face's FIT_FIELDS values, its FNV head parts (so NPCs
sharing FaceGen but not brows or beards keep their own fits) and its sex's
basis hash (basis_hash: SHA-1 of the basis arrays), under FIT_VERSION. No code
record stands behind it: FIT_VERSION is bumped by hand when a fit's result
changes, and tests/test_fo4_face_fit_version.py holds the bump to that.

The file is gzipped JSON, read without pickle. It holds FIT_VERSION (as
fit_code), each sex's basis hash (never the arrays) and, per sex, each face
keyed by a SHA-1 of its fields and head parts with its three fits as numbers
and Fallout4.esm FormIDs only. A build takes a face from the installed file
only when the version and its sex's basis hash match this machine's
(warm_faces counts each face it takes or fits), and keeps it under the same key.

See: docs/fork/fo4_pipeline.md#published-face-fits
See: docs/fork/fo4_build_speed.md#faces
"""

import argparse
import dataclasses
import functools
import gzip
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

from fo4_import.face import sculpt, tint
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import lookup_versioned, store_versioned, versioned
from fo4_import.spike.fnv_npc import head_parts
from fo4_import.spike.head_parts import HeadChoice
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: The face fits' version, of FIT_SITES' entries and the published file: bump it when any fit's result changes.
FIT_VERSION = 2
#: The FNV NPC fields a face fit reads; with its head parts and its sex's basis hash, its inputs (fit_key).
FIT_FIELDS = ('FGGS', 'FGGA', 'FGTS', 'RNAM.Race', 'HNAM.Hair', 'ENAM.Eyes', 'HCLR.R', 'HCLR.G', 'HCLR.B',
              'LNAM.HairLength')
#: The versioned work-cache sites of a face's sculpt fit, tint fit and head part choice, in face_work's order.
FIT_SITES = ('sculpt_fit', 'tint_fit', 'head_parts')
#: Where install puts a published file and builds read it.
INSTALLED = sculpt.CACHE / 'face_fits.json.gz'
#: The file layout's version.
FORMAT = 1
#: Build log count of a face taken from the installed file.
TAKEN = 'faces from published fits'
#: The sexes by female flag, as the file names them.
SEXES = {False: 'male', True: 'female'}
#: HeadChoice fields the file carries: the parts and colour (FormIDs) and the coverage distances.
HEAD_FORMS = ('hair', 'facial_hair', 'eyes', 'colour')


def fit_key(export_dir: Path, npc: dict, female: bool) -> 'tuple | None':
    """The work-cache inputs of FNV NPC `npc`'s face fits: its FIT_FIELDS values, its head parts as `export_dir`
    resolves them (fnv_npc.head_parts) and its sex's basis hash; None uncalibrated.
    See: docs/fork/fo4_pipeline.md#face-fit-head-parts
    """
    basis = basis_hash(female)
    if basis is None:
        return None
    parts = tuple(head_parts(export_dir, int(npc['FormID'], 16)))
    return tuple(npc.get(k, '') for k in FIT_FIELDS) + (parts, basis)


def face_id(key: tuple) -> str:
    """The file's key of a face: a SHA-1 of its fit_key `key` but the basis hash."""
    return hashlib.sha1(repr(key[:-1]).encode()).hexdigest()


def kept(index: int, key: tuple, default=None):
    """FIT_SITES[index]'s value kept for fit_key `key` and FIT_VERSION; else `default`."""
    return lookup_versioned(FIT_SITES[index], FIT_VERSION, key, default)


def keep(index: int, key: tuple, value):
    """Keep `value` as FIT_SITES[index]'s for fit_key `key` and FIT_VERSION."""
    return store_versioned(FIT_SITES[index], FIT_VERSION, key, value)


def fitted(index: int, key: tuple, make):
    """FIT_SITES[index]'s value for fit_key `key` and FIT_VERSION, from make() once."""
    return versioned(FIT_SITES[index], FIT_VERSION, key, make)


@functools.cache
def basis_hash(female: bool) -> 'str | None':
    """A SHA-1 of one sex's sculpt and tint basis arrays (names, types, shapes, values), worked out once per
    process; None uncalibrated."""
    if not (sculpt.basis_path(female).exists() and tint.basis_path(female).exists()):
        return None
    digest = hashlib.sha1()
    for path in (sculpt.basis_path(female), tint.basis_path(female)):
        with np.load(path) as arrays:
            for name in sorted(arrays.files):
                digest.update(f'{name}\0{arrays[name].dtype.str}\0{arrays[name].shape}\0'.encode())
                digest.update(np.ascontiguousarray(arrays[name]).tobytes())
    return digest.hexdigest()


def _number(value) -> 'int | float':
    """`value` if a JSON number, else ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'not a number: {value!r}')
    return value


def _form(value) -> 'int | None':
    """`value` if None or a FormID, else ValueError."""
    if value is not None and not 0 <= _number(value) <= 0xFFFFFFFF:
        raise ValueError(f'not a FormID: {value!r}')
    return value


def encode_sculpt(value: tuple) -> list:
    """[[[region, [seven controls]], ...], captured] of a sculpt fit (FMRI/FMRS pairs, fraction captured)."""
    morphs, captured = value
    subs = list(subrecords(morphs))
    pairs = []
    for (region, index), (controls, data) in zip(subs[::2], subs[1::2]):
        if (region, controls, len(index), data[28:]) != (b'FMRI', b'FMRS', 4, bytes(8)):
            raise ValueError('a sculpt fit holds more than FMRI/FMRS pairs')
        pairs.append([struct.unpack('<I', index)[0], list(struct.unpack('<7f', data[:28]))])
    return [pairs, captured]


def decode_sculpt(value: list) -> tuple:
    """The sculpt fit encode_sculpt gave `value` for."""
    pairs, captured = value
    return b''.join(pack_subrecord('FMRI', struct.pack('<I', _form(region)))
                    + pack_subrecord('FMRS', sculpt.pack_fmrs([_number(c) for c in controls]))
                    for region, controls in pairs), _number(captured)


def encode_tint(value: tuple) -> list:
    """[values, skin tone scale, captured] of a tint fit."""
    values, tone, captured = value
    return [values.tolist(), tone.tolist(), captured]


def decode_tint(value: list) -> tuple:
    """The tint fit encode_tint gave `value` for."""
    values, tone, captured = value
    return (np.array([_number(v) for v in values], np.float64), np.array([_number(v) for v in tone], np.float64),
            _number(captured))


def encode_head(value: HeadChoice) -> dict:
    """A head part choice's FormIDs and distances (not `unmapped`: FNV EditorIDs)."""
    return {**{name: getattr(value, name) for name in HEAD_FORMS}, 'distances': value.distances}


def decode_head(value: dict) -> HeadChoice:
    """The head part choice encode_head gave `value` for (`unmapped` empty)."""
    distances = value['distances']
    if not set(distances) <= {'hair', 'facial hair'} or set(value) != {*HEAD_FORMS, 'distances'}:
        raise ValueError(f'unknown head part choice fields: {sorted(value)}')
    return HeadChoice(**{name: _form(value[name]) for name in HEAD_FORMS},
                      distances={k: _number(v) for k, v in distances.items()})


#: Per FIT_SITES index, the value's (encoder, decoder).
CODECS = ((encode_sculpt, decode_sculpt), (encode_tint, decode_tint), (encode_head, decode_head))


def published_value(values: tuple) -> tuple:
    """`values` (FIT_SITES' order) as a build taking them from the file stores them."""
    return tuple(None if v is None else dataclasses.replace(v, unmapped=[]) if isinstance(v, HeadChoice) else v
                 for v in values)


def same(a, b) -> bool:
    """Whether `a` and `b` are one value to the bit: types, arrays' types and bytes, floats' bits (any NaN
    matching any NaN, as JSON keeps no NaN sign), containers and HeadChoice fields in order."""
    if type(a) is not type(b):
        return False
    if isinstance(a, np.ndarray):
        return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    if isinstance(a, HeadChoice):
        a, b = list(vars(a).items()), list(vars(b).items())
    elif isinstance(a, dict):
        a, b = list(a.items()), list(b.items())
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, float):
        return struct.pack('<d', a) == struct.pack('<d', b) or a != a and b != b
    return a == b


def encode(values: tuple) -> list:
    """A face's three fits as JSON numbers; ValueError unless they decode to published_value(values) (same).
    See: docs/fork/fo4_pipeline.md#published-face-fits
    """
    out = [None if v is None else codec[0](v) for v, codec in zip(values, CODECS)]
    if not same(decode(json.loads(json.dumps(out))), published_value(values)):
        raise ValueError('a fit does not survive the file byte for byte')
    return out


def decode(entry: list) -> tuple:
    """The three fits encode gave `entry` for."""
    if len(entry) != len(CODECS):
        raise ValueError('a face needs three fits')
    return tuple(None if v is None else codec[1](v) for v, codec in zip(entry, CODECS))


def collect(export_dir: Path) -> dict:
    """{sex: {face_id: encoded fits}} of every NPC_ in `export_dir` whose three fits this machine's work cache
    holds under its current fit version and bases."""
    faces, missing = {sex: {} for sex in SEXES.values()}, object()
    for npc in export_records(export_dir, 'NPC_'):
        female = bool(int(npc.get('ACBS.Flags', 0)) & 1)
        key = fit_key(export_dir, npc, female)
        values = tuple(kept(i, key, missing) for i in range(len(FIT_SITES))) if key else (missing,)
        if missing not in values:
            faces[SEXES[female]][face_id(key)] = encode(values)
    return faces


def header() -> dict:
    """A file's header on this machine: format, fit version, basis hashes."""
    return {'format': FORMAT, 'fit_code': FIT_VERSION, 'bases': {sex: basis_hash(f) for f, sex in SEXES.items()}}


def write(path: Path, faces: dict) -> None:
    """Write `faces` ({sex: {face_id: fits}}) under header() to file `path`."""
    text = json.dumps({**header(), 'faces': faces}, sort_keys=True, separators=(',', ':'))
    Path(path).write_bytes(gzip.compress(text.encode(), mtime=0))


def read(path: Path) -> dict:
    """The file at `path`, every face decoded (ValueError on anything but numbers where numbers go)."""
    data = json.loads(gzip.decompress(Path(path).read_bytes()))
    if data.get('format') != FORMAT:
        raise ValueError(f'format {data.get("format")} is not {FORMAT}')
    data['faces'] = {sex: {face: decode(entry) for face, entry in data['faces'][sex].items()}
                     for sex in SEXES.values()}
    return data


def unusable(data: dict, female: bool) -> 'str | None':
    """Why file `data` (read) cannot give this machine's faces of one sex; None when it can."""
    if data['fit_code'] != FIT_VERSION:
        return 'fit version differs'
    local = basis_hash(female)
    return None if local and data['bases'][SEXES[female]] == local else f'{SEXES[female]} basis differs'


@functools.cache
def installed() -> 'dict | None':
    """The installed file, read once per process; None when there is none."""
    return read(INSTALLED) if INSTALLED.exists() else None


def take(female: bool, key: tuple, wanted: list) -> tuple:
    """(taken, build log count): keep a face's `wanted` FIT_SITES values under its work-cache key `key` (keep)
    from the installed file when it can give them."""
    data = installed()
    reason = 'none installed' if data is None else unusable(data, female)
    values = None if reason else data['faces'][SEXES[female]].get(face_id(key))
    if values is None:
        return False, f'faces fitted locally (published fits: {reason or "face not in file"})'
    for i in wanted:
        keep(i, key, values[i])
    return True, TAKEN


def verify(path: Path) -> bool:
    """Print whether the file at `path` reads (numbers only) and which sexes this machine can take; whether any."""
    data = read(path)
    usable = False
    for female, sex in SEXES.items():
        reason = unusable(data, female)
        usable |= reason is None
        print(f'{sex}: {len(data["faces"][sex])} faces, {reason or "usable here"}')
    return usable


def main(argv=None) -> int:
    """Run export, verify or install; the exit code (1: nothing this machine can use)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    ex = sub.add_parser('export', help="write this machine's cached fits to a file")
    ex.add_argument('--export', required=True, type=Path, help='The FNV export folder (export/FalloutNV.esm)')
    ex.add_argument('--out', required=True, type=Path, help='The file to write')
    for name in ('verify', 'install'):
        sub.add_parser(name, help=f'{name} a published file').add_argument('file', type=Path)
    args = ap.parse_args(argv)
    if args.cmd == 'export':
        faces = collect(args.export)
        write(args.out, faces)
        print(args.out, {sex: len(f) for sex, f in faces.items()})
        return 0
    if not verify(args.file):
        return 1
    if args.cmd == 'install':
        INSTALLED.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.file, INSTALLED)
        print('installed:', INSTALLED)
    return 0


if __name__ == '__main__':
    sys.exit(main())
