"""A step-test interior for Fallout 4's player: labeled stations of steps, ramps and bare door lips.

    py -3.14 -m fo4_import.spike.step_map --out <StepTest.esp> --data <Data> [--export <FalloutNV.esm export>]

Each station is one static whose visible mesh is its collision (game units),
written through Elric as is (collision.mesh_collision: no winding repair, no
stairs pass), so what the player sees is what FO4 walks on. Its reference is
named Step<code> and its base StepTest_<code>; `coc StepTest` lands at the
south-west corner facing north. The build prints the legend (stations()).

See: docs/fork/fo4_spikes.md#step-map
"""

import argparse
import math
from pathlib import Path

import numpy as np

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.nif import bgsm
from fo4_import.nif import collision as C
from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import NONE
from fo4_import.nif.convert_static import DESC_PLAIN, IDENTITY, NODE_FLAGS, TEXTURE_SLOTS, SLOT_SPECULAR
from fo4_import.nif.convert_static import lighting_shader, vertices
from fo4_import.nif.elric import finish
from fo4_import.nif.file import NifFile
from fo4_import.spike import records as R
from fo4_import.spike.dialogue import vanilla_cell
from fo4_import.pipeline.mesh_cache import mesh_bounds
from pyffi.formats.nif import NifFormat
from tes5_import.base.tes5_reader import subrecords

MASTERS = ['Fallout4.esm']
CELL_EDID, MODEL_DIR = 'StepTest', 'steptest'
#: Fallout4.esm's COCMarkerHeading, where `coc` puts the player.
COC_MARKER = 0x32
#: Collision materials: FNV's stone and its stairs variant, as FO4 CRCs.
PLAIN, STAIRS = C.MATERIALS[0], C.STAIRS[0]
#: Vanilla materials the visible meshes show: the cell floor, a station, a stairs-material station.
LOOKS = {'floor': 'materials\\architecture\\diamondcity\\diamondconcretefloor01.bgsm',
         'station': 'materials\\interiors\\building\\bldfloorconcrete01.bgsm',
         'stairs': 'materials\\architecture\\diamondcity\\diamondconcretefloor01stairs.bgsm'}
#: The mobile home's doorway (MobileHomeASNV, game units): floor height, lip height, gap, far edge below the lip.
RISE, LIP, GAP, FAR = 46.9, 10.3, 22.4, -0.9
#: Its outer skirt: run toward the lip and height of the slanted face under the far edge.
SKIRT_RUN, SKIRT_HEIGHT = 6.8, 41.5
#: Station half width (the doorway is 96 wide), wall height above the platform, back-ramp slope.
HALF, WALL, BACK_RAMP = 48.0, 120.0, 20.0
#: FNV collision object whose body settings every station takes (static layer, fixed motion).
TEMPLATE = 'vehicles\\mobilehomeasnv.nif'
#: The converted mobile home (cell spike) and its FNV bounds, placed as controls when present.
CARAVAN, CARAVAN_BOUNDS = 'fnv\\vehicles\\mobilehomeasnv.nif', (-632, -163, -2, 412, 116, 296)
#: The mobile home's doorway cut out of its collision (its frame, game units) and where its frame stops in DNF.
DOOR_LO, DOOR_HI, FRAMELESS_TOP = (-380.0, 40.0, -10.0), (-210.0, 140.0, 300.0), 70.0
#: Station grid: column spacing, row spacing, row of each code's first letter.
COLUMN, ROW = 220.0, 520.0
ROWS = {'A': 0, 'S': 1, 'R': 1, 'C': 2, 'E': 3, 'G': 3, 'F': 4, 'K': 4, 'D': 5, 'H': 6}
#: Where the two control mobile homes stand (north of every row) and the cell floor's north edge.
CARAVAN_Y, FLOOR_NORTH = 7 * ROW + 300, 4300.0
#: Headroom doorframes: opening width (the home's door), jamb and lintel size, the step under one, clearances tried.
OPENING, FRAME, STEP_UP, CLEARANCES = 94.0, 30.0, 10.0, (130, 135, 140, 145, 150, 155, 160)


def _solid(faces: list) -> list:
    """Triangles of a convex solid's polygon `faces`, each wound outward; degenerate ones dropped."""
    pts = np.array([p for f in faces for p in f], dtype=float)
    centre, out = pts.mean(axis=0), []
    for face in faces:
        f = np.array(face, dtype=float)
        for k in range(1, len(f) - 1):
            tri = np.array([f[0], f[k], f[k + 1]])
            normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            if np.linalg.norm(normal) < 1e-6:
                continue
            out.append(tri if np.dot(normal, tri.mean(axis=0) - centre) > 0 else tri[[0, 2, 1]])
    return out


def _block(x0: float, x1: float, y0: float, y1: float, z0: float, top0: float, top1: float) -> list:
    """A solid over x0..x1, y0..y1 from z0 up to a top at `top0` (y0 edge) and `top1` (y1 edge): a box or a ramp."""
    lo = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
    hi = [(x0, y0, top0), (x1, y0, top0), (x1, y1, top1), (x0, y1, top1)]
    sides = [[lo[i], lo[(i + 1) % 4], hi[(i + 1) % 4], hi[i]] for i in range(4)]
    return _solid([lo, hi] + sides)


def _face(points: list, toward: tuple) -> list:
    """A zero-thickness polygon as triangles facing along `toward`."""
    f = np.array(points, dtype=float)
    tris = [np.array([f[0], f[k], f[k + 1]]) for k in range(1, len(f) - 1)]
    return [t if np.dot(np.cross(t[1] - t[0], t[2] - t[0]), toward) > 0 else t[[0, 2, 1]] for t in tris]


def _step(height: float, crc: int) -> list:
    """A block `height` tall and 128 deep, climbed going north."""
    return [(_block(-HALF, HALF, 0, 128, 0, height, height), crc)]


def _ramp(degrees: float) -> list:
    """A slope of `degrees` up to RISE, then a platform 64 deep."""
    run = RISE / math.tan(math.radians(degrees))
    return [(_block(-HALF, HALF, 0, run, 0, 0, RISE) + _block(-HALF, HALF, run, run + 64, 0, RISE, RISE), PLAIN)]


def _ledge(lip: float = LIP, gap: 'float | None' = GAP, far: float = FAR, thick: bool = False) -> list:
    """The mobile home's doorway, left going south: a RISE platform (back ramp to the north) ending in a bare lip
    `lip` tall, a `gap`, then the skirt's slanted face topping out `far` from the lip's top (no gap: no skirt)."""
    run = RISE / math.tan(math.radians(BACK_RAMP))
    top, front = RISE + lip, -(gap or 0) - 2
    tris = _block(-HALF, HALF, 0, 160, 0, RISE, RISE) + _block(-HALF, HALF, 160, 160 + run, 0, RISE, 0)
    tris += _block(-HALF - 2, -HALF, front, 160, 0, RISE + WALL, RISE + WALL)
    tris += _block(HALF, HALF + 2, front, 160, 0, RISE + WALL, RISE + WALL)
    if thick:
        tris += _block(-HALF, HALF, -1, 0, RISE, top, top)
    else:
        tris += _face([(-HALF, 0, RISE), (HALF, 0, RISE), (HALF, 0, top), (-HALF, 0, top)], (0, 1, 0))
    if gap is not None:
        edge = top + far
        tris += _face([(-HALF, -gap + SKIRT_RUN, edge - SKIRT_HEIGHT), (HALF, -gap + SKIRT_RUN, edge - SKIRT_HEIGHT),
                       (HALF, -gap, edge), (-HALF, -gap, edge)], (0, -1, 0))
    return [(tris, PLAIN)]


def _doorframe(clear: float, step: float) -> list:
    """A free-standing doorframe OPENING wide, walked through going north, its lintel `clear` above what the player
    stands on in it: the floor, or a `step` up that starts at the frame's south face and runs 128 past it."""
    side, inner, top = OPENING / 2 + FRAME, OPENING / 2, step + clear
    tris = _block(-side, -inner, -8, 8, 0, top, top) + _block(inner, side, -8, 8, 0, top, top)
    tris += _block(-side, side, -8, 8, top, top + FRAME, top + FRAME)
    if step:
        tris += _block(-side, side, -8, 128, 0, step, step)
    return [(tris, PLAIN)]


def _cut(poly: list, axis: int, bound: float, keep: int) -> list:
    """Polygon `poly` cut by the plane where coordinate `axis` is `bound`, keeping the side `keep` (+1 above)."""
    out = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        da, db = keep * (a[axis] - bound), keep * (b[axis] - bound)
        if da >= 0:
            out.append(a)
        if da * db < 0:
            out.append(a + (b - a) * da / (da - db))
    return out


def _clip(tri, lo: tuple, hi: tuple) -> list:
    """The triangles of what of `tri` lies inside the box lo..hi, wound as `tri`."""
    poly = [np.asarray(p, dtype=float) for p in tri]
    for axis in range(3):
        poly = _cut(_cut(poly, axis, lo[axis], 1), axis, hi[axis], -1)
        if len(poly) < 3:
            return []
    return [np.array([poly[0], poly[k], poly[k + 1]]) for k in range(1, len(poly) - 1)]


def _doorway(caravan: tuple, top: float) -> list:
    """The mobile home's own doorway collision below `top` (DOOR_LO..DOOR_HI), turned to be left going south and
    centred on x 0, its pivot kept (tilting moves it as it moves the home), on a platform with a back ramp."""
    parts = {}
    for tri, crc in zip(*caravan):
        for piece in _clip(tri, DOOR_LO, (*DOOR_HI[:2], top)):
            turned = piece * np.array([-1.0, -1.0, 1.0]) + np.array([(DOOR_LO[0] + DOOR_HI[0]) / 2, 0.0, 0.0])
            if np.linalg.norm(np.cross(turned[1] - turned[0], turned[2] - turned[0])) > 1e-6:
                parts.setdefault(crc, []).append(turned)
    half, back = (DOOR_HI[0] - DOOR_LO[0]) / 2, -DOOR_LO[1]
    run = RISE / math.tan(math.radians(BACK_RAMP))
    access = _block(-half, half, back, back + 110, 0, RISE, RISE) + _block(-half, half, back + 110, back + 110 + run,
                                                                           0, RISE, 0)
    access += _block(-half - 2, -half, -DOOR_HI[1] - 2, back + 110, 0, 350, 350)
    access += _block(half, half + 2, -DOOR_HI[1] - 2, back + 110, 0, 350, 350)
    return [(tris, crc) for crc, tris in parts.items()] + [(access, PLAIN)]


def stations(export_dir: Path) -> list:
    """[(code, what it tests, [(triangles, material)], X tilt in degrees)], in grid order."""
    out = [(f'A{h:02d}', f'plain step {h} tall', _step(h, PLAIN), 0.0) for h in range(6, 21)]
    out += [(f'S{h}', f'stairs-material step {h} tall', _step(h, STAIRS), 0.0) for h in (12, 16, 20, 24)]
    out += [(f'R{d}', f'ramp at {d} degrees', _ramp(d), 0.0) for d in (20, 30, 35, 40, 45, 50)]
    out += [(code, f'mobile home doorway, X tilt {tilt}', _ledge(), tilt)
            for code, tilt in (('C000', 0.0), ('C021', 0.2138), ('C030', 0.3038), ('C049', 0.4938),
                               ('C052', 0.5238), ('CN052', -0.5238))]
    out += [(f'E{h:02d}', f'doorway with a {h} lip', _ledge(lip=h), 0.0) for h in (6, 8, 12, 14)]
    out += [('GNO', 'doorway lip with no skirt beyond (open drop)', _ledge(gap=None), 0.0)]
    out += [(f'G{g:02d}', f'doorway with a {g} gap', _ledge(gap=g), 0.0) for g in (8, 15, 30)]
    out += [(code, f'doorway, skirt {far:+} from the lip top', _ledge(far=far), 0.0)
            for code, far in (('FM4', -4.0), ('F00', 0.0), ('FP1', 1.0))]
    out += [('K10', 'doorway with a 1-thick solid lip (a top)', _ledge(thick=True), 0.0)]
    caravan = C.mesh_triangles(str(export_dir / 'meshes' / TEMPLATE.replace('\\', '/')))
    out += [(code, f'mobile home doorway cut from its collision{note}, X tilt {tilt}', _doorway(caravan, top), tilt)
            for code, note, top, tilt in (('D000', '', DOOR_HI[2], 0.0), ('D052', '', DOOR_HI[2], 0.5238),
                                          ('DNF000', ' below 70 (no frame)', FRAMELESS_TOP, 0.0),
                                          ('DNF052', ' below 70 (no frame)', FRAMELESS_TOP, 0.5238))]
    out += [(f'H{c}', f'doorframe, lintel {c} above the floor', _doorframe(c, 0.0), 0.0) for c in CLEARANCES]
    out += [(f'HS{c}', f'doorframe on a {STEP_UP:g} step, lintel {c} above the step', _doorframe(c, STEP_UP), 0.0)
            for c in CLEARANCES]
    return out


def _render(tris: np.ndarray) -> tuple:
    """(positions, UVs, normals, triangles) of flat-shaded `tris` (n, 3, 3), UVs planar 1 per 256 units."""
    pos = tris.reshape(-1, 3)
    normal = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    nrm = np.repeat(normal, 3, axis=0)
    axis = np.abs(nrm).argmax(axis=1)
    uv = np.where((axis == 2)[:, None], pos[:, [0, 1]], np.where((axis == 1)[:, None], pos[:, [0, 2]], pos[:, [1, 2]]))
    return pos, uv / 256.0, nrm, np.arange(len(pos)).reshape(-1, 3)


def _nif(name: str, parts: list, look: str, template, materials: Archives) -> NifFile:
    """One station's NIF: a root with one lit shape showing `parts` in vanilla material `look`, and their collision."""
    tris = np.array([t for part, _ in parts for t in part], dtype=float)
    crcs = [crc for part, crc in parts for _ in part]
    pos, uv, nrm, faces = _render(tris)
    nif = NifFile()
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    textures = bgsm.read(materials.read(look))['textures']
    slots = [''] * TEXTURE_SLOTS
    slots[0], slots[1] = f'textures\\{textures["diffuse"]}', f'textures\\{textures["normal"]}'
    slots[SLOT_SPECULAR] = f'textures\\{textures["smooth_spec"]}'
    nif.blocks.append(('NiNode', {'name': nif.string(name), 'extra': [4], 'controller': NONE, 'flags': NODE_FLAGS,
                                  'translation': (0.0, 0.0, 0.0), 'rotation': IDENTITY, 'scale': 1.0,
                                  'collision': NONE, 'children': [1]}))
    nif.blocks.append(('BSTriShape', {
        'name': nif.string(name), 'extra': [], 'controller': NONE, 'flags': NODE_FLAGS, 'translation': (0.0, 0.0, 0.0),
        'rotation': IDENTITY, 'scale': 1.0, 'collision': NONE,
        'bound': (*map(float, centre), float(np.linalg.norm(pos - centre, axis=1).max())), 'skin': NONE, 'shader': 2,
        'alpha_property': NONE, 'vertex_desc': DESC_PLAIN, 'vertices': vertices(pos, uv, nrm, None, faces),
        'triangles': [tuple(map(int, t)) for t in faces]}))
    nif.blocks.append(('BSLightingShaderProperty', lighting_shader(nif, look, 3, 0)))
    nif.blocks.append(('BSShaderTextureSet', {'textures': slots}))
    nif.blocks.append(('BSXFlags', {'name': nif.string('BSX'), 'value': 0x82}))
    nif.blocks[0][1]['collision'] = C.mesh_collision(nif, 0, [tuple(map(tuple, t)) for t in tris], crcs, template)
    return nif


def _template(export_dir: Path):
    """The FNV mobile home's root collision object (its body settings are every station's)."""
    data = NifFormat.Data()
    with open(export_dir / 'meshes' / TEMPLATE.replace('\\', '/'), 'rb') as f:
        data.read(f)
    return data.roots[0].collision_object


def write_meshes(export_dir: Path, data_dir: Path) -> list:
    """Write every station's NIF (and the floor's) under <data_dir>/Meshes and run Elric; [(code, note, model, OBND,
    X tilt)], the floor first."""
    template, materials = _template(export_dir), Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Materials.ba2')
    floor = [(_block(-500, 3700, -500, FLOOR_NORTH, -32, 0, 0), PLAIN)]
    made = []
    for code, note, parts, tilt in [("Floor", "cell floor", floor, 0.0)] + stations(export_dir):
        look = 'floor' if code == 'Floor' else 'stairs' if parts[0][1] == STAIRS else 'station'
        nif = _nif(f'StepTest_{code}', parts, LOOKS[look], template, materials)
        model = f'{MODEL_DIR}\\{code.lower()}.nif'
        path = data_dir / 'Meshes' / model
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(nif_file.write(nif))
        made.append((code, note, model, mesh_bounds(nif), tilt))
    failed = finish([data_dir / 'Meshes' / m for _, _, m, _, _ in made])
    if failed:
        raise SystemExit(f'Elric failed on {failed}')
    return made


def _cell(fid: int) -> bytes:
    """The StepTest interior: QASmoke's lighting, lighting template and imagespace."""
    subs = dict(subrecords(vanilla_cell()[1]))
    template = int.from_bytes(subs.get(b'LTMP', bytes(4)), 'little')
    imagespace = int.from_bytes(subs.get(b'XCIM', bytes(4)), 'little')
    return R.pack_cell(fid, CELL_EDID, 'Step Test', 1, subs[b'XCLL'], template, imagespace)


def build(export_dir: Path, out: Path, data_dir: Path) -> list:
    """Write the meshes and the plugin; the stations [(code, note, model, OBND, X tilt)]."""
    made = write_meshes(export_dir, data_dir)
    w = FO4PluginWriter(masters=MASTERS, is_esm=False, description='FO4 step test map')
    refs, columns = b'', {}
    for code, _, model, bounds, tilt in made:
        base = w.derive_formid('StepTest STAT', code)
        w.add_record('STAT', R.pack_stat(base, f'StepTest_{code}', model, bounds))
        row = ROWS[code[0]] if code != 'Floor' else None
        columns[row] = columns.get(row, -1) + 1
        pos = (columns[row] * COLUMN, row * ROW, 0.0) if row is not None else (0.0, 0.0, 0.0)
        refs += R.pack_refr(w.derive_formid('StepTest REFR', code), base, pos, (math.radians(tilt), 0.0, 0.0),
                            edid=f'Step{code}')
    refs += R.pack_refr(w.derive_formid('StepTest REFR', 'COC'), COC_MARKER, (-300.0, -300.0, 0.0), (0.0, 0.0, 0.0))
    if (data_dir / 'Meshes' / CARAVAN).exists():
        refs += _caravans(w)
    cell = w.derive_formid('StepTest CELL', CELL_EDID)
    w.add_raw_group('CELL', R.pack_interior_cells([(_cell(cell), cell, refs, b'')]))
    out.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(out))
    return made


def _caravans(w: FO4PluginWriter) -> bytes:
    """Two converted mobile homes, door south, as controls: StepCaravanTilt (X 0.5238, which lets the player out in
    the Goodsprings cell) and StepCaravanFlat (no tilt, which traps them)."""
    base = w.derive_formid('StepTest STAT', 'Caravan')
    w.add_record('STAT', R.pack_stat(base, 'StepTest_Caravan', CARAVAN, CARAVAN_BOUNDS))
    heading, y = math.radians(183.205), CARAVAN_Y
    tilted = (math.radians(0.5238), math.radians(0.1478), heading)
    return (R.pack_refr(w.derive_formid('StepTest REFR', 'CaravanTilt'), base, (600.0, y, 0.0), tilted,
                        edid='StepCaravanTilt')
            + R.pack_refr(w.derive_formid('StepTest REFR', 'CaravanFlat'), base, (2000.0, y, 0.0), (0.0, 0.0, heading),
                          edid='StepCaravanFlat'))


def main():
    """Build the map and print its legend."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', default='export/FalloutNV.esm', help='FalloutNV.esm export (the body template)')
    ap.add_argument('--out', required=True, help='Plugin to write (StepTest.esp)')
    ap.add_argument('--data', required=True, help='Data folder for the meshes')
    args = ap.parse_args()
    for code, note, _, _, _ in build(Path(args.export), Path(args.out), Path(args.data)):
        print(f'Step{code:<6} {note}')


if __name__ == '__main__':
    main()
