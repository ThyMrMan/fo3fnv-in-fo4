"""Fit FNV outfits onto a Fallout 4 body NIF (vanilla's, or a body mod's such as CBBE's), write the worn NIFs,
and measure them: per shape the distance to the body, and for bare skin how far its UVs are from the UVs of a
body (`--against`) at the same points, which is what the skin samples on that body's texture.

    py -3.14 tools/nif/fo4_body_fit_check.py --export export/FalloutNV.esm --sex female --out D:/scratch/fit
        --models armor/lingerie/outfitf.nif --body <CBBE>/meshes/actors/character/characterassets/FemaleBody.nif
        [--against <body NIF>] [--bodyslide <mod>/Tools/BodySlide --template "CBBE Body"]

With `--bodyslide`, each worn outfit also gets a BodySlide project under `--out`/Tools/BodySlide (the body's
sliders conformed onto it, fo4_import.nif.bodyslide), in group "F3NV check". One JSON line per shape.

See: docs/fork/fo4_bodies_cbbe.md#bare-skin
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.face.bake import surface
from fo4_import.nif import bodyslide, file as nif_file, outfit
from fo4_import.nif.blocks import SHADER_SKIN_TINT, Reader, read_tri_shape
from fo4_import.pipeline.export_index import export_file
from tools.nif.fnv_convert_check import run_static

#: The BodySlide group the check's projects go in.
GROUP = 'F3NV check'


def body_surface(data: bytes) -> tuple:
    """(surface points, UV per point) of a body NIF's first BSSubIndexTriShape."""
    nif = nif_file.read(data)
    shape = read_tri_shape(Reader(next(b for k, b in nif.blocks if k == 'BSSubIndexTriShape')))
    points = np.array([v['position'] for v in shape['vertices']], float)
    uv, tris = np.array([v['uv'] for v in shape['vertices']], float), np.array(shape['triangles'])
    samples, owner, bary = surface(points, tris)
    return samples, (bary[:, :, None] * uv[tris[owner]]).sum(1)


def measured(worn: bytes, body: tuple, against: tuple) -> list:
    """Per shape of worn NIF `worn`: its name, vertices, distance to `body` and, for skin, its UV gap on
    `against` (each a body_surface)."""
    nif, out = nif_file.read(worn), []
    near_body, near_against = cKDTree(body[0]), cKDTree(against[0])
    for kind, raw in nif.blocks:
        if kind != 'BSSubIndexTriShape':
            continue
        shape = read_tri_shape(Reader(raw))
        points = np.array([v['position'] for v in shape['vertices']], float)
        dist = near_body.query(points)[0]
        line = {'shape': nif.strings[shape['name']], 'vertices': len(points),
                'body_gap_median': round(float(np.median(dist)), 3), 'body_gap_p90': round(float(np.percentile(dist, 90)), 3)}
        if nif.blocks[shape['shader']][1]['shader_type'] == SHADER_SKIN_TINT:
            uv = np.array([v['uv'] for v in shape['vertices']], float)
            gap = np.linalg.norm(uv - against[1][near_against.query(points)[1]], axis=1)
            line.update(uv_gap_median=round(float(np.median(gap)), 4), uv_gap_p90=round(float(np.percentile(gap, 90)), 4))
        out.append(line)
    return out


def write_projects(worn: dict, args) -> None:
    """BodySlide projects of {model: worn NIF bytes} under args.out/Tools/BodySlide, on args.template."""
    tools = args.out / 'Tools' / 'BodySlide'
    data = tools / 'ShapeData' / GROUP
    data.mkdir(parents=True, exist_ok=True)
    ref = bodyslide.reference(Path(args.bodyslide), args.template)
    sets = []
    for model, nif in worn.items():
        stem = Path(model).with_suffix('')
        name = f'{GROUP} - {stem.as_posix().replace("/", " ")}'
        (data / f'{name}.nif').write_bytes(nif)
        out_path = str(Path('Meshes') / stem.parent).replace('/', '\\')
        made, osd = bodyslide.project(name, bodyslide.shapes(nif), ref, (GROUP, f'{name}.nif', out_path, stem.name))
        (data / f'{name}.osd').write_bytes(osd)
        sets.append(made)
    (tools / 'SliderSets').mkdir(exist_ok=True)
    (tools / 'SliderGroups').mkdir(exist_ok=True)
    (tools / 'SliderSets' / f'{GROUP}.osp').write_bytes(bodyslide.slider_sets(sets))
    (tools / 'SliderGroups' / f'{GROUP}.xml').write_bytes(bodyslide.slider_group(GROUP, [s.get('name') for s in sets]))


def main() -> None:
    """Fit, write and measure each model; write BodySlide projects when asked."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--export', type=Path, default=ROOT / 'export' / 'FalloutNV.esm')
    parser.add_argument('--models', nargs='+', required=True, help='FNV outfit models under meshes')
    parser.add_argument('--sex', choices=('male', 'female'), default='female')
    parser.add_argument('--body', type=Path, help="body NIF to fit to (default: Fallout 4's own)")
    parser.add_argument('--against', type=Path, help='body NIF whose UVs skin is measured on (default: --body)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bodyslide', help="a BodySlide folder holding the body's slider set (Tools/BodySlide)")
    parser.add_argument('--template', default='CBBE Body', help='the BodySlide reference template to conform to')
    args = parser.parse_args()
    archives = Archives(FALLOUT4_DIR / 'Data')
    body_nif = args.body.read_bytes() if args.body else archives.read(outfit.FO4_BODIES[args.sex])
    fit = outfit.body_fit(args.export, args.sex, archives, body_nif)
    body = body_surface(body_nif)
    against = body_surface(args.against.read_bytes()) if args.against else body
    worn = {}
    for model in args.models:
        path = export_file(args.export, 'meshes', model)
        worn[model] = outfit.worn(nif_file.write(run_static(str(path)).nif), path, fit)
        target = args.out / 'meshes' / model
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(worn[model])
        for line in measured(worn[model], body, against):
            print(json.dumps({'model': model, **line}), flush=True)
    if args.bodyslide:
        write_projects(worn, args)


if __name__ == '__main__':
    main()
