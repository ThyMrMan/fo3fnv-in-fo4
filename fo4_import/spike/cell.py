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
from fo4_import.base.ba2_pack import pack_textures
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest
from fo4_import.face import hair, tint
from fo4_import.face.sculpt import FACE_SHAPE
from fo4_import.face.sculpt import load_basis as sculpt_basis
from fo4_import.spike.face_fit import sculpt_fit, tint_fit
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.head_parts import choose, head_parts_edit
from fo4_import.spike.consumables import Consumables
from fo4_import.spike.creatures import Creatures
from fo4_import.spike.equipment import Equipment
from fo4_import.spike.scol import BASE_SITE, PART_SITE, Parts, compose
from fo4_import.spike.imagespace import BASE_IMAGESPACE, LUT_FOLDER, base_hdr, pack_imgs, write_lut
from fo4_import.spike.activators import Activators
from fo4_import.spike import character, replacements, skeleton
from fo4_import.spike.attach import ObjectScripts
from fo4_import.spike.conversation import GREETING, Conversations, Hub, hub
from fo4_import.spike.furniture import furniture, markers
from fo4_import.spike.navmesh import navi, navmeshes
from fo4_import.spike.exterior import Exterior
from fo4_import.spike.imods import ImageSpaces
from fo4_import.spike.packages import Packages
from fo4_import.spike.poses import Poses
from fo4_import.spike.sounds import Sounds
from fo4_import.spike.swaps import Swaps
from fo4_import.spike.items import ENGINE_IDS, ITEM_TYPES, Items, index, shared_engine_ids
from fo4_import.nif import weapon
from fo4_import.nif.elric import finish
from fo4_import.spike import records as R
from fo4_import.spike import voice
from fo4_import.spike.dialogue import CELL_FO4, SPEAKERS, VOICES
from fo4_import.spike.say_topics import SayTopics, actor_values, conditions_of
from fo4_import.spike.script import compile_into
from fo4_import.spike.quest import objective_globals, quest_record
from fo4_import.spike.statics import tree_assets, write_assets
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from script_convert.context_setup import load_records
from tes5_import.base.tes5_reader import first_sub, sub_map, walk
from tes5_import.base.text_reader import parse_export_file
from tes5_import.dialogue.unlocks import build_unlock_plan

MASTERS = ['Fallout4.esm', FALLOUT4_HELPER_PLUGIN, 'XDI.esm']
#: Master index of the helper plugin (TES4Helpers.esl).
HELPER_INDEX = 1
#: XDI's menu keyword (conversation menus show more than four options).
XDI_KEYWORD = MASTERS.index('XDI.esm') << 24 | R.XDI_KEYWORD
#: Stand-in subrecords a clone leaves out: its factions (vanilla doctor dialogue, caravans) and crime faction.
STAND_IN_TIES = frozenset({b'SNAM', b'CRIF'})
#: The player's reference, the same FormID in both games.
PLAYER = 0x14
#: FNV quests the cell's scripts run, converted with it.
CELL_QUESTS = ('VCG01', 'VCG01Test', 'VGenericTimer', 'VFreeformGoodsprings', 'VDoctors')
#: Quests the spike starts by hand (setstage), not with the game: VCG01's stage 0 takes a loaded save's Pip-Boy.
HAND_STARTED = frozenset({'VCG01'})
#: derive_formid site of the statics made from FNV TREE records (key: the TREE's FormID).
TREE_SITE = 'FNV TREE'
#: FormID site of a load door's static copy of an FNV DOOR (CellBuilder.load_door).
LOAD_DOOR_SITE = 'FNV DOOR load'
FIRST_ID = 0x800
#: FNV base types placed as FO4 statics (their mesh only) until each gets its own conversion.
AS_STATIC = ('STAT', 'MSTT', 'SCOL', 'ALCH', 'WEAP', 'ARMO', 'BOOK', 'KEYM', 'NOTE', 'AMMO', 'TERM', 'IDLM')
#: FNV base types converted as themselves (spike.items), and the types whose engine objects FO4 may share.
ITEM_BASES, SHARED_TYPES = ('MISC', 'CONT'), ('STAT', 'MISC')
#: Item types placed as FO4 items; each still takes its old static's numbered FormID (its static when no item).
PICKUPS = ('ALCH', 'AMMO', 'WEAP', 'ARMO')
#: Stand-in doors in QASmoke: the first one's position and the spacing along X.
DOOR_START, DOOR_SPACING = (-1700.0, -1184.0, 0.0), 300.0
#: Where a stand-in door puts the player: offset from the door, facing +X, away from it.
ARRIVAL, ARRIVAL_ROT = (100.0, 64.0, 0.0), (0.0, 0.0, math.pi / 2)
#: QASmoke's test chest: QAConsumableChest (its model), a spot past the first door's arrival, rounds per gun, FormID site.
TEST_CHEST, TEST_CHEST_POS, TEST_ROUNDS, TEST_SITE = 0x1E7DC8, (-1450.0, -1120.0, 0.0), 100, 'FNV test chest'
#: FNV creatures in QASmoke, as (EditorID, position, rotation): Cheyenne (saloon not built), VCG02's well geckos.
QA_CREATURES = (('GSCheyenne', (-1550.0, -1330.0, 0.0), (0.0, 0.0, 0.0)),
                ('VCG02CrGecko', (-1150.0, -1450.0, 0.0), (0.0, 0.0, 3.14)),
                ('VCG02CrGecko', (-1050.0, -1500.0, 0.0), (0.0, 0.0, 3.14)))
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

    def __init__(self, export_dir: Path, data_dir: Path, bases: dict, table: 'dict | None' = None,
                 plugin_dirs: tuple = ()):
        """A builder writing assets into `data_dir`; `bases` is {FNV FormID: (type, record)}; `table` the
        replacement table (spike.replacements; its other plugins become masters, found in `plugin_dirs`)."""
        self.export_dir, self.data_dir, self.bases = export_dir, data_dir, bases
        self.table, self.plugin_dirs = table if table is not None else replacements.load(), plugin_dirs
        self.masters = MASTERS + replacements.extra_masters(self.table)
        self.writer = FO4PluginWriter(masters=self.masters, is_esm=False, description='FNV cell spike')
        self.next_id = len(self.masters) << 24 | FIRST_ID
        self.made, self.meshes, self.items, self.activators, self.scripts = {}, {}, None, None, None
        self.actor_ids, self.npc_ids, self.say, self.packages, self.objectives = {}, {}, None, None, {}
        self.swaps, self.imods, self.poses, self.parts, self.weapons = None, None, None, None, set()
        self.equipment, self.load_doors = None, {}
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

    def weapon_mesh(self, model: str, pose: dict) -> tuple:
        """mesh() of an FNV weapon model in its held `pose`, dressed as a weapon after Elric (nif.weapon)."""
        if model not in self.meshes:
            self.meshes[model] = write_assets(self.export_dir, model, self.data_dir, pose, animated=False)
        self.weapons.add(self.meshes[model][0])
        return self.meshes[model]

    def base(self, fnv_fid: int, new_id=None) -> 'int | None':
        """The FO4 base for an FNV base FormID, made on first use (id from `new_id`); None: not converted."""
        if fnv_fid < ENGINE_IDS:
            return self.items.shared.get(fnv_fid)
        if self.items.records.get(fnv_fid, ('',))[0] in ITEM_BASES:
            return self.items.item(fnv_fid)
        sig, rec = self.bases.get(fnv_fid, (None, None))
        if fnv_fid in self.made:
            return self.made[fnv_fid]
        if sig in PICKUPS:
            self.made[fnv_fid] = self._pickup(fnv_fid, sig, rec)
        elif sig == 'TREE':
            self.made[fnv_fid] = self._tree(fnv_fid, rec)
        elif sig == 'SOUN':
            self.made[fnv_fid] = self.sounds.marker(fnv_fid)
        else:
            made = sig in ('LIGH', 'ACTI') or (sig and _model(rec))
            self.made[fnv_fid] = self._make(sig, rec, new_id or self.new_id) if made else None
        return self.made[fnv_fid]

    def _tree(self, fnv_fid: int, rec: dict) -> int:
        """The FO4 static for FNV TREE `rec`, its mesh generated from its SpeedTree; FormID hashed from FNV's."""
        fid = self.writer.derive_formid(TREE_SITE, f'{fnv_fid:08X}')
        model, bounds = self.meshes[_model(rec)] = tree_assets(self.export_dir, rec, self.data_dir)
        self.writer.add_record('STAT', R.pack_stat(fid, f'FNV_{rec["EditorID"]}', model, bounds or _bounds(rec)))
        self.counts['TREE'] += 1
        return fid

    def _pickup(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """The FO4 item for placed FNV item `rec`; without one, its static on the numbered FormID it reserves."""
        reserved = self.new_id() if _model(rec) else None
        item = self.items.item(fnv_fid)
        if item is not None or reserved is None:
            return item
        return self._make(sig, rec, lambda: reserved)

    def _make(self, sig: str, rec: dict, new_id) -> int:
        """Write the FO4 record for FNV base `rec` of type `sig` on FormID `new_id()`; its FormID."""
        fid, edid = new_id(), f'FNV_{rec["EditorID"]}'
        model, bounds = self.mesh(_model(rec)) if _model(rec) else ('', None)
        bounds = bounds or _bounds(rec)
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
            record = self._door(fid, edid, rec, (model, bounds))
        else:
            sig, record = _static(sig, fid, edid, model, bounds)
        self.writer.add_record(sig, record)
        self.counts[sig] += 1
        return fid

    def _door(self, fid: int, edid: str, rec: dict, mesh: tuple) -> bytes:
        """FNV DOOR `rec` as FO4's on `fid` with `mesh` (model, bounds)."""
        vmad = self.scripts.vmad(int(rec['SCRI'], 16)) if 'SCRI' in rec else b''
        return R.pack_door(fid, edid, rec.get('FULL', ''), *mesh, int(rec.get('FNAM.Flags', 0)), vmad,
                           (self.sounds.field(rec, 'SNAM.Open'), self.sounds.field(rec, 'ANAM.Close')))

    def load_door(self, fnv_fid: int) -> 'int | None':
        """The FO4 base for FNV door `fnv_fid` placed as a load door: a copy on its mesh made static (FNV never
        opens a load door), FormID hashed from FNV's; the plain base when the mesh has no animation.

        See: docs/fork/fo4_spikes.md#spike-4-load-doors
        """
        if fnv_fid in self.load_doors:
            return self.load_doors[fnv_fid]
        plain = self.base(fnv_fid)
        sig, rec = self.bases.get(fnv_fid, (None, None))
        made = write_assets(self.export_dir, _model(rec), self.data_dir, load=True) \
            if sig == 'DOOR' and plain is not None else None
        self.load_doors[fnv_fid] = plain
        if made is not None:
            self.meshes[f'{_model(rec)}#load'] = made
            fid = self.load_doors[fnv_fid] = self.writer.derive_formid(LOAD_DOOR_SITE, f'{fnv_fid:08X}')
            self.writer.add_record('DOOR', self._door(fid, f'FNV_{rec["EditorID"]}Load', rec, made))
            self.counts['load doors made static'] += 1
        return self.load_doors[fnv_fid]


def _static(sig: str, fid: int, edid: str, model: str, bounds: tuple) -> tuple:
    """(FO4 type, record): an FNV MSTT as a movable static, anything else as a static."""
    if sig == 'MSTT':
        return 'MSTT', R.pack_mstt(fid, edid, model, bounds)
    return 'STAT', R.pack_stat(fid, edid, model, bounds)


def _find_cell(export_dir: Path, edid: str) -> dict:
    """The FNV interior CELL record with EditorID `edid`."""
    for rec in parse_export_file(str(export_dir / 'CELL.txt')):
        if rec.get('EditorID') == edid:
            return rec
    raise SystemExit(f'no CELL {edid}')


def _bases(export_dir: Path, used: set) -> dict:
    """{FNV FormID: (type, record)} of the used bases this spike converts."""
    out = {}
    for sig in AS_STATIC + ('LIGH', 'DOOR', 'FURN', 'ACTI', 'TREE', 'SOUN'):
        for rec in parse_export_file(str(export_dir / f'{sig}.txt')):
            fid = int(rec['FormID'], 16)
            if fid in used:
                out[fid] = (sig, rec)
    return out


def _linked(door_refs: list, ids: dict) -> dict:
    """{door ref: its teleport} of doors whose partner is in `ids`."""
    return {r['FormID']: (ids[r['XTEL.Door']], *_place(r, 'XTEL.')) for r in door_refs if r['XTEL.Door'] in ids}


def _doors(builder: CellBuilder, door_refs: list, links: dict, ids: dict) -> tuple:
    """Stand-in doors in QASmoke for the cell's teleport doors: (their REFRs, {door ref: its teleport}).

    A door whose partner is converted leads to it; for another, a stand-in
    leads to where the FNV door's partner led into the cell (the cell door's
    own position when the partner is not in the export).
    """
    qa_refs, teleports = b'', _linked(door_refs, ids)
    for i, ref in enumerate(r for r in door_refs if r['FormID'] not in teleports):
        pos = (DOOR_START[0] + i * DOOR_SPACING, DOOR_START[1], DOOR_START[2])
        stand_in, partner = builder.new_id(), links.get(ref['XTEL.Door'], ref)
        inside = _place(partner, 'XTEL.') if partner is not ref else _place(ref)
        qa_refs += R.pack_refr(stand_in, builder.load_door(int(ref['NAME'], 16)), pos, (0.0, 0.0, 0.0),
                               teleport=(ids[ref['FormID']], *inside))
        teleports[ref['FormID']] = (stand_in, tuple(p + a for p, a in zip(pos, ARRIVAL)), ARRIVAL_ROT)
    return qa_refs, teleports


def _test_chest(builder: CellBuilder, template) -> bytes:
    """QASmoke's test chest (vanilla QA chests' footlocker) with every converted weapon and armor piece; its REFR."""
    subs = sub_map(template.body)
    fid = builder.writer.derive_formid(TEST_SITE, 'CONT')
    builder.writer.add_record('CONT', R.pack_cont(
        fid, 'FNV_TestChest', 'FNV test chest', subs[b'MODL'].rstrip(b'\0').decode(),
        struct.unpack('<6h', subs[b'OBND']), builder.equipment.test_items(TEST_ROUNDS), 0, 0.0))
    return R.pack_refr(builder.writer.derive_formid(TEST_SITE, 'REFR'), fid, TEST_CHEST_POS, (0.0, 0.0, 0.0))


def _qa_creatures(builder: CellBuilder, export_dir: Path, data_dir: Path) -> bytes:
    """ACHRs of QA_CREATURES in QASmoke (their FNV cells not built yet)."""
    creatures = Creatures(builder, export_dir, data_dir)
    return b''.join(creatures.placed(edid, pos, rot) for edid, pos, rot in QA_CREATURES)


def _placed(builder: CellBuilder, refs: list, ids: dict, teleports: dict) -> tuple:
    """(persistent, temporary) REFRs of the cell's converted references."""
    persistent, temporary = b'', b''
    for ref in refs:
        base = (builder.load_door if ref['FormID'] in teleports else builder.base)(int(ref['NAME'], 16))
        if int(ref['NAME'], 16) in builder.parts.parts:
            temporary += _part_refs(builder, ref)
            continue
        if base is None:
            builder.counts['skipped ' + builder.bases.get(int(ref['NAME'], 16), ('other',))[0]] += 1
            continue
        keep = bool(int(ref['RecordFlags']) & 0x400) or ref['FormID'] in teleports
        radius = float(ref['XRDS.Radius']) if 'XRDS.Radius' in ref and builder.bases.get(
            int(ref['NAME'], 16), ('',))[0] == 'LIGH' else None
        record = R.pack_refr(ids[ref['FormID']], base, *_place(ref), float(ref.get('XSCL.Scale', 1.0)), radius,
                             teleports.get(ref['FormID']), keep, bytes.fromhex(ref.get('XPRM.Raw', '')),
                             bool(int(ref['RecordFlags']) & R.INITIALLY_DISABLED), ids.get(ref.get('XLKR.LinkedRef'), 0))
        persistent, temporary = (persistent + record, temporary) if keep else (persistent, temporary + record)
        builder.counts['placed'] += 1
    return persistent, temporary


def _part_refs(builder: CellBuilder, ref: dict) -> bytes:
    """The REFRs of FNV SCOL reference `ref`'s parts, on hashed FormIDs (scol.PART_SITE)."""
    position, angle = _place(ref)
    scale, out = float(ref.get('XSCL.Scale', 1.0)), b''
    disabled = bool(int(ref['RecordFlags']) & R.INITIALLY_DISABLED)
    derive = builder.writer.derive_formid
    for index, (part, placement) in enumerate(builder.parts.parts[int(ref['NAME'], 16)]):
        base = builder.base(part, lambda: derive(BASE_SITE, part))
        if base is None:
            builder.counts['SCOL part skipped'] += 1
            continue
        at, turn, size = compose(position, angle, scale, placement)
        fid = derive(PART_SITE, (ref['FormID'], index))
        out += R.pack_refr(fid, base, at, turn, size, persistent=False, disabled=disabled)
        builder.counts['SCOL parts placed'] += 1
    builder.counts['SCOL references split'] += 1
    return out


def _vanilla(fo4: bytes, fids: set) -> dict:
    """{FormID: Record} of the Fallout4.esm records `fids` (CELL, IMGS, NPC_, CONT)."""
    return {rec.form_id: rec for rec, _ in walk(fo4, b'CELL', b'IMGS', b'NPC_', b'CONT')
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


def _actors(builder: CellBuilder, export_dir: Path, cell_fid: str, vanilla: dict, form_map: dict) -> bytes:
    """Persistent ACHRs for the cell's FNV actors that have a stand-in, each base a clone of it.

    One clone per FACE_VARIANTS entry, side by side along the actor's right:
    the stand-in's body and inventory with FNV's face fitted (sculpt regions,
    tints) and the FNV NPC's packages, under its EditorID and name plus the
    variant; STH also takes FNV's matched hair, facial hair, eyes and hair
    colour. `form_map` maps the FNV forms packages name.
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
        packages = R.packages_edit(builder.packages.for_npc(npc, form_map))
        edits = {'ST': _composed(tinted, packages),
                 'STH': _composed(tinted, _head_edit(builder, export_dir, npc['EditorID'], assets), packages)}
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


def _form_map(builder: CellBuilder, ref_ids: dict, recs: list, quests: dict) -> dict:
    """FNV to FO4 forms: the cell's references, quests, player, objective states."""
    return {**{int(k, 16): v for k, v in ref_ids.items()}, PLAYER: PLAYER, **builder.objectives,
            **{int(r['FormID'], 16): quests[r['EditorID']] for r in recs}}


def _quests(builder: CellBuilder, export_dir: Path, recs: list, quests: dict, ref_ids: dict) -> None:
    """Write FNV quests `recs` (FO4 ids in `quests`) with their lines; `ref_ids` maps FNV references.

    A line's conditions see the cell's references, actors' bases, these
    quests, the player, actor values and the items FO4 shares or stands in. Conversations are built once every script's
    `TES4Talk_<topic>` scene is known; they share one Hub (every quest's lines
    and topic list), and the greeting goes to `_greeter`'s quest.
    """
    say = builder.say = SayTopics(builder, export_dir)
    form_map = {**builder.items.shared, **actor_values(HELPER_INDEX), **_form_map(builder, ref_ids, recs, quests),
                **builder.npc_ids}
    shared = _hub(builder, export_dir, say, recs, quests, form_map)
    greeter, done = _greeter(say, recs), []
    for rec in recs:
        fid = quests[rec['EditorID']]
        topics = {dial: builder.new_id() for dial in say.topics(rec)}
        builder.scripts.named.update({say.dials[d]['EditorID']: t for d, t in topics.items()})
        branch, blobs = say.build(rec, fid, topics, form_map) if topics else (None, [])
        talks = Conversations(say, rec, fid, form_map, XDI_KEYWORD, shared)
        record = quest_record(fid, rec, builder.scripts, ref_ids, talks.has_lines(),
                              rec['EditorID'] not in HAND_STARTED)
        done.append((fid, record, [branch] if branch else [], blobs, talks))
    built = set()
    for fid, record, branches, blobs, talks in sorted(done, key=lambda d: d[4].quest is not greeter):
        built |= {prop for prop, scene in list(builder.scripts.talks.items())
                  if prop not in built and talks.talk(prop, scene)}
        if talks.quest is greeter:
            talks.greeting(builder.packages.greets)
        builder.writer.add_record('QUST', pack_quest(record, fid, branches, blobs + talks.topics, talks.scenes))
        builder.counts['QUST'] += 1
        builder.counts['SCEN'] += len(talks.scenes)
    for prop in set(builder.scripts.talks) - built:
        builder.counts[f'{prop}: no lines in the cell quests'] += 1


def _hub(builder: CellBuilder, export_dir: Path, say: SayTopics, recs: list, quests: dict, form_map: dict) -> Hub:
    """The cell quests' Hub, listing only topics with a line whose conditions convert; a topic an AddTopic
    reveals is gated on the unlock global the scripts set, as the script converter's unlock plan names it."""
    plan = build_unlock_plan(load_records(str(export_dir), ('DIAL', 'INFO', 'QUST', 'SCPT')))
    shared = hub(say, recs, quests, plan['added'])
    shared.topics = tuple(d for d in shared.topics if any(
        r['ParentDIAL'].upper() == d and conditions_of(r, form_map, say.script_vars) is not None
        for r in shared.lines.values()))
    shared.gates = {d: builder.scripts.global_(plan['gated'][int(d, 16) & 0xFFFFFF]) for d in shared.topics
                    if int(d, 16) & 0xFFFFFF in plan['gated']}
    builder.counts['topics listed'] = len(shared.topics)
    return shared


def _greeter(say: SayTopics, recs: list) -> 'dict | None':
    """Of the quests with GREETING lines: a game-started one, highest priority."""
    greeting = [r for r in recs
                if any(i['ParentDIAL'].upper() == GREETING for i in say.infos.get(r['FormID'].upper(), []))]
    return max(greeting, key=lambda r: (r['EditorID'] not in HAND_STARTED, int(r.get('DATA.Priority', 0) or 0)),
               default=None)


def _voice(builder: CellBuilder, export_dir: Path, data_dir: Path, plugin: str) -> None:
    """The scripted lines' FNV recordings as .fuz under every cell actor's stand-in voice type."""
    folders = export_dir / 'sound' / 'voice' / 'falloutnv.esm'
    voices = [(folders / VOICES[label][0], VOICES[label][1]) for label, fnv, *_ in SPEAKERS
              if fnv in builder.npc_ids and label in VOICES]
    todo = voice.jobs(builder.say.voiced, voices, data_dir, plugin)
    folders = [data_dir / 'Sound' / 'Voice' / plugin / fo4 for _, fo4 in voices]
    builder.counts['stale voice files removed'] = voice.remove_stale(todo, folders)
    builder.counts['voice files'] = voice.convert(todo, FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator')


def _object_makers(builder: CellBuilder, export_dir: Path, scripts_dir: 'Path | None', refs: list) -> None:
    """Give `builder` its item, activator and package makers; `refs` are the cell's FNV references."""
    builder.sounds = Sounds(builder, export_dir)
    records = index(export_dir, ITEM_TYPES)
    consumables, builder.equipment = Consumables(builder, HELPER_INDEX), Equipment(builder)
    equipment = builder.equipment
    makers = {'ALCH': consumables.alch, 'AMMO': consumables.ammo, 'WEAP': equipment.weap, 'ARMO': equipment.armo}
    stand_ins = replacements.items(builder.table, builder.fo4, builder.masters, builder.plugin_dirs)
    builder.items = Items(builder, records, shared_engine_ids(builder.fo4, {**builder.bases, **records},
                                                              SHARED_TYPES), makers, stand_ins)
    builder.scripts = ObjectScripts(builder, export_dir, scripts_dir, HELPER_INDEX)
    builder.activators = Activators(builder, export_dir)
    builder.packages = Packages(builder, export_dir, {int(r['FormID'], 16) for r in refs
                                                      if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN'})
    builder.swaps = Swaps(builder, export_dir, {r['EditorID'].lower(): _model(builder.bases[int(r['NAME'], 16)][1])
                                                for r in refs if r.get('EditorID') and int(r['NAME'], 16) in builder.bases})
    builder.imods = ImageSpaces(builder)
    furniture = [(_place(r), str(export_dir / 'meshes' / _model(builder.bases[int(r['NAME'], 16)][1]).lower()))
                 for r in refs if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN']
    builder.poses = Poses(builder, {r['EditorID']: _place(r) for r in refs if r.get('EditorID')}, furniture)


def build(export_dir: Path, out: Path, data_dir: Path, cell_edid: str,
          scripts_dir: 'Path | None' = None, exterior: tuple = None, table: 'dict | None' = None,
          plugin_dirs: tuple = ()) -> collections.Counter:
    """Write the plugin and assets for the FNV interior cell `cell_edid`; counts of what was made.

    `scripts_dir` holds the converted scripts; the activators' are attached and compiled into <data_dir>/Scripts.
    `exterior` is (worldspace, (grid x, y), radius): that block of the worldspace too (exterior.Exterior).
    `table` is the replacement table (spike.replacements), its other plugins found in `plugin_dirs`.
    """
    cell = _find_cell(export_dir, cell_edid)
    all_refs = parse_export_file(str(export_dir / 'REFR.txt'))
    refs = [r for r in all_refs if r.get('ParentCELL') == cell['FormID']]
    links = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    world = Exterior(export_dir, all_refs, *exterior) if exterior else None
    outside = world.refs if world else []
    used = {int(r['NAME'], 16) for r in refs + outside}
    parts = Parts(used)
    builder = CellBuilder(export_dir, data_dir, _bases(export_dir, used | parts.fids()), table, plugin_dirs)
    builder.parts = parts
    _object_makers(builder, export_dir, scripts_dir, refs)
    cell_fid = builder.new_id()
    ids = {r['FormID']: builder.new_id() for r in refs}
    ext_ids = world.ids(len(builder.masters)) if world else {}
    quests = {edid: builder.new_id() for edid in CELL_QUESTS}
    quest_recs = [r for r in parse_export_file(str(export_dir / 'QUST.txt')) if r.get('EditorID') in quests]
    builder.scripts.named.update({**{r['EditorID']: ids[r['FormID']] for r in refs if r.get('EditorID')}, **quests})
    builder.objectives = objective_globals(builder, quest_recs)
    vanilla = _vanilla(builder.fo4, {CELL_FO4, BASE_IMAGESPACE, TEST_CHEST} | set(STAND_INS.values()))
    actors = _actors(builder, export_dir, cell['FormID'], vanilla, _form_map(builder, ids, quest_recs, quests))
    qa_refs, teleports = _doors(builder, [r for r in refs if 'XTEL.Door' in r], links, {**ids, **ext_ids})
    qa_refs += _test_chest(builder, vanilla[TEST_CHEST]) + _qa_creatures(builder, export_dir, data_dir)
    teleports.update(_linked([r for r in outside if 'XTEL.Door' in r], ids))
    persistent, temporary = _placed(builder, refs, ids, teleports)
    persistent += actors
    _quests(builder, export_dir, quest_recs, quests, {**ids, **builder.actor_ids})
    character.build(builder, export_dir, data_dir, out.name, HELPER_INDEX)
    temporary += _navmesh(builder, export_dir, cell['FormID'], cell_fid, ids)
    _cell_group(builder, export_dir, cell, cell_fid, vanilla, (persistent + builder.poses.placed, temporary, qa_refs))
    if world:
        for ref in world.placement_order():
            builder.base(int(ref['NAME'], 16))
        builder.writer.add_raw_group('WRLD', world.group(builder, lambda r: _placed(builder, r, ext_ids, teleports),
                                                         data_dir))
    return _finish(builder, export_dir, data_dir, out, scripts_dir)


def _cell_group(builder: CellBuilder, export_dir: Path, cell: dict, cell_fid: int, vanilla: dict, children: tuple):
    """Add the CELL group: the FNV cell with `children` (persistent, temporary) and QASmoke with its stand-in doors."""
    persistent, temporary, qa_refs = children
    qa_record = pack_fo4_record('CELL', CELL_FO4, vanilla[CELL_FO4].flags, vanilla[CELL_FO4].body)
    template = sub_map(vanilla[CELL_FO4].body)
    imagespace = _imagespace(builder, export_dir, cell, vanilla[BASE_IMAGESPACE].body)
    edid = cell['EditorID']
    record = R.pack_cell(cell_fid, f'FNV_{edid}', cell.get('FULL', edid), int(cell['DATA.Flags']) & 0xFF,
                         lighting(cell, template[b'XCLL']), struct.unpack('<I', template[b'LTMP'])[0],
                         imagespace or struct.unpack('<I', template[b'XCIM'])[0])
    builder.writer.add_raw_group('CELL', R.pack_interior_cells([(record, cell_fid, persistent, temporary),
                                                                (qa_record, CELL_FO4, qa_refs, b'')]))


def _finish(builder: CellBuilder, export_dir: Path, data_dir: Path, out: Path, scripts_dir) -> collections.Counter:
    """Collision, lowered skeletons, voices and sounds, the texture BA2 and scripts, then the plugin; the counts."""
    failed = finish([data_dir / 'Meshes' / model for model, _ in builder.meshes.values()])
    builder.counts['meshes without collision (Elric failed)'] = len(failed)
    for model in sorted(builder.weapons):
        weapon.dress_file(data_dir / 'Meshes' / model)
    builder.counts['weapon meshes'] = len(builder.weapons)
    builder.counts['human skeletons lowered'] = skeleton.write(data_dir)
    _voice(builder, export_dir, data_dir, out.name)
    todo = [job for job in builder.sounds.jobs if not job[1].exists()]
    builder.counts['sound files'] = voice.convert(todo, FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator')
    builder.counts['textures packed'] = pack_textures(data_dir, out.name, (LUT_FOLDER,))
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
    ap.add_argument('--world', help='FNV worldspace editor ID to add a block of (with --around)')
    ap.add_argument('--around', type=int, nargs=2, default=(0, 0), metavar=('X', 'Y'), help='The block\'s center cell')
    ap.add_argument('--radius', type=int, default=1, help='Cells around the center (1: a 3x3 block)')
    ap.add_argument('--replacements', type=Path, help='A replacement table laid over the defaults (JSON)')
    ap.add_argument('--plugin-dirs', nargs='*', default=(), help='Folders holding plugins the table names')
    ap.add_argument('cell', help='FNV interior cell editor ID')
    args = ap.parse_args()
    exterior = (args.world, tuple(args.around), args.radius) if args.world else None
    table = replacements.load(args.replacements)
    for key, count in sorted(build(Path(args.export), Path(args.out), Path(args.data), args.cell,
                                   args.scripts, exterior, table, tuple(args.plugin_dirs)).items()):
        print(f'{key}: {count}')


if __name__ == '__main__':
    main()
