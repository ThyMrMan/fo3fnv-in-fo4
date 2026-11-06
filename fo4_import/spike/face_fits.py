"""Published face fits: the work cache's face fits, in a file any user with the same fit code and bases installs
instead of fitting the game's faces (about 2,247, 1.5-2 h) locally.

    py -3.14 -m fo4_import.spike.face_fits export --export export/FalloutNV.esm --out <file>
    py -3.14 -m fo4_import.spike.face_fits verify <file>
    py -3.14 -m fo4_import.spike.face_fits install <file>

The file is gzipped JSON, read without pickle. It holds the fit code version
(fit_code), each sex's basis hash (basis_hash: SHA-1 of the basis arrays, never
the arrays) and, per sex, each face keyed by a SHA-1 of its FIT_FIELDS values
with its three fits as numbers and Fallout4.esm FormIDs only. A build takes a
face from the installed file only when the code version and its sex's basis
hash match this machine's (warm_faces counts each face it takes or fits).
A face's key also holds its FNV head parts (fit_key), so NPCs sharing FaceGen
but not brows or beards keep their own fits.

See: docs/fork/fo4_pipeline.md#published-face-fits
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
from fo4_import.pipeline.code_tag import code_tag
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import lookup, store
from fo4_import.spike.fnv_npc import head_parts
from fo4_import.spike.head_parts import HeadChoice
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: The FNV NPC fields a face fit reads; with its sex's two basis files, the fit's work-cache inputs (fit_key).
FIT_FIELDS = ('FGGS', 'FGGA', 'FGTS', 'RNAM.Race', 'HNAM.Hair', 'ENAM.Eyes', 'HCLR.R', 'HCLR.G', 'HCLR.B',
              'LNAM.HairLength')
#: (work-cache site, module) of a face's sculpt fit, tint fit and head part choice, in face_work's order.
FIT_SITES = (('sculpt_fit', 'fo4_import.spike.face_fit'), ('tint_fit', 'fo4_import.spike.face_fit'),
             ('head_parts', 'fo4_import.spike.head_parts'))
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


@functools.cache
def bases(female: bool) -> tuple:
    """One sex's existing sculpt and tint basis files' bytes, read once per process."""
    return tuple(p.read_bytes() for p in (sculpt.basis_path(female), tint.basis_path(female)) if p.exists())


def fit_key(export_dir: Path, npc: dict, female: bool) -> 'tuple | None':
    """The work-cache inputs of FNV NPC `npc`'s face fits: its FIT_FIELDS values, its head parts as `export_dir`
    resolves them (fnv_npc.head_parts) and its sex's two basis files; None uncalibrated.
    See: docs/fork/fo4_pipeline.md#face-fit-head-parts
    """
    found = bases(female)
    if len(found) < 2:
        return None
    parts = tuple(head_parts(export_dir, int(npc['FormID'], 16)))
    return tuple(npc.get(k, '') for k in FIT_FIELDS) + (parts,) + found


def face_id(key: tuple) -> str:
    """The file's key of a face: a SHA-1 of its fit_key `key` but the basis files."""
    return hashlib.sha1(repr(key[:-2]).encode()).hexdigest()


@functools.cache
def fit_code() -> str:
    """The fit code version: a SHA-1 of FIT_SITES' modules' code tags."""
    return hashlib.sha1('\0'.join(code_tag(module) for _, module in FIT_SITES).encode()).hexdigest()


@functools.cache
def basis_hash(female: bool) -> 'str | None':
    """A SHA-1 of one sex's sculpt and tint basis arrays (names, types, shapes, values); None uncalibrated."""
    if len(bases(female)) < 2:
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
    holds under its current code and bases."""
    faces, missing = {sex: {} for sex in SEXES.values()}, object()
    for npc in export_records(export_dir, 'NPC_'):
        female = bool(int(npc.get('ACBS.Flags', 0)) & 1)
        key = fit_key(export_dir, npc, female)
        values = tuple(lookup(*site, key, missing) for site in FIT_SITES) if key else (missing,)
        if missing not in values:
            faces[SEXES[female]][face_id(key)] = encode(values)
    return faces


def header() -> dict:
    """A file's header on this machine: format, fit code version, basis hashes."""
    return {'format': FORMAT, 'fit_code': fit_code(), 'bases': {sex: basis_hash(f) for f, sex in SEXES.items()}}


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
    if data['fit_code'] != fit_code():
        return 'fit code differs'
    local = basis_hash(female)
    return None if local and data['bases'][SEXES[female]] == local else f'{SEXES[female]} basis differs'


@functools.cache
def installed() -> 'dict | None':
    """The installed file, read once per process; None when there is none."""
    return read(INSTALLED) if INSTALLED.exists() else None


def take(female: bool, key: tuple, wanted: list) -> tuple:
    """(taken, build log count): store a face's `wanted` FIT_SITES values under its work-cache key `key` from
    the installed file when it can give them."""
    data = installed()
    reason = 'none installed' if data is None else unusable(data, female)
    values = None if reason else data['faces'][SEXES[female]].get(face_id(key))
    if values is None:
        return False, f'faces fitted locally (published fits: {reason or "face not in file"})'
    for i in wanted:
        store(*FIT_SITES[i], key, values[i])
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
