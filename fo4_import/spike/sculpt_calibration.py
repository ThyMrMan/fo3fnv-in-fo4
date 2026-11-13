"""Measure FO4's face sculpt region and tint layer bases through the Creation Kit, once per race and sex.

    py -3.14 -m fo4_import.spike.sculpt_calibration --data <mod folder> [--what sculpt|tints|presets] [--female]

Writes the calibration plugin (face.sculpt) into the mod folder, exports its
FaceGen with the CK through MO2, measures each control's effect on the face
vertices, and caches the basis, the region list and the baseline head under
output/fo4_cache; then removes the plugin and its FaceGen.

See: docs/fork/fo4_spikes.md#spike-2-sculpt
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.face import presets, sculpt, tint
from fo4_import.face.tint import HUMAN_RACE, TEMPLATES
from fo4_import.spike.facegen import FACEGEN_DIRS, clear, collect, run_ck
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

PLUGIN, TINT_PLUGIN, PRESET_PLUGIN = 'FNVSculptCalib.esp', 'FNVTintCalib.esp', 'FNVPresetCalib.esp'


def _template(female: bool) -> tuple:
    """(HumanRace record, template NPC record, template body without its face fields) for one sex, as a fitted
    copy has it.
    See: docs/fork/fo4_facegen_plan.md#body-skin
    """
    records = {r.form_id: r for r, _ in walk(FALLOUT4_ESM.read_bytes(), b'RACE', b'NPC_')
               if r.form_id in (HUMAN_RACE, TEMPLATES[female])}
    template = records[TEMPLATES[female]]
    body = b''.join(pack_subrecord(t.decode(), d) for t, d in subrecords(template.body) if t not in sculpt.FACE_FIELDS)
    return records[HUMAN_RACE], template, body


def calibrate(data_dir: Path, female: bool = False) -> Path:
    """Measure and cache HumanRace's sculpt basis for one sex; the cache file."""
    race, template, body = _template(female)
    regions = sculpt.race_regions(race.body, female=female)
    names = sculpt.calibration_plugin(data_dir / PLUGIN, body, template.flags, regions)
    try:
        clear(PLUGIN, data_dir)
        run_ck(PLUGIN)
        collect(PLUGIN, data_dir)
        folder = data_dir / FACEGEN_DIRS[0] / PLUGIN
        nifs = {name: (folder / f'{0x800 + i:08X}.NIF').read_bytes() for i, name in enumerate(names)}
        out = sculpt.basis_path(female)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, basis=sculpt.measure(nifs, regions), regions=np.array(regions, np.uint32),
                            baseline=np.frombuffer(nifs[sculpt.BASELINE], np.uint8))
    finally:
        (data_dir / PLUGIN).unlink(missing_ok=True)
        clear(PLUGIN, data_dir)
    return out


def _exported(names: list, plugin: str, data_dir: Path, folder: int, suffix: str) -> dict:
    """{EditorID: path} of exported FaceGeom NIFs (folder 0) or textures (1)."""
    base = data_dir / FACEGEN_DIRS[folder] / plugin
    return {name: base / f'{0x800 + i:08X}{suffix}' for i, name in enumerate(names)}


def calibrate_tints(data_dir: Path, female: bool = False) -> Path:
    """Measure and cache HumanRace's tint basis for one sex; the cache file."""
    race, template, body = _template(female)
    complexion, brows, tone = tint.race_options(race.body, female=female)
    options = complexion + brows
    names = tint.calibration_plugin(data_dir / TINT_PLUGIN, body, template.flags, options, tone)
    try:
        clear(TINT_PLUGIN, data_dir)
        run_ck(TINT_PLUGIN)
        collect(TINT_PLUGIN, data_dir)
        paths = _exported(names, TINT_PLUGIN, data_dir, 1, '_d.dds')
        effects = tint.measure({n: tint.reduced(p) for n, p in paths.items()}, options)
        baseline = np.asarray(Image.open(paths[tint.BASELINE]).convert('RGBA'))
        out = tint.basis_path(female)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, effects=effects.astype(np.float16), options=np.array(options, np.uint32),
                            baseline=baseline, brows=np.array(brows, np.uint32))
    finally:
        (data_dir / TINT_PLUGIN).unlink(missing_ok=True)
        clear(TINT_PLUGIN, data_dir)
    return out


def calibrate_presets(data_dir: Path, female: bool = False) -> Path:
    """Measure and cache HumanRace's morph preset basis for one sex; the cache file."""
    race, template, body = _template(female)
    found = presets.race_presets(race.body, female)
    names = presets.calibration_plugin(data_dir / PRESET_PLUGIN, body, template.flags, found)
    try:
        clear(PRESET_PLUGIN, data_dir)
        run_ck(PRESET_PLUGIN)
        collect(PRESET_PLUGIN, data_dir)
        nifs = {n: p.read_bytes() for n, p in _exported(names, PRESET_PLUGIN, data_dir, 0, '.NIF').items()}
        out = presets.basis_path(female)
        morph_names = presets.morphs(found)
        np.savez_compressed(out, basis=presets.measure(nifs, morph_names), names=np.array(morph_names))
    finally:
        (data_dir / PRESET_PLUGIN).unlink(missing_ok=True)
        clear(PRESET_PLUGIN, data_dir)
    return out


#: --what -> the calibration it runs.
CALIBRATIONS = {'sculpt': calibrate, 'tints': calibrate_tints, 'presets': calibrate_presets}


def main():
    """Calibrate and print the cache path."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data', required=True, help='The MO2 mod folder the CK sees')
    ap.add_argument('--what', choices=tuple(CALIBRATIONS), default='sculpt', help='Which basis to measure')
    ap.add_argument('--female', action='store_true', help='Measure the female HumanRace basis')
    args = ap.parse_args()
    print('basis:', CALIBRATIONS[args.what](Path(args.data), args.female))


if __name__ == '__main__':
    main()
