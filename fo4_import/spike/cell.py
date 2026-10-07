"""Spike 2 step 2: an FNV interior cell rebuilt in Fallout 4.

    py -3.14 -m fo4_import.spike.cell --export <FalloutNV.esm export> --out <plugin.esp> --data <Data> <cell EDID>

The cell keeps FNV's lighting, every placed object with a mesh, its lights,
doors, misc items, containers, furniture and activators with their
converted scripts (other types are statics for now). A door that led out of
the cell leads to a stand-in door in QASmoke, and back. Engine objects FO4
shares keep their base. Meshes get FNV's collision through Elric. Sounds are
a later step.

See: docs/fork/fo4_spikes.md#spike-2-cell
"""

import argparse
import collections
import math
import struct
from pathlib import Path

from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest
from fo4_import.face import hair, tint
from fo4_import.face.sculpt import FACE_SHAPE
from fo4_import.face.sculpt import load_basis as sculpt_basis
from fo4_import.spike.face_fit import sculpt_fit, tint_fit
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.head_parts import choose, head_parts_edit
from fo4_import.spike.imagespace import BASE_IMAGESPACE, base_hdr, pack_imgs, write_lut
from fo4_import.spike.activators import Activators
from fo4_import.spike.attach import ObjectScripts
from fo4_import.spike.furniture import furniture, markers
from fo4_import.spike.navmesh import navi, navmeshes
from fo4_import.spike.items import ENGINE_IDS, ITEM_TYPES, Items, index, shared_engine_ids
from fo4_import.nif.elric import finish
from fo4_import.spike import records as R
from fo4_import.spike import voice
from fo4_import.spike.dialogue import CELL_FO4, SPEAKERS, VOICES
from fo4_import.spike.say_topics import SayTopics
from fo4_import.spike.script import compile_into
from fo4_import.spike.quest import quest_record
from fo4_import.spike.statics import write_assets
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from tes5_import.base.tes5_reader import first_sub, sub_map, walk
from tes5_import.base.text_reader import parse_export_file

MASTERS = ['Fallout4.esm', FALLOUT4_HELPER_PLUGIN]
#: Master index of the helper plugin (TES4Helpers.esl).
HELPER_INDEX = 1
#: Stand-in subrecords a clone leaves out: its factions (vanilla doctor dialogue, caravans) and crime faction.
STAND_IN_TIES = frozenset({b'SNAM', b'CRIF'})
#: The player's reference, the same FormID in both games.
PLAYER = 0x14
#: FNV quests the cell's scripts run, converted with it.
CELL_QUESTS = ('VCG01',)
FIRST_ID = 0x800
#: FNV base types placed as FO4 statics (their mesh only) until each gets its own conversion.
AS_STATIC = ('STAT', 'MSTT', 'ALCH', 'WEAP', 'ARMO', 'BOOK', 'KEYM', 'NOTE', 'AMMO', 'TERM', 'IDLM')
#: FNV base types converted as themselves (spike.items), and the types whose engine objects FO4 may share.
ITEM_BASES, SHARED_TYPES = ('MISC', 'CONT'), ('STAT', 'MISC')
#: Stand-in doors in QASmoke: the first one's position and the spacing along X.
DOOR_START, DOOR_SPACING = (-1700.0, -1184.0, 0.0), 300.0
#: Where a stand-in door puts the player: offset from the door, facing +X, away from it.
ARRIVAL, ARRIVAL_ROT = (100.0, 64.0, 0.0), (0.0, 0.0, math.pi / 2)
#: FNV LIGH flag bits as FO4 ones: carried, flicker (and slow), off by default, pulse (and slow), spot, spot shadow.
LIGHT_FLAGS = {0x2: 0x2, 0x8: 0x8, 0x20: 0x20, 0x40: 0x8, 0x80: 0x80, 0x100: 0x80, 0x200: 0x4000, 0x400: 0x400}
#: FNV NPC -> the vanilla FO4 NPC whose face and body its clone takes (the dialogue spike's stand-ins).
STAND_INS = {fnv: fo4 for _, fnv, fo4, *_ in SPEAKERS if fnv}
#: Face variants per actor (fitted sculpt regions and tints, FNV's head parts matched); the last plays the FNV ref.
FACE_VARIANTS, FACE_SPACING = ('STH',), 50.0
#: The bit every vanilla FO4 omni light carries.
LIGHT_BASE = 0x1


def _model(rec: dict) -> str:
    """An FNV base record's world model ('' for none)."""
    return rec.get('Model.MODL') or rec.get('Male.WorldModel.MODL') or ''


def _bounds(rec: dict) -> tuple:
    """An FNV record's OBND."""
    return tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))


def _floats(rec: dict, prefix: str, keys: tuple) -> tuple:
    """`rec[prefix + key]` for each key, as floats."""
    return tuple(float(rec[prefix + k]) for k in keys)


def _place(rec: dict, prefix: str = '') -> tuple:
    """(position, rotation) of a reference, or of its teleport with prefix 'XTEL.'."""
    return _floats(rec, prefix, ('PosX', 'PosY', 'PosZ')), _floats(rec, prefix, ('RotX', 'RotY', 'RotZ'))


def _color(cell: dict, key: str) -> bytes:
    """An FNV XCLL colour as FO4 byte colours (RGB, 0)."""
    return bytes(int(cell[f'XCLL.{key}{c}']) for c in 'RGB') + b'\0'


def lighting(cell: dict, template: bytes) -> bytes:
    """FO4 XCLL: FNV's colours, fog, directional light and fog power over `template`, inheriting nothing.

    FNV's ambient colour also fills FO4's six directional ambient colours and
    its fog colour the far fog colour; the FO4-only fields keep `template`'s.
    """
    out = bytearray(template)
    out[0:12] = _color(cell, 'Ambient') + _color(cell, 'Directional') + _color(cell, 'Fog')
    out[12:40] = struct.pack('<2f2i3f', *_floats(cell, 'XCLL.', ('FogNear', 'FogFar')),
                             int(cell['XCLL.DirectionalRotXY']), int(cell['XCLL.DirectionalRotZ']),
                             *_floats(cell, 'XCLL.', ('DirectionalFade', 'FogClipDist', 'FogPower')))
    out[40:64] = _color(cell, 'Ambient') * 6
    out[72:76] = _color(cell, 'Fog')
    out[88:92] = bytes(4)
    return bytes(out)


def light_flags(fnv: int) -> int:
    """FNV LIGH flags as FO4 ones (Negative and Dynamic have none)."""
    return LIGHT_BASE | sum({v for k, v in LIGHT_FLAGS.items() if fnv & k})


class CellBuilder:
    """FO4 base records for one FNV cell's references, each base and mesh converted once."""

    def __init__(self, export_dir: Path, data_dir: Path, bases: dict):
        """A builder writing assets into `data_dir`; `bases` is {FNV FormID: (type, record)}."""
        self.export_dir, self.data_dir, self.bases = export_dir, data_dir, bases
        self.writer = FO4PluginWriter(masters=MASTERS, is_esm=False, description='FNV cell spike')
        self.next_id = len(MASTERS) << 24 | FIRST_ID
        self.made, self.meshes, self.items, self.activators, self.scripts = {}, {}, None, None, None
        self.actor_ids, self.npc_ids, self.say = {}, {}, None
        self.fo4 = FALLOUT4_ESM.read_bytes()
        self.keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                         for r, _ in walk(self.fo4, b'KYWD')}
        self.counts = collections.Counter()

    def new_id(self) -> int:
        """The next plugin FormID."""
        self.next_id += 1
        return self.next_id - 1

    def mesh(self, model: str) -> tuple:
        """(FO4 model path, bounds) of an FNV model, converted into the data folder once."""
        if model not in self.meshes:
            self.meshes[model] = write_assets(self.export_dir, model, self.data_dir)
        return self.meshes[model]

    def base(self, fnv_fid: int) -> 'int | None':
        """The FO4 base for an FNV base FormID, made on first use; None when it is not converted."""
        if fnv_fid < ENGINE_IDS:
            return self.items.shared.get(fnv_fid)
        if self.items.records.get(fnv_fid, ('',))[0] in ITEM_BASES:
            return self.items.item(fnv_fid)
        sig, rec = self.bases.get(fnv_fid, (None, None))
        if fnv_fid not in self.made:
            self.made[fnv_fid] = self._make(sig, rec) if sig in ('LIGH', 'ACTI') or (sig and _model(rec)) else None
        return self.made[fnv_fid]

    def _make(self, sig: str, rec: dict) -> int:
        """Write the FO4 record for FNV base `rec` of type `sig`; its FormID."""
        fid, edid = self.new_id(), f'FNV_{rec["EditorID"]}'
        model, bounds = self.mesh(_model(rec)) if _model(rec) else ('', _bounds(rec))
        if sig == 'LIGH':
            light = (int(rec['DATA.Radius']), tuple(int(rec[f'DATA.Color.{c}']) for c in 'RGB'),
                     light_flags(int(rec['DATA.Flags'])))
            record = R.pack_ligh(fid, edid, _bounds(rec), model, light, float(rec.get('FNAM.Fade', 1.0)))
        elif sig == 'FURN':
            marks = markers(str(self.export_dir / 'meshes' / _model(rec).replace('/', '\\').lower()))
            record = furniture(fid, rec, model, bounds, marks, self.keywords)
        elif sig == 'ACTI':
            record = self.activators.record(fid, rec, model, bounds)
        elif sig == 'DOOR':
            vmad = self.scripts.vmad(int(rec['SCRI'], 16)) if 'SCRI' in rec else b''
            record = R.pack_door(fid, edid, rec.get('FULL', ''), model, bounds, int(rec.get('FNAM.Flags', 0)), vmad)
        else:
            sig, record = 'STAT', R.pack_stat(fid, edid, model, bounds)
        self.writer.add_record(sig, record)
        self.counts[sig] += 1
        return fid


def _find_cell(export_dir: Path, edid: str) -> dict:
    """The FNV interior CELL record with EditorID `edid`."""
    for rec in parse_export_file(str(export_dir / 'CELL.txt')):
        if rec.get('EditorID') == edid:
            return rec
    raise SystemExit(f'no CELL {edid}')


def _bases(export_dir: Path, used: set) -> dict:
    """{FNV FormID: (type, record)} of the used bases this spike converts."""
    out = {}
    for sig in AS_STATIC + ('LIGH', 'DOOR', 'FURN', 'ACTI'):
        for rec in parse_export_file(str(export_dir / f'{sig}.txt')):
            fid = int(rec['FormID'], 16)
            if fid in used:
                out[fid] = (sig, rec)
    return out


def _doors(builder: CellBuilder, door_refs: list, links: dict, ids: dict) -> tuple:
    """Stand-in doors in QASmoke for the cell's teleport doors: (their REFRs, {door ref: its teleport}).

    Each stand-in leads to where the FNV door's partner led into the cell
    (the cell door's own position when the partner is not in the export).
    """
    qa_refs, teleports = b'', {}
    for i, ref in enumerate(door_refs):
        pos = (DOOR_START[0] + i * DOOR_SPACING, DOOR_START[1], DOOR_START[2])
        stand_in, partner = builder.new_id(), links.get(ref['XTEL.Door'], ref)
        inside = _place(partner, 'XTEL.') if partner is not ref else _place(ref)
        qa_refs += R.pack_refr(stand_in, builder.base(int(ref['NAME'], 16)), pos, (0.0, 0.0, 0.0),
                               teleport=(ids[ref['FormID']], *inside))
        teleports[ref['FormID']] = (stand_in, tuple(p + a for p, a in zip(pos, ARRIVAL)), ARRIVAL_ROT)
    return qa_refs, teleports


def _placed(builder: CellBuilder, refs: list, ids: dict, teleports: dict) -> tuple:
    """(persistent, temporary) REFRs of the cell's converted references."""
    persistent, temporary = b'', b''
    for ref in refs:
        base = builder.base(int(ref['NAME'], 16))
        if base is None:
            builder.counts['skipped ' + builder.bases.get(int(ref['NAME'], 16), ('other',))[0]] += 1
            continue
        keep = bool(int(ref['RecordFlags']) & 0x400) or ref['FormID'] in teleports
        radius = float(ref['XRDS.Radius']) if 'XRDS.Radius' in ref and builder.bases.get(
            int(ref['NAME'], 16), ('',))[0] == 'LIGH' else None
        record = R.pack_refr(ids[ref['FormID']], base, *_place(ref), float(ref.get('XSCL.Scale', 1.0)), radius,
                             teleports.get(ref['FormID']), keep, bytes.fromhex(ref.get('XPRM.Raw', '')))
        persistent, temporary = (persistent + record, temporary) if keep else (persistent, temporary + record)
    builder.counts['placed'] = len(refs) - sum(v for k, v in builder.counts.items() if k.startswith('skipped'))
    return persistent, temporary


def _vanilla(fo4: bytes, fids: set) -> dict:
    """{FormID: Record} of the Fallout4.esm records `fids` (CELL, IMGS, NPC_)."""
    return {rec.form_id: rec for rec, _ in walk(fo4, b'CELL', b'IMGS', b'NPC_')
            if rec.form_id in fids}


def _sculpt_morphs(builder: CellBuilder, export_dir: Path, edid: str) -> bytes:
    """FO4 sculpt regions fitted to FNV NPC `edid`'s face; b'' before calibration."""
    fitted = sculpt_fit(export_dir, edid)
    if fitted is None:
        builder.counts['sculpt fit skipped (no calibration)'] += 1
        return b''
    builder.counts[f'sculpt fit captures % ({edid})'] = round(100 * fitted[1])
    return fitted[0]


def _tint_edit(builder: CellBuilder, export_dir: Path, edid: str, tone_options: frozenset):
    """A clone edit giving FNV NPC `edid`'s fitted tint layers and skin tone; None before calibration."""
    fitted = tint_fit(export_dir, edid)
    cached = tint.load_basis()
    if fitted is None:
        builder.counts['tint fit skipped (no calibration)'] += 1
        return None
    values, tone, captured = fitted
    builder.counts[f'tint fit captures % ({edid})'] = round(100 * captured)

    def edit(subs: bytes) -> bytes:
        """The clone with the fitted tint layers and its skin tone scaled."""
        rest, kept = tint.without_tints(subs, tone_options)
        rest = tint.with_tints(rest, tint.pack_layers(cached[1], values, kept, cached[3]))
        return tint.with_tone(rest, tone, tone_options)
    return edit


def _head_edit(builder: CellBuilder, export_dir: Path, edid: str, assets: hair.Fo4Assets):
    """A clone edit giving FNV NPC `edid`'s matched hair, facial hair, eyes and hair colour; None uncalibrated."""
    if sculpt_basis() is None:
        builder.counts['head parts skipped (no calibration)'] += 1
        return None
    choice = choose(export_dir, edid, assets, sculpt_basis()[2])
    picked = [assets.edid(p) for p in (choice.hair, choice.facial_hair, choice.eyes) if p is not None]
    builder.counts[f'head parts ({edid}): ' + ', '.join(picked)] += 1
    builder.counts[f'hair colour ({edid}): ' + assets.colours[choice.colour][b'EDID'][0].rstrip(b'\0').decode()] += 1
    for name in choice.unmapped:
        builder.counts[f'head part without an FO4 kind ({edid}): {name}'] += 1
    return head_parts_edit(choice, assets)


def _composed(*edits):
    """One clone edit applying `edits` (None skipped) in order."""
    present = [e for e in edits if e is not None]

    def edit(subs: bytes) -> bytes:
        """The subrecords after every edit."""
        for step in present:
            subs = step(subs)
        return subs
    return edit if present else None


def _actors(builder: CellBuilder, export_dir: Path, cell_fid: str, vanilla: dict) -> bytes:
    """Persistent ACHRs for the cell's FNV actors that have a stand-in, each base a clone of it.

    One clone per FACE_VARIANTS entry, side by side along the actor's right:
    the stand-in's body and inventory with FNV's face fitted (sculpt regions,
    tints), under the FNV NPC's EditorID and name plus the variant; STH also
    takes FNV's matched hair, facial hair, eyes and hair colour.
    """
    npcs = {int(r['FormID'], 16): r for r in parse_export_file(str(export_dir / 'NPC_.txt'))}
    assets = hair.Fo4Assets(builder.fo4, Archives(FALLOUT4_DIR / 'Data'))
    out = b''
    for ref in parse_export_file(str(export_dir / 'ACHR.txt')):
        fnv = int(ref['NAME'], 16)
        if ref.get('ParentCELL') != cell_fid or fnv not in STAND_INS:
            continue
        stand_in, npc = vanilla[STAND_INS[fnv]], npcs[fnv]
        pos, rot = _place(ref)
        morphs = _sculpt_morphs(builder, export_dir, npc['EditorID'])
        tinted = _tint_edit(builder, export_dir, npc['EditorID'], skin_tone_layers())
        edits = {'ST': tinted, 'STH': _composed(tinted, _head_edit(builder, export_dir, npc['EditorID'], assets))}
        for i, variant in enumerate(FACE_VARIANTS):
            base = builder.new_id()
            builder.writer.add_record('NPC_', R.clone_npc(
                base, stand_in.body, stand_in.flags, f'FNV_{npc["EditorID"]}_{variant}',
                f'{npc.get("FULL", "")} ({variant})', FACE_SHAPE | STAND_IN_TIES, morphs, edits[variant]))
            spot = (pos[0] + i * FACE_SPACING * math.cos(rot[2]), pos[1] - i * FACE_SPACING * math.sin(rot[2]), pos[2])
            achr = builder.new_id()
            builder.actor_ids[ref['FormID']] = builder.scripts.named[ref.get('EditorID', '')] = achr
            vmad = builder.scripts.vmad(int(npc['SCRI'], 16)) if 'SCRI' in npc else b''
            out += R.pack_achr(achr, base, spot, rot, vmad)
            builder.counts['NPC_'] += 1
            builder.npc_ids[fnv] = base
    return out


def _imagespace(builder: CellBuilder, export_dir: Path, cell: dict, base_body: bytes):
    """The FO4 imagespace made from the FNV cell's (FNV's grading in a LUT); None if the cell names none."""
    if 'XCIM.Imagespace' not in cell:
        builder.counts['cell without an FNV imagespace'] += 1
        return None
    fnv = next(r for r in parse_export_file(str(export_dir / 'IMGS.txt')) if r['FormID'] == cell['XCIM.Imagespace'])
    lut = write_lut(bytes.fromhex(fnv['DNAM']), fnv['EditorID'], builder.data_dir, base_hdr(base_body))
    fid = builder.new_id()
    builder.writer.add_record('IMGS', pack_imgs(fid, f'FNV_{fnv["EditorID"]}', base_body, lut))
    builder.counts[f'imagespace: {fnv["EditorID"]}'] += 1
    return fid


def _navmesh(builder: CellBuilder, export_dir: Path, fnv_cell: str, cell_fid: int, ids: dict) -> bytes:
    """The cell's FNV navmeshes as FO4 NAVM records, registered in the plugin's NAVI override."""
    recs = [r for r in parse_export_file(str(export_dir / 'NAVM.txt')) if r.get('DATA.Cell') == fnv_cell]
    records, infos = navmeshes(recs, cell_fid, ids, builder.new_id)
    if infos:
        builder.writer.add_record('NAVI', navi(builder.fo4, infos))
        builder.counts['NAVM'] += len(recs)
    return records


def _quests(builder: CellBuilder, export_dir: Path, quests: dict, ref_ids: dict) -> None:
    """Write the FNV quests `quests` ({EditorID: FormID}) with their scripted lines; `ref_ids` maps FNV references.

    A line's conditions see the cell's references, actors' bases, these quests and the player.
    """
    say = builder.say = SayTopics(builder, export_dir)
    recs = [r for r in parse_export_file(str(export_dir / 'QUST.txt')) if r.get('EditorID') in quests]
    form_map = {**{int(k, 16): v for k, v in ref_ids.items()}, **builder.npc_ids, PLAYER: PLAYER,
                **{int(r['FormID'], 16): quests[r['EditorID']] for r in recs}}
    for rec in recs:
        fid = quests[rec['EditorID']]
        topics = {dial: builder.new_id() for dial in say.topics(rec)}
        builder.scripts.named.update({say.dials[d]['EditorID']: t for d, t in topics.items()})
        branch, blobs = say.build(rec, fid, topics, form_map) if topics else (None, [])
        record = quest_record(fid, rec, builder.scripts, ref_ids)
        builder.writer.add_record('QUST', pack_quest(record, fid, [branch] if branch else [], blobs, []))
        builder.counts['QUST'] += 1


def _voice(builder: CellBuilder, export_dir: Path, data_dir: Path, plugin: str) -> None:
    """The scripted lines' FNV recordings as .fuz under every cell actor's stand-in voice type."""
    folders = export_dir / 'sound' / 'voice' / 'falloutnv.esm'
    voices = [(folders / VOICES[label][0], VOICES[label][1]) for label, fnv, *_ in SPEAKERS
              if fnv in builder.npc_ids and label in VOICES]
    todo = voice.jobs(builder.say.voiced, voices, data_dir, plugin)
    builder.counts['voice files'] = voice.convert(todo, FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator')


def _object_makers(builder: CellBuilder, export_dir: Path, scripts_dir: 'Path | None') -> None:
    """Give `builder` its item and activator makers."""
    records = index(export_dir, ITEM_TYPES)
    builder.items = Items(builder, records, shared_engine_ids(builder.fo4, {**builder.bases, **records},
                                                              SHARED_TYPES))
    builder.scripts = ObjectScripts(builder, export_dir, scripts_dir, HELPER_INDEX)
    builder.activators = Activators(builder, export_dir)


def build(export_dir: Path, out: Path, data_dir: Path, cell_edid: str,
          scripts_dir: 'Path | None' = None) -> collections.Counter:
    """Write the plugin and assets for the FNV interior cell `cell_edid`; counts of what was made.

    `scripts_dir` holds the converted scripts; the activators' are attached and compiled into <data_dir>/Scripts.
    """
    cell = _find_cell(export_dir, cell_edid)
    all_refs = parse_export_file(str(export_dir / 'REFR.txt'))
    refs = [r for r in all_refs if r.get('ParentCELL') == cell['FormID']]
    links = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    builder = CellBuilder(export_dir, data_dir, _bases(export_dir, {int(r['NAME'], 16) for r in refs}))
    _object_makers(builder, export_dir, scripts_dir)
    cell_fid = builder.new_id()
    ids = {r['FormID']: builder.new_id() for r in refs}
    quests = {edid: builder.new_id() for edid in CELL_QUESTS}
    builder.scripts.named.update({**{r['EditorID']: ids[r['FormID']] for r in refs if r.get('EditorID')}, **quests})
    vanilla = _vanilla(builder.fo4, {CELL_FO4, BASE_IMAGESPACE} | set(STAND_INS.values()))
    actors = _actors(builder, export_dir, cell['FormID'], vanilla)
    qa_refs, teleports = _doors(builder, [r for r in refs if 'XTEL.Door' in r], links, ids)
    persistent, temporary = _placed(builder, refs, ids, teleports)
    persistent += actors
    _quests(builder, export_dir, quests, {**ids, **builder.actor_ids})
    temporary += _navmesh(builder, export_dir, cell['FormID'], cell_fid, ids)
    qa_record = pack_fo4_record('CELL', CELL_FO4, vanilla[CELL_FO4].flags, vanilla[CELL_FO4].body)
    template = sub_map(vanilla[CELL_FO4].body)
    imagespace = _imagespace(builder, export_dir, cell, vanilla[BASE_IMAGESPACE].body)
    record = R.pack_cell(cell_fid, f'FNV_{cell_edid}', cell.get('FULL', cell_edid), int(cell['DATA.Flags']) & 0xFF,
                         lighting(cell, template[b'XCLL']), struct.unpack('<I', template[b'LTMP'])[0],
                         imagespace or struct.unpack('<I', template[b'XCIM'])[0])
    builder.writer.add_raw_group('CELL', R.pack_interior_cells([(record, cell_fid, persistent, temporary),
                                                                (qa_record, CELL_FO4, qa_refs, b'')]))
    failed = finish([data_dir / 'Meshes' / model for model, _ in builder.meshes.values()])
    builder.counts['meshes without collision (Elric failed)'] = len(failed)
    _voice(builder, export_dir, data_dir, out.name)
    if builder.scripts.used:
        print(compile_into(scripts_dir, data_dir, builder.scripts.used))
    builder.writer.next_object_id = builder.next_id & 0xFFFFFF
    out.parent.mkdir(parents=True, exist_ok=True)
    builder.writer.write(str(out))
    return builder.counts


def main():
    """Build the plugin and assets, and print the counts."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--export', required=True, help='FalloutNV.esm export folder')
    ap.add_argument('--out', required=True, help='Plugin to write')
    ap.add_argument('--data', required=True, help='Data folder for meshes, materials and textures')
    ap.add_argument('--scripts', type=Path, help='Converted FNV scripts (script_convert.pipeline --target fallout4)')
    ap.add_argument('cell', help='FNV interior cell editor ID')
    args = ap.parse_args()
    for key, count in sorted(build(Path(args.export), Path(args.out), Path(args.data), args.cell,
                                   args.scripts).items()):
        print(f'{key}: {count}')


if __name__ == '__main__':
    main()
