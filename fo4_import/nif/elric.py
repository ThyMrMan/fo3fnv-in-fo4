"""Fallout 4's Elric turns pre-Elric Havok blocks into FO4 physics; only that physics is kept.

`finish(paths)` runs Elric once over a temporary copy of every NIF that has
Havok input blocks (collision.py), then puts each output's bhkPhysicsSystem
and bhkNPCollisionObject in place of the input blocks, keeping our own
render blocks (Elric also changes a shader flag). Elric crashes on some
input; after a crash the files it had not done run one at a time, and one
it still crashes on is written without collision.

See: docs/fork/fo4_spikes.md#spike-2-collision
"""

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile

ELRIC = FALLOUT4_DIR / 'Tools' / 'Elric'
#: Seconds one Elric run may take before it counts as hung.
TIMEOUT = 600
#: An identity rotation as NiNode stores it (nine cells).
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def havok_start(nif: NifFile) -> 'int | None':
    """The index of the first pre-Elric Havok block, or None."""
    for i, (kind, _) in enumerate(nif.blocks):
        if kind.startswith('bhk') or kind == 'NiTriStripsData':
            return i
    return None


def without_havok(nif: NifFile) -> NifFile:
    """`nif` cut before its Havok blocks, no node naming a collision object."""
    start = havok_start(nif)
    if start is None:
        return nif
    nif.blocks = nif.blocks[:start]
    for _, block in nif.blocks:
        if isinstance(block, dict) and 'collision' in block:
            block['collision'] = NONE
    return nif


def graft(ours: NifFile, processed: NifFile) -> NifFile:
    """`ours` with its Havok input replaced by Elric's FO4 physics, matched to our nodes by name, in order.

    Elric bakes a collision node's transform into the physics and keeps it on the node too, so a
    collision-only node (no children: collision.collision_nodes') is reset to identity. Every
    collision object shares Elric's one bhkPhysicsSystem, as vanilla's do.
    See: docs/fork/fo4_spikes.md#spike-4-exterior
    """
    owners = [i for i, (_, b) in enumerate(ours.blocks) if isinstance(b, dict) and b.get('collision', NONE) != NONE]
    names = [ours.strings[ours.blocks[i][1]['name']] for i in owners]
    without_havok(ours)
    systems = {}
    for kind, raw in processed.blocks:
        if kind != 'bhkNPCollisionObject':
            continue
        target, flags, data, body_id = struct.unpack('<iHiI', raw)
        name = processed.strings[processed.blocks[target][1]['name']]
        owner = owners.pop(names.index(name))
        names.remove(name)
        if data not in systems:
            ours.blocks.append(('bhkPhysicsSystem', processed.blocks[data][1]))
            systems[data] = len(ours.blocks) - 1
        ours.blocks.append(('bhkNPCollisionObject', struct.pack('<iHiI', owner, flags, systems[data], body_id)))
        ours.blocks[owner][1]['collision'] = len(ours.blocks) - 1
        if not ours.blocks[owner][1].get('children', [None]):
            ours.blocks[owner][1].update(translation=(0.0, 0.0, 0.0), rotation=IDENTITY, scale=1.0)
    return ours


def _run(sources: dict, work: Path) -> tuple:
    """One Elric run over {name: bytes}; (return code, {name: output bytes})."""
    shutil.rmtree(work, ignore_errors=True)
    src, out = work / 'Meshes', work / 'Out'
    src.mkdir(parents=True)
    for name, data in sources.items():
        (src / name).write_bytes(data)
    cmd = [str(ELRIC / 'Elrich.exe'), str(ELRIC / 'Settings' / 'PCMeshes.esf'),
           f'-ElricOptions.ConvertTarget={src}', f'-ElricOptions.OutputDirectory={out}',
           '-ElricOptions.CloseWhenFinished=true']
    rc = subprocess.run(cmd, cwd=ELRIC, timeout=TIMEOUT, capture_output=True, **POPEN_FLAGS).returncode
    return rc, {name: (out / name).read_bytes() for name in sources if (out / name).exists()}


def process(sources: dict) -> dict:
    """Elric's output for {name: pre-Elric NIF bytes}; a file Elric crashes on alone is left out."""
    with tempfile.TemporaryDirectory() as tmp:
        rc, done = _run(sources, Path(tmp) / 'batch')
        if rc == 0:
            return done
        for name in sorted(set(sources) - set(done)):
            _, single = _run({name: sources[name]}, Path(tmp) / 'one')
            done.update(single)
    return done


def finish(paths: list) -> list:
    """Replace the Havok input in each NIF at `paths` with Elric's physics; the paths left without collision."""
    inputs = {}
    for i, path in enumerate(paths):
        nif = nif_file.read(Path(path).read_bytes())
        if havok_start(nif) is not None:
            inputs[f'{i:05d}.nif'] = (Path(path), nif)
    done = process({name: nif_file.write(nif) for name, (_, nif) in inputs.items()})
    failed = []
    for name, (path, nif) in inputs.items():
        if name in done:
            path.write_bytes(nif_file.write(graft(nif, nif_file.read(done[name]))))
        else:
            path.write_bytes(nif_file.write(without_havok(nif)))
            failed.append(path)
    return failed
