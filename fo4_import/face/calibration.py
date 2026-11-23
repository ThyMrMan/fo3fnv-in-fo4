"""FO4's face bases (face.sculpt, face.presets, face.tint) measured on our own FaceGen, once per sex, without the
Creation Kit.

    py -3.14 -m fo4_import.face.calibration [--again]

Each base's calibration plugin is written to a scratch folder; its NPCs' FaceGeom (facegeom.build) or face _d
(face_tint) is drawn from Fallout4.esm and the game's archives, and each control's effect against the baseline
NPC is cached under output/fo4_cache. The bases are Bethesda data: made on the user's machine, never shipped.

See: docs/fork/fo4_facegen_plan.md#calibration
"""

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import face_tint, facegeom, presets, sculpt, tint
from fo4_import.face.tint import HUMAN_RACE, TEMPLATES
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The calibration plugin's file name in its scratch folder.
PLUGIN = 'FNVFaceCalib.esp'
#: The size the CK exports a face _d at, which the tint baseline keeps.
TINT_SIZE = 2048


def template(female: bool) -> tuple:
    """(HumanRace record, template NPC record, template body without its face fields) for one sex.
    See: docs/fork/fo4_facegen_plan.md#body-skin
    """
    records = {r.form_id: r for r, _ in walk(FALLOUT4_ESM.read_bytes(), b'RACE', b'NPC_')
               if r.form_id in (HUMAN_RACE, TEMPLATES[female])}
    npc = records[TEMPLATES[female]]
    body = b''.join(pack_subrecord(t.decode(), d) for t, d in subrecords(npc.body) if t not in sculpt.FACE_FIELDS)
    return records[HUMAN_RACE], npc, body


def drawn(write, female: bool, draw) -> dict:
    """{EditorID: draw(Sources, local id)} of each NPC the calibration plugin `write(path, body, flags)` writes."""
    _, npc, body = template(female)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / PLUGIN
        names = write(path, body, npc.flags)
        src = facegeom.Sources(path, [path.parent])
        return {name: draw(src, 0x800 + i) for i, name in enumerate(names)}


def head(src: facegeom.Sources, form_id: int) -> bytes:
    """The calibration NPC's FaceGeom NIF."""
    return facegeom.build(src, PLUGIN, form_id)


def face_d(src: facegeom.Sources, form_id: int) -> np.ndarray:
    """The calibration NPC's face _d, RGBA uint8 at TINT_SIZE."""
    npc, race, female, _ = facegeom.npc_face(src, PLUGIN, form_id)
    rgb = np.asarray(face_tint.as_image(face_tint.face_diffuse(face_tint.Face(src, npc, race, female), TINT_SIZE)))
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


def measure_sculpt(female: bool) -> Path:
    """Measure and cache HumanRace's sculpt basis for one sex; the cache file."""
    regions = sculpt.race_regions(template(female)[0].body, female=female)
    nifs = drawn(lambda path, body, flags: sculpt.calibration_plugin(path, body, flags, regions), female, head)
    return saved(sculpt.basis_path(female), basis=sculpt.measure(nifs, regions), regions=np.array(regions, np.uint32),
                 baseline=np.frombuffer(nifs[sculpt.BASELINE], np.uint8))


def measure_presets(female: bool) -> Path:
    """Measure and cache HumanRace's morph preset basis for one sex; the cache file."""
    found = presets.race_presets(subrecords(template(female)[0].body), female)
    nifs = drawn(lambda path, body, flags: presets.calibration_plugin(path, body, flags, found), female, head)
    names = presets.morphs(found)
    return saved(presets.basis_path(female), basis=presets.measure(nifs, names), names=np.array(names))


def measure_tints(female: bool) -> Path:
    """Measure and cache HumanRace's tint basis for one sex; the cache file."""
    complexion, brows, tone = tint.race_options(template(female)[0].body, female=female)
    options = complexion + brows
    faces = drawn(lambda path, body, flags: tint.calibration_plugin(path, body, flags, options, tone), female, face_d)
    effects = tint.measure({name: tint.reduced(rgba) for name, rgba in faces.items()}, options)
    return saved(tint.basis_path(female), effects=effects.astype(np.float16), options=np.array(options, np.uint32),
                 baseline=faces[tint.BASELINE], brows=np.array(brows, np.uint32))


def saved(path: Path, **arrays) -> Path:
    """`arrays` written to `path` (compressed .npz); the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    return path


#: Each base's module, and what measures it for one sex.
MEASURES = ((sculpt, measure_sculpt), (presets, measure_presets), (tint, measure_tints))


def missing() -> list:
    """[(measure, female)] of every base not yet cached."""
    return [(measure, female) for female in (False, True) for base, measure in MEASURES
            if not base.basis_path(female).exists()]


def ensure(log=print) -> int:
    """Measure every base missing() names, each logged; how many."""
    todo = missing()
    for measure, female in todo:
        started = time.time()
        path = measure(female)
        log(f'face calibration: {path.name} measured in {time.time() - started:.0f} s')
    return len(todo)


def main() -> None:
    """Measure the missing bases (all with --again) and print each."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--again', action='store_true', help='Measure every base again, not only the missing ones')
    args = ap.parse_args()
    if args.again:
        for base, _ in MEASURES:
            for female in (False, True):
                base.basis_path(female).unlink(missing_ok=True)
    print('bases measured:', ensure())


if __name__ == '__main__':
    main()
