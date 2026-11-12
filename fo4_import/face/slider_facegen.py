"""A FaceGen test mod on FO4's own sliders, exported by the Creation Kit, read through an MO2 profile's load order.

    py -3.14 -m fo4_import.face.slider_facegen --export <an FNV export> --out temp/facegen_heads/<mod name>
        --npcs <plugin>:<FormID>...

Per NPC: sculpt values and morph presets fitted to FNV's proportions
(proportions.unmaxed_fit), its own rear head part, and for an own hair a
chargen .tri (hair_morphs). The CK exports copies of the NPCs (new FormIDs in
a staging plugin in MO2's overwrite, so it writes only new files), the fit is
refined from what it made, and it exports again; each NPC keeps its better
round, renamed to the real NPC's paths. Skin: an NPC with its own face set
keeps the CK's face texture, with a skin tone matching it at the neck and a
rear head in FNV's whole skin; any other gets T1. Scratch only.

See: docs/fork/fo4_facegen_plan.md#slider-test
"""

import argparse
import functools
import re
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from asset_convert.character.facegen_tri import TriFile
from fo4_import.base.install import FALLOUT4_ESM
from fo4_import.base.source import record_dir
from fo4_import.face import facegeom, hair, hair_morphs, own_facegen, presets, proportions, sculpt, skin_seams, tint
from fo4_import.face import slider_records as records
from fo4_import.face.bake import FACE_PARTS, face_moves, face_shape, positions, seam_tree, triangles, uvs
from fo4_import.face.texture import bilinear, dds_like, texel_map, vanilla_face_texture, write_dds
from fo4_import.nif import file as nif_file
from fo4_import.pipeline import creation_kit
from fo4_import.spike.facegen import CK_TARGET, FACEGEN_DIRS, HUMAN_RACE, ck_timeout, skin_tone_layers
from fo4_import.spike.fnv_npc import fnv_face
from tes5_import.base.tes5_reader import subrecords, walk

#: The default --name: the test plugin's stem and our files' folder under Meshes and Textures.
NAME = 'FaceGenSliders'
#: How every FaceGen test plugin's description starts (own_facegen's and ours), so a run reads past them.
TEST_DESCRIPTION = 'FaceGen test'
#: The part type of a hair.
HAIR_PART = 3
#: CK rounds: export, refit from the CK's heads, export again.
ROUNDS = 2
#: Face points this near the neck seam give the face's colour there.
NECK_REACH = 1.0
#: A hair point this far inside the scalp clips it.
CLIPS = -0.05
#: Per sex (female?), Fallout4.esm's young face set (SkinHeadFemaleYoung, SkinHeadYoungMale) for --skin-maps young.
YOUNG_FACE_SETS = {True: 0x0F7E65, False: 0x16F83D}
#: HDPT part type of the eyes, and the face set slots of the skin maps it takes (normal TX01, specular TX07).
EYES_PART, SKIN_MAPS = 2, ((1, b'TX01'), (7, b'TX07'))


@dataclass(frozen=True)
class Problem:
    """One sex's fit: measure matrix, sculpt basis and regions, baseline face and FaceGeom, preset basis."""

    measures: np.ndarray
    basis: np.ndarray
    regions: list
    face: np.ndarray
    baseline: bytes
    presets: tuple
    eye_part: str


@dataclass(eq=False)
class Face:
    """One NPC under test: its records, FNV colour (head, pieces), target measures and what the run made."""

    plugin: str
    form_id: int
    npc: facegeom.Rec
    race: facegeom.Rec
    female: bool
    colour: tuple
    target: np.ndarray
    fit: proportions.Fit = None
    tone: np.ndarray = None
    rounds: list = field(default_factory=list)

    @property
    def stem(self) -> str:
        """The NPC's FaceGen file stem."""
        return f'{self.form_id:08X}'


@dataclass
class Job:
    """What every NPC of one run shares."""

    src: facegeom.Sources
    dirs: list
    order: list
    out: Path
    templates: dict
    layers: frozenset
    #: The fit's target shape (bake variant C1 or C2F), and whether own face sets take the young skin maps.
    shape: str = 'C2F'
    young: bool = True
    #: The test plugin's stem (its staging plugin adds 'CK') and our files' folder under Meshes and Textures.
    name: str = NAME
    copies: dict = field(default_factory=dict)

    @property
    def staging(self) -> str:
        """The staging plugin the CK exports."""
        return f'{self.name}CK.esp'


@functools.cache
def human_race() -> bytes:
    """Fallout4.esm's HumanRace body."""
    return next(r for r, _ in walk(FALLOUT4_ESM.read_bytes(), b'RACE') if r.form_id == HUMAN_RACE).body


@functools.cache
def problem(female: bool) -> Problem:
    """The fit problem for one sex (the sculpt and preset bases must be measured)."""
    basis, regions, baseline = sculpt.load_basis(female)
    face = face_shape(baseline)[0]
    names = proportions.region_names(human_race(), female)
    measures = proportions.measure_matrix(proportions.region_sets(basis, regions, names, face), face)
    morph_basis, morphs = presets.load_basis(female)
    picks = {(p.group, p.morph): p.key for p in presets.race_presets(human_race(), female) if p.morph in morphs}
    eye_part = next(name for name in shapes(baseline) if name in eye_parts())
    return Problem(measures, basis, regions, face, baseline,
                   (morph_basis, [(g, key, morphs.index(m)) for (g, m), key in picks.items()]), eye_part)


@functools.cache
def eye_parts() -> frozenset:
    """Fallout4.esm's eyes head part EditorIDs."""
    out = set()
    for rec, _ in walk(FALLOUT4_ESM.read_bytes(), b'HDPT'):
        subs = dict(subrecords(rec.body))
        if subs.get(b'PNAM') == struct.pack('<I', EYES_PART):
            out.add(facegeom.zstr(subs[b'EDID']))
    return frozenset(out)


def old_values(npc: facegeom.Rec, regions: list) -> np.ndarray:
    """The record's own sculpt values [region, CONTROLS]."""
    out, region = np.zeros((len(regions), sculpt.CONTROLS)), None
    for tag, data in npc.subs:
        region = struct.unpack('<I', data)[0] if tag == b'FMRI' else region
        if tag == b'FMRS' and region in regions:
            out[regions.index(region)] = struct.unpack_from('<7f', data)
    return out


def measured(p: Problem, nif_bytes: bytes) -> np.ndarray:
    """A FaceGeom's measures off the baseline face."""
    return p.measures @ (face_shape(nif_bytes)[0] - p.face).ravel()


def part_of(src, face: Face, part_type: int) -> tuple:
    """(the NPC's head part of `part_type` (Rec), its PNAM bytes or None when the race gives it)."""
    part = next(p for p in facegeom.head_parts(src, face.npc, face.race, face.female)
                if facegeom.part_type(p) == part_type)
    raw = next((d for t, d in face.npc.subs if t == b'PNAM' and src.get(face.npc, d) is part), None)
    return part, raw


def rear_path(job, face: Face) -> str:
    """The NPC's own rear head texture, under Textures."""
    return f'{job.name}\\{face.plugin[:-4]}_{face.stem}_rear_d.dds'


def own_hairs(job, faces: list) -> dict:
    """{PNAM bytes: (hair part Rec, chargen .tri path under Meshes, female)} of the faces' own hairs (not from
    Fallout4.esm)."""
    out = {}
    for face in faces:
        part, raw = part_of(job.src, face, HAIR_PART)
        if raw and part.owner != 'fallout4.esm':
            out[raw] = (part, f'{job.name}\\{facegeom.zstr(part.first(b"EDID"))}Chargen.tri', face.female)
    return out


def npc_body(job: Job, face: Face, rear: int, staging: bool) -> tuple:
    """(the NPC's FormID (its plugin's own index is the test plugin's, a master prefix), record flags, its
    subrecords as the test plugin overrides it, on rear head part `rear`)."""
    _, old = part_of(job.src, face, records.REAR_PART)
    rec = records.source_record(own_facegen.find(job.dirs, face.plugin), face.form_id)
    body = records.fitted_npc(rec.body, face.fit, problem(face.female).regions, (old, rear))
    if face.tone is not None:
        body = own_facegen.with_template_tone(body, job.templates[face.female], face.tone, job.layers)
    if staging:
        body = records.pack((t, d[:-1] + b'CK\0' if t == b'EDID' else d) for t, d in subrecords(body))
    return rec.form_id, rec.flags, body


def plugin(job: Job, faces: list, staging: bool) -> records.TestPlugin:
    """The test plugin's records; `staging` makes NPC copies (new FormIDs, EditorIDs + 'CK') for the CK, listed
    in job.copies by local id."""
    names = sorted({f.plugin for f in faces}, key=lambda n: [o.lower() for o in job.order].index(n.lower()))
    out = records.TestPlugin([own_facegen.find(job.dirs, n) for n in names])
    for face in faces:
        rear, _ = part_of(job.src, face, records.REAR_PART)
        edid = f'{job.name}Rear_{face.plugin[:-4]}_{face.stem}'
        textures = facegeom.body_textures(job.src, face.npc, face.race, face.female)
        txst = out.add('TXST', out.new_id(), records.rear_texture_set(edid + 'Set', textures, rear_path(job, face)))
        part = out.add('HDPT', out.new_id(), records.rear_part(rear, edid, txst))
        form_id, flags, body = npc_body(job, face, part, staging)
        npc_id = out.add('NPC_', out.new_id() if staging else form_id, body, flags)
        if staging:
            job.copies[npc_id & 0xFFFFFF] = face
    for raw, (part, tri, _) in own_hairs(job, faces).items():
        out.add('HDPT', struct.unpack('<I', raw)[0], records.with_chargen_tri(part, tri))
    for raw, (face_set, maps) in (young_skins(job, faces) if job.young else {}).items():
        out.add('TXST', struct.unpack('<I', raw)[0], records.with_skin_maps(face_set, maps))
    return out


def young_skins(job: Job, faces: list) -> dict:
    """{FTST bytes: (face set Rec, {TX tag: path})}: each own face set (not Fallout4.esm's) with its sex's young
    face set's normal and specular maps."""
    out = {}
    for face in faces:
        raw = face.npc.first(b'FTST')
        face_set = job.src.get(face.npc, raw) if raw else None
        if face_set and face_set.owner != 'fallout4.esm':
            young = facegeom.txst_slots(job.src, job.src.records['fallout4.esm', YOUNG_FACE_SETS[face.female]])
            out[raw] = (face_set, {tag: young[slot] for slot, tag in SKIN_MAPS if young[slot]})
    return out


def chargen_head(female: bool) -> str:
    """The base head's chargen .tri for one sex, under Meshes."""
    return 'Actors\\Character\\CharacterAssets\\' + ('BaseFemaleHeadChargen.tri' if female else
                                                     'BaseMaleHeadCharGen.tri')


def own_files(job: Job, faces: list) -> dict:
    """{path under Data: bytes} the plugin needs beside it: own hairs' .tri files and rear texture stand-ins."""
    out = {}
    for part, tri, female in own_hairs(job, faces).values():
        nif = nif_file.read(job.src.read('meshes\\' + facegeom.zstr(part.first(b'MODL'))))
        raw = next(b for k, b in nif.blocks if k in facegeom.SHAPES and isinstance(b, bytes))
        head = TriFile.from_bytes(job.src.read('meshes\\' + chargen_head(female)))
        out[f'Meshes\\{tri}'] = hair_morphs.part_tri(head, raw)
    for face in faces:
        textures = facegeom.body_textures(job.src, face.npc, face.race, face.female)
        out[f'Textures\\{rear_path(job, face)}'] = job.src.read('textures\\' + textures[0])
    return out


def ck_export(job: Job, faces: list) -> dict:
    """Export the staging plugin's heads with the CK through MO2; {Face: FaceGeom NIF bytes} (face textures copied
    to the test mod as the NPC's own)."""
    stage = creation_kit.output_dir()
    files = own_files(job, faces)
    job.copies.clear()
    plugin(job, faces, staging=True).write(stage / job.staging)
    for rel, data in files.items():
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_bytes(data)
    try:
        for folder in FACEGEN_DIRS:
            shutil.rmtree(stage / folder / job.staging, ignore_errors=True)
        creation_kit.run(f'-ExportFaceGenData:{job.staging} {CK_TARGET}', ck_timeout(len(faces)), 'exporting the test')
        return collect(job, stage)
    finally:
        for rel in [*files, job.staging]:
            (stage / rel).unlink(missing_ok=True)
        for folder in {(stage / rel).parent for rel in files}:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        for folder in FACEGEN_DIRS:
            shutil.rmtree(stage / folder / job.staging, ignore_errors=True)


def collect(job: Job, stage: Path) -> dict:
    """{Face: FaceGeom NIF bytes} of the CK's export of the copies; their face textures copied to the test mod
    under the real NPCs' names, re-encoded as vanilla's."""
    out = {}
    for local, face in job.copies.items():
        nif = (stage / FACEGEN_DIRS[0] / job.staging / f'{local:08X}.nif').read_bytes()
        folder = job.out / FACEGEN_DIRS[1] / face.plugin
        folder.mkdir(parents=True, exist_ok=True)
        for made in (stage / FACEGEN_DIRS[1] / job.staging).glob(f'{local:08X}_*'):
            target = folder / (face.stem + made.name[8:])
            shutil.copyfile(made, target)
            vanilla_face_texture(target)
        out[face] = renamed(nif, f'{job.staging}\\{local:08X}', f'{face.plugin}\\{face.stem}')
    return out


def renamed(nif_bytes: bytes, old: str, new: str) -> bytes:
    """The FaceGeom NIF with texture paths naming `old` (any case) naming `new`."""
    nif = nif_file.read(nif_bytes)
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    for _, block in nif.blocks:
        if isinstance(block, dict) and 'textures' in block:
            block['textures'] = [pattern.sub(new.replace('\\', '\\\\'), t) for t in block['textures']]
    return nif_file.write(nif)


def new_face(job: Job, export: Path, plugin_name: str, form_id: int) -> Face:
    """NPC `form_id` of `plugin_name` with its FNV colour and target measures (job.shape's moves of FO4's
    baseline face)."""
    npc, race, female, _ = facegeom.npc_face(job.src, plugin_name, form_id)
    colour = fnv_face(record_dir(export, plugin_name), own_facegen.fnv_edid(npc))
    p = problem(female)
    target = p.measures @ face_moves(p.baseline, colour[0], job.shape, p.eye_part)[1].ravel()
    return Face(plugin_name, form_id & 0xFFFFFF, npc, race, female, colour, target)


def rms(values: np.ndarray) -> float:
    """Root mean square."""
    return float(np.sqrt((values ** 2).mean()))


def fit_rounds(job: Job, faces: list) -> dict:
    """{Face: FaceGeom NIF bytes} of each face's best CK round; each round refits to the target moved by the
    previous round's miss (face.rounds: (fit, NIF, measures))."""
    aim = {face: face.target for face in faces}
    for _ in range(ROUNDS):
        for face in faces:
            p = problem(face.female)
            face.fit = proportions.unmaxed_fit(p.measures, p.basis, p.presets, aim[face])
        nifs = ck_export(job, faces)
        for face in faces:
            actual = measured(problem(face.female), nifs[face])
            face.rounds.append((face.fit, nifs[face], actual))
            aim[face] = aim[face] + face.fit.predicted - actual
    best = {}
    for face in faces:
        face.fit, best[face], _ = min(face.rounds, key=lambda r, f=face: rms(r[2] - f.target))
    return best


def neck_tone(drawn: np.ndarray, face_geo: tuple, seam, body: tuple) -> np.ndarray:
    """The skin tint drawing the body at the neck as the face texture `drawn` (RGB) is there."""
    points, uv, _ = face_geo
    near = seam.query(points)[0] < NECK_REACH
    face_colour = np.median(bilinear(drawn, uv[near]), 0)
    return face_colour / np.median(skin_seams.body_drawn(points[near], body, np.ones(3)), 0)


def whole_scale(drawn: np.ndarray, face_geo: tuple, colour: tuple) -> np.ndarray:
    """Per channel, the face texture `drawn` (RGB) over FNV's whole skin on the same face texels."""
    fnv, (stock, offset, race_skin) = colour
    rows, cols, fnv_uv, _ = texel_map(face_geo, (fnv.mean, fnv.triangles, fnv.uvs), drawn.shape[:2])
    whole = bilinear(stock, fnv_uv) + bilinear(offset, fnv_uv)
    whole += 0 if race_skin is None else bilinear(race_skin, fnv_uv)
    return np.median(drawn[rows, cols], 0) / np.median(whole, 0)


def own_face_texture(diffuse: Path, face_geo: tuple, colour: tuple) -> np.ndarray:
    """Rewrite the CK's face texture of an own face set at `diffuse`, scaled per channel to FNV's whole skin
    (its median over the face); its RGB as floats.
    See: docs/fork/fo4_facegen_plan.md#willow-skin
    """
    rgba = hair.image(diffuse.read_bytes()).astype(float)
    rgba[..., :3] /= whole_scale(rgba[..., :3], face_geo, colour)
    rgba = np.clip(rgba, 0, 255).astype(np.uint8)
    write_dds(rgba, diffuse)
    vanilla_face_texture(diffuse)
    return rgba[..., :3].astype(float)


def skin(job: Job, face: Face, nif: bytes) -> tuple:
    """Write the face's skin and set its tone: an own face set keeps the CK's face texture (own_face_texture),
    toned to match at the neck, its rear head in FNV's whole skin; otherwise T1. (the FaceGeom on it,
    own_rear's note)."""
    face_geo, seam = face_shape(nif), seam_tree(nif)
    template = np.array(struct.unpack('<4f', job.templates[face.female][0])[:3])
    body = own_facegen.body(job.src, face.npc, face.race, face.female)
    diffuse = job.out / FACEGEN_DIRS[1] / face.plugin / f'{face.stem}_d.dds'
    whole = None
    if face.npc.first(b'FTST'):
        drawn = own_face_texture(diffuse, face_geo, face.colour)
        face.tone = neck_tone(drawn, face_geo, seam, body) / template
        whole = np.ones(3)
    else:
        rgba, face.tone = skin_seams.face_texture(tint.load_basis(face.female)[2], face_geo, *face.colour,
                                                  (seam, body, lambda s: np.clip(template * s, 0.0, 1.0)))
        write_dds(rgba, diffuse)
        vanilla_face_texture(diffuse)
    qnam = np.clip(template * face.tone, 0.0, 1.0)
    face.tone = qnam / template
    return own_rear(job, face, nif, (face_geo[0], (seam, (template, qnam)), whole))


def own_rear(job: Job, face: Face, nif_bytes: bytes, rear: tuple) -> tuple:
    """(the FaceGeom with its rear head on the NPC's own texture, written under the test mod, and drawn with its
    skin tint; (the rear shape's name, whether the CK already drew it on that texture)). `rear` = (face points,
    neck as rear_texture takes it, whole scale or None)."""
    frame, neck, whole = rear
    nif = nif_file.read(nif_bytes)
    own = job.src.read('textures\\' + facegeom.body_textures(job.src, face.npc, face.race, face.female)[0])
    note = None
    for kind, raw in list(nif.blocks):
        sh = nif.blocks[hair.shader_index(raw)][1] if kind in facegeom.SHAPES and isinstance(raw, bytes) else None
        if not isinstance(sh, dict) or sh.get('skin_tint') is None:
            continue
        texture_set = nif.blocks[sh['texture_set']][1]['textures']
        note = (nif.strings[struct.unpack_from('<i', raw)[0]], texture_set[0].lower() == rear_path(job, face).lower())
        rgba = skin_seams.rear_texture(hair.image(own), (positions(raw), uvs(raw), triangles(raw)), frame,
                                       face.colour, neck, whole)
        path = job.out / 'Textures' / rear_path(job, face).replace('\\', '/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(dds_like(rgba, own))
        texture_set[0] = rear_path(job, face)
        sh['skin_tint'] = (*(np.round(neck[1][1] * 255) / 255).tolist(), sh['skin_tint'][3])
    return nif_file.write(nif), note


def shapes(nif_bytes: bytes) -> dict:
    """{shape name: (points, triangles, shader)} of a NIF."""
    nif = nif_file.read(nif_bytes)
    return {nif.strings[struct.unpack_from('<i', raw)[0]]: (positions(raw), triangles(raw),
                                                             nif.blocks[hair.shader_index(raw)][1])
            for kind, raw in nif.blocks if kind in facegeom.SHAPES and isinstance(raw, bytes)}


def scalp(parts: dict) -> tuple:
    """(points, triangles) of the face and the skin-tint (rear head) parts together."""
    points, tris = [], []
    for name, (p, t, sh) in parts.items():
        if name in FACE_PARTS or (isinstance(sh, dict) and sh.get('skin_tint') is not None):
            tris.append(t + sum(len(q) for q in points))
            points.append(p)
    return np.vstack(points), np.vstack(tris)


def hair_clearance(job: Job, face: Face, nif: bytes) -> 'str | None':
    """How the face's own hair sits off the scalp in the CK's head against our unmorphed build; None for none."""
    part, raw = part_of(job.src, face, HAIR_PART)
    if not raw or part.owner == 'fallout4.esm':
        return None
    name = facegeom.zstr(part.first(b'EDID'))
    ck, ref = shapes(nif), shapes(facegeom.build(job.src, face.plugin, face.form_id))
    c_ck, c_ref = (hair_morphs.clearance(s[name][0], scalp(s)) for s in (ck, ref))
    near, change = c_ref < 1.0, c_ck - c_ref
    moved = np.linalg.norm(ck[name][0] - ref[name][0], axis=1)
    return (f'hair {name}: points inside the scalp (< {CLIPS}) CK {(c_ck < CLIPS).sum()} vs unmorphed '
            f'{(c_ref < CLIPS).sum()} of {len(c_ck)}; the {near.sum()} points within 1 of it: clearance median '
            f'{np.median(c_ref[near]):.2f} -> {np.median(c_ck[near]):.2f}, change {change[near].min():.2f}'
            f'..{change[near].max():.2f}; hair moved median {np.median(moved):.2f} max {moved.max():.2f}')


def fit_report(face: Face) -> list:
    """Lines: the fit's bound count, presets and proportion errors (old fit, new predicted, new from the CK)."""
    p = problem(face.female)
    olds = old_values(face.npc, p.regions)
    old = p.measures @ (p.basis.reshape(len(p.basis), -1).T @ olds.ravel())
    actual = next(a for f, _, a in face.rounds if f is face.fit)
    rounds = ', '.join(f'round {i + 1} CK {rms(a - face.target):.3f}' for i, (_, _, a) in enumerate(face.rounds))
    lines = [f'{face.plugin}:{face.stem} {own_facegen.fnv_edid(face.npc)}: at bound (|v| >= {proportions.BOUND}) '
             f'{proportions.at_bound(face.fit)}, max |sculpt| {np.abs(face.fit.sculpt).max():.2f}; old fit at |1| '
             f'{int((np.abs(olds) >= 0.999).sum())}; presets {[(hex(k), round(v, 2)) for k, _, v in face.fit.presets]}',
             f'  rms vs FNV: none {rms(face.target):.3f}, old {rms(old - face.target):.3f} (predicted), new '
             f'{rms(face.fit.predicted - face.target):.3f} (predicted), {rounds}',
             f'  {"measure":14s} {"FNV":>7s} {"old":>7s} {"new":>7s} {"new CK":>7s}']
    for i, (name, *_) in enumerate(proportions.MEASURES):
        lines.append(f'  {name:14s} {face.target[i]:7.3f} {old[i]:7.3f} {face.fit.predicted[i]:7.3f} {actual[i]:7.3f}')
    return lines


def without_tests(profile: Path, out: str) -> tuple:
    """own_facegen.profile_order of `profile` without mod folder `out`, any FaceGen test plugin (its description
    starts TEST_DESCRIPTION) and the mod folders holding one."""
    dirs, order = own_facegen.profile_order(profile, creation_kit.MO2, (out,))
    tests = {name for name in order if own_facegen.find(dirs, name).is_file()
             and description(own_facegen.find(dirs, name).read_bytes()).startswith(TEST_DESCRIPTION)}
    return [d for d in dirs if not any((d / name).is_file() for name in tests)], [n for n in order if n not in tests]


def description(data: bytes) -> str:
    """A plugin's description (TES4 SNAM)."""
    size = struct.unpack_from('<I', data, 4)[0]
    return next((facegeom.zstr(d) for t, d in subrecords(data[24:24 + size]) if t == b'SNAM'), '')


def main(argv=None) -> None:
    """Write the test mod folder --out for --npcs (plugin:FormID) through --profile's load order."""
    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument('--profile', type=Path, help="MO2 profile folder (default: MO2's selected profile)")
    p.add_argument('--export', type=Path, required=True, help='an FNV export folder (others found beside it)')
    p.add_argument('--out', type=Path, required=True, help='the test mod folder (scratch)')
    p.add_argument('--npcs', nargs='+', required=True, help='plugin:FormID (hex)')
    p.add_argument('--shape', default='C2F', choices=('C1', 'C2F'), help='the target shape (bake variant)')
    p.add_argument('--skin-maps', default='young', choices=('young', 'own'), help="own face sets' normal/specular")
    p.add_argument('--name', default=NAME, help="the test plugin's stem and our files' folder")
    args = p.parse_args(argv)
    dirs, order = without_tests(args.profile or creation_kit.profile_dir(), args.out.name)
    npcs = [(name, int(fid, 16)) for name, fid in (item.rsplit(':', 1) for item in args.npcs)]
    deepest = max((n for n, _ in npcs), key=lambda n: [o.lower() for o in order].index(n.lower()))
    esm = FALLOUT4_ESM.read_bytes()
    layers = skin_tone_layers(esm)
    job = Job(facegeom.Sources(own_facegen.find(dirs, deepest), dirs, order), dirs, order, args.out,
              own_facegen.template_tones(esm, layers), layers, args.shape, args.skin_maps == 'young', args.name)
    faces = [new_face(job, args.export, name, fid) for name, fid in npcs]
    finish(job, faces, fit_rounds(job, faces))


def finish(job: Job, faces: list, nifs: dict) -> None:
    """Skin each face, write its FaceGeom, the own hairs' .tri files and the test plugin; print the report."""
    for face in faces:
        nif, rear = skin(job, face, nifs[face])
        geom = job.out / own_facegen.GEOM_DIR / face.plugin / f'{face.stem}.nif'
        geom.parent.mkdir(parents=True, exist_ok=True)
        geom.write_bytes(nif)
        print('\n'.join(fit_report(face)))
        print(f'  rear head: shape {rear[0]}, the CK drew it on its own texture: {rear[1]}; skin tone x'
              f'{np.round(face.tone, 3).tolist()}', flush=True)
        clearance = hair_clearance(job, face, nif)
        print(f'  {clearance}' if clearance else "  hair: the build's own match, unchanged")
    for rel, data in own_files(job, faces).items():
        if rel.startswith('Meshes'):
            (job.out / rel.replace('\\', '/')).parent.mkdir(parents=True, exist_ok=True)
            (job.out / rel.replace('\\', '/')).write_bytes(data)
    print('plugin masters:', plugin(job, faces, staging=False).write(job.out / f'{job.name}.esp'))


if __name__ == '__main__':
    main()
