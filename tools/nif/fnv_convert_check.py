"""Run an FNV/FO3 mesh converter on real inputs twice, reading with pyffi (fnv_file.read_pyffi) and with
fnv_file.read (our reader), each in its own worker processes, and compare everything the converter returns
(FO4 NIF bytes, materials, arrays, frames) by a hash of its contents.

    py -3.14 tools/nif/fnv_convert_check.py static --paths <files or folders> --max 100
    py -3.14 tools/nif/fnv_convert_check.py outfit --export export/FalloutNV.esm --max 10

Converters: static, outfit, headgear, gun, creature, face, tree, clips. Inputs come from the export's own records
(ARMO, WEAP, TREE) and folders. One JSON line per input, then a summary line. Nothing is written but the lines.

See: docs/fork/research/fnv_nif_reader.md#integration
"""

import argparse
import dataclasses
import functools
import hashlib
import multiprocessing
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.process_job import limit_own_memory
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face import fnv_head, hair
from fo4_import.havok import gun_clips
from fo4_import.nif import clip_shaders, convert_static, creature, file as fo4_file, fnv_file, gun, headgear, outfit
from fo4_import.nif import tree, weapon
from fo4_import.nif.fnv_schema import Struct
from fo4_import.pipeline.export_index import asset_root, export_file, export_records
from pyffi.object_models.xml.struct_ import StructBase
from tools.nif.fnv_reader_check import emit, meshes, varied

#: FNV biped flag of an upper-body outfit (as fo4_import.spike.equipment).
UPPER_BODY = 0x4
SEXES = ('male', 'female')
#: The FO4 receiver every gun is placed on.
RECEIVER = 'meshes\\weapons\\huntingrifle\\huntingriflereceiver.nif'
#: FNV's gun folders under meshes (guns.py's guns; melee and thrown weapons are dressed elsewhere).
GUN_FOLDERS = ('weapons/1handpistol/', 'weapons/2handrifle/', 'weapons/2handautomatic/', 'weapons/2handlauncher/',
               'weapons/2handhandle/')


# ---------------------------------------------------------------------------
# Contents of a result
# ---------------------------------------------------------------------------

def _fields(obj) -> tuple:
    """(type name, field names) of a block or struct read by either reader."""
    names = type(obj).PYFFI._names if isinstance(obj, Struct) else type(obj)._names
    return type(obj).__name__.removesuffix('View'), names


def feed(value, h, seen: set) -> None:
    """Hash `value`'s contents into `h`: containers by element, arrays by bytes, NIFs by their written bytes, read
    blocks by field (each block once)."""
    if isinstance(value, (Struct, StructBase)):
        name, names = _fields(value)
        h.update(f'<{name}'.encode())
        if id(value) not in seen:
            seen.add(id(value))
            for n in names:
                feed(getattr(value, n), h, seen)
        return
    for kind, write in _FEEDS:
        if isinstance(value, kind):
            return write(value, h, seen)
    if hasattr(value, '__iter__') and hasattr(value, '__len__'):
        return _feed_items(list(value), h, seen)
    h.update(repr(value).encode())
    return None


def _feed_items(items, h, seen: set) -> None:
    """Hash each of `items`."""
    h.update(f'[{len(items)}'.encode())
    for item in items:
        feed(item, h, seen)


#: (type, hasher) of the values hashed by kind before the generic walk.
_FEEDS = (
    ((bytes, bytearray), lambda v, h, s: h.update(b'b' + bytes(v))),
    (str, lambda v, h, s: h.update(b's' + v.encode())),
    ((bool, int, float, type(None)), lambda v, h, s: h.update(repr(v).encode())),
    (np.ndarray, lambda v, h, s: h.update(f'{v.dtype.str}{v.shape}'.encode() + np.ascontiguousarray(v).tobytes())),
    (np.generic, lambda v, h, s: h.update(repr(v.item()).encode())),
    (fo4_file.NifFile, lambda v, h, s: h.update(b'nif' + fo4_file.write(v))),
    (dict, lambda v, h, s: _feed_items(sorted(v.items(), key=lambda kv: repr(kv[0])), h, s)),
    ((set, frozenset), lambda v, h, s: _feed_items(sorted(v, key=repr), h, s)),
)


def digest(value) -> str:
    """The hash of `value`'s contents (feed)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    h = hashlib.sha1()
    feed(value, h, set())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Converters, as the pipeline calls them
# ---------------------------------------------------------------------------

def texture_root(path) -> str:
    """The export folder holding mesh `path` (the part before its `meshes` folder)."""
    parts = Path(path).resolve().parts
    lower = [p.lower() for p in parts]
    return str(Path(*parts[:lower.index('meshes')])) if 'meshes' in lower else ''


def _static(path) -> bytes:
    """The FO4 static NIF bytes of FNV mesh `path`."""
    return fo4_file.write(run_static(str(path)).nif)


@functools.cache
def _archives() -> Archives:
    """Fallout 4's archives, once per worker."""
    return Archives(FALLOUT4_DIR / 'Data')


@functools.cache
def _body_fit(export_dir: str, sex: str):
    """outfit.body_fit, once per worker."""
    return outfit.body_fit(Path(export_dir), sex, _archives())


@functools.cache
def _head_fit(export_dir: str, sex: str):
    """headgear.head_fit, once per worker."""
    return headgear.head_fit(Path(export_dir), sex, _archives())


def run_static(path: str):
    """convert_static.convert of `path`."""
    return convert_static.convert(path, texture_root(path) or None)


def run_outfit(export_dir: str, model: str, sex: str):
    """outfit.worn (third and first person) and shape_materials of FNV outfit `model` on `sex`."""
    path = export_file(export_dir, 'meshes', model)
    static = _static(path)
    fit = _body_fit(export_dir, sex)
    return [outfit.worn(static, path, fit, first) for first in (False, True)], outfit.shape_materials(static, path)


def run_headgear(export_dir: str, model: str, sex: str, slots: tuple):
    """headgear.rigid, head_frame and worn of FNV headgear `model` on `sex` in `slots`."""
    path = export_file(export_dir, 'meshes', model)
    rigid = headgear.rigid(path)
    frame = None if rigid else headgear.head_frame(path, export_file(export_dir, 'meshes', headgear.FNV_HEADS[sex]))
    on = rigid or frame is not None
    return rigid, frame, headgear.worn(_static(path), _head_fit(export_dir, sex), slots, frame) if on else None


def run_gun(export_dir: str, model: str):
    """gun.fnv_nodes, fnv_layout, gun_clips.fnv_frames, and gun.gun on RECEIVER of FNV gun `model`."""
    path = export_file(export_dir, 'meshes', model)
    static, nodes = _static(path), gun.fnv_nodes(path)
    receiver = _archives().read(RECEIVER)
    matrix = gun.placement(static, nodes, receiver)
    return nodes, gun.fnv_layout(static, nodes), gun_clips.fnv_frames(path), gun.gun(static, nodes, receiver, matrix)


def run_creature(export_dir: str, folder: str, name: str):
    """creature.creature_mesh of FNV creature `folder`'s mesh `name` alone, on its FO4 pair."""
    meshes_dir = asset_root(export_dir, 'meshes', folder)
    path = meshes_dir / name
    fit = creature.creature_fit(Path(export_dir), folder, _archives())
    parts = [(run_static(str(path)), path)]
    bare = creature.skin_texture([path]) or None
    return creature.creature_mesh(parts, fit, creature.PAIRS[folder].rig.root,
                                  creature.skeleton_parents(meshes_dir / 'skeleton.nif'), bare)


def run_face(export_dir: str, model: str):
    """hair.fnv_shape of FNV head part `model`, and fnv_head.head of the mean heads."""
    meshes_dir = asset_root(export_dir, 'meshes')
    heads = [fnv_head.head(meshes_dir, headgear.FNV_HEADS[sex], '', '') for sex in SEXES]
    return hair.fnv_shape(export_file(export_dir, 'meshes', model)), heads


def run_tree(export_dir: str, editor_id: str):
    """tree.tree_mesh of FNV TREE `editor_id`."""
    rec = next(r for r in export_records(export_dir, 'TREE') if r.get('EditorID') == editor_id)
    return tree.tree_mesh(Path(export_dir), rec)


def run_clips(export_dir: str, kf: str):
    """clip_shaders.clip_channels of `kf`; weapon.held_pose of both holds."""
    return clip_shaders.clip_channels(Path(kf)), [weapon.held_pose(Path(export_dir), t) for t in (1, 2)]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _sample(items: list, count: int, seed: int) -> list:
    """Up to `count` of `items`, seeded."""
    items = sorted(set(items))
    return random.Random(seed).sample(items, min(count, len(items)))


def _model(rec: dict, key: str) -> str:
    """Record `rec`'s model at `key`, as a lower-case path under meshes; '' for none."""
    return rec.get(key, '').replace('\\', '/').lower()


def _armor(export_dir: str, test) -> list:
    """(model, sex, biped flags) of every ARMO body model whose flags pass `test` and whose file is exported."""
    out = []
    for rec in export_records(export_dir, 'ARMO'):
        flags = int(rec.get('BMDT.BipedFlags', 0))
        for sex in SEXES:
            model = _model(rec, f'{sex.title()}.BipedModel.MODL') or _model(rec, 'Male.BipedModel.MODL')
            if model and test(flags) and export_file(export_dir, 'meshes', model).is_file():
                out.append((model, sex, flags))
    return out


def jobs(converter: str, args) -> list:
    """[(label, runner, args)] of `converter`'s inputs."""
    ex, n, seed = str(args.export), args.max, args.seed
    if converter == 'static':
        files = meshes(args.paths)
        return [(str(p), 'run_static', (str(p),)) for p in (varied(files, n, seed) if n else files)]
    if converter == 'outfit':
        picked = _sample(_armor(ex, lambda f: f & UPPER_BODY), n, seed)
        return [(f'{m} {s}', 'run_outfit', (ex, m, s)) for m, s, _ in picked]
    if converter == 'headgear':
        picked = _sample(_armor(ex, lambda f: headgear.slots(f) is not None), n, seed)
        return [(f'{m} {s}', 'run_headgear', (ex, m, s, headgear.slots(f))) for m, s, f in picked]
    if converter == 'gun':
        models = [_model(r, 'Model.MODL') for r in export_records(ex, 'WEAP')]
        models = [m for m in models if m.startswith(GUN_FOLDERS) and export_file(ex, 'meshes', m).is_file()]
        return [(m, 'run_gun', (ex, m)) for m in _sample(models, n, seed)]
    return _more_jobs(converter, args)


def _more_jobs(converter: str, args) -> list:
    """jobs() of the creature, face, tree and clips converters."""
    ex, n, seed = str(args.export), args.max, args.seed
    if converter == 'creature':
        found = [(folder, p.name) for folder in creature.PAIRS
                 for p in Path(asset_root(ex, 'meshes', folder)).glob('*.nif') if 'skeleton' not in p.name]
        return [(f'{f} {m}', 'run_creature', (ex, f, m)) for f, m in _sample(found, n, seed)]
    if converter == 'face':
        root = Path(asset_root(ex, 'meshes', 'characters'))
        found = [str(p.relative_to(root.parent)).replace('\\', '/') for p in (root / 'hair').glob('*.nif')]
        found += [str(p.relative_to(root.parent)).replace('\\', '/') for p in (root / 'head').glob('eye*.nif')]
        return [(m, 'run_face', (ex, m)) for m in _sample(found, n, seed)]
    if converter == 'tree':
        ids = [r['EditorID'] for r in export_records(ex, 'TREE') if r.get('EditorID')]
        return [(i, 'run_tree', (ex, i)) for i in _sample(ids, n, seed)]
    kfs = [str(p) for p in Path(asset_root(ex, 'meshes')).rglob('*.kf') if 'characters' not in p.parts]
    return [(k, 'run_clips', (ex, k)) for k in _sample(kfs, n, seed)]


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def _start(mode: str, cap: int) -> None:
    """A worker reading with `mode` ('pyffi' or 'ours'), capped at `cap` bytes."""
    limit_own_memory(cap)
    if mode == 'pyffi':
        fnv_file.read = fnv_file.read_pyffi


def _run(task: tuple) -> dict:
    """{label, seconds converting, hash or error} of one input."""
    label, runner, args = task
    start = time.perf_counter()
    try:
        made = globals()[runner](*args)
        seconds = time.perf_counter() - start
        out = {'hash': digest(made), 'seconds': seconds}
    except MemoryError:
        out = {'error': 'memory cap'}
    except Exception as error:
        out = {'error': f'{type(error).__name__}: {error}'[:200]}
    return {'label': label, 'seconds': time.perf_counter() - start, **out}


def run_mode(mode: str, tasks: list, args) -> dict:
    """{label: result} of every task with `mode`'s reader."""
    context = multiprocessing.get_context('spawn')
    with context.Pool(args.workers, _start, (mode, int(args.cap_gb * 2 ** 30)), maxtasksperchild=20) as pool:
        return {r['label']: r for r in pool.imap_unordered(_run, tasks)}


def compare(theirs: dict, mine: dict) -> dict:
    """One input's line: same contents (or the same error), both times."""
    same = theirs.get('hash') == mine.get('hash') and theirs.get('error', '')[:30] == mine.get('error', '')[:30]
    return {'label': theirs['label'], 'same': same, 'pyffi_s': theirs['seconds'], 'ours_s': mine['seconds'],
            'pyffi_error': theirs.get('error'), 'ours_error': mine.get('error')}


def main() -> None:
    """Run the converter on every input in both modes; write each comparison and a summary."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('converter', choices=('static', 'outfit', 'headgear', 'gun', 'creature', 'face', 'tree',
                                              'clips'))
    parser.add_argument('--paths', nargs='*', default=[])
    parser.add_argument('--export', default='export/FalloutNV.esm')
    parser.add_argument('--max', type=int, default=20)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--workers', type=int, default=max(1, os.cpu_count() - 1))
    parser.add_argument('--cap-gb', type=float, default=4.0)
    parser.add_argument('--out', help='append one JSON line per input here')
    args = parser.parse_args()
    tasks = jobs(args.converter, args)
    theirs, mine = run_mode('pyffi', tasks, args), run_mode('ours', tasks, args)
    lines = [compare(theirs[label], mine[label]) for label, _, _ in tasks]
    for line in lines:
        emit(line, args.out)
    ok = [x for x in lines if not x['pyffi_error']]
    emit({'converter': args.converter, 'inputs': len(lines), 'same': sum(x['same'] for x in lines),
          'converted': len(ok), 'same_converted': sum(x['same'] for x in ok),
          'pyffi_s': sum(x['pyffi_s'] for x in ok), 'ours_s': sum(x['ours_s'] for x in ok)}, args.out)


if __name__ == '__main__':
    main()
