"""Spike 2 step 2: an FNV interior cell rebuilt in Fallout 4 (built through fo4_import.pipeline.run).

The cell keeps FNV's lighting, every placed object with a mesh, its lights,
doors, misc items, containers, furniture and activators with their
converted scripts (other types are statics for now). Every interior a door
leads into is built too (interiors.py); a door that led out of the build
leads to a stand-in door in QASmoke, and back. Engine objects FO4
shares keep their base. Meshes get FNV's collision through Elric.

See: docs/fork/fo4_spikes.md#spike-2-cell
"""

import collections
import math
import struct
from pathlib import Path

from fo4_import.base.ba2_pack import pack_textures
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM, fnv_esm
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest
from fo4_import.spike.consumables import Consumables
from fo4_import.spike.creatures import Creatures
from fo4_import.spike.equipment import Equipment
from fo4_import.spike.scol import PART_SITE, Parts, compose
from fo4_import.spike.emittance import Emittance
from fo4_import.spike.lighting_template import resolved
from fo4_import.spike.imagespace import BASE_IMAGESPACE, DISPLAY_GAMMA, LUT_FOLDER, base_hdr, pack_imgs, write_lut
from fo4_import.spike.activators import Activators
from fo4_import.spike import character, replacements, skeleton
from fo4_import.spike.attach import ObjectScripts
from fo4_import.spike.conversation import GREETING, Conversations, Hub, hub
from fo4_import.spike.furniture import furniture, markers
from fo4_import.spike.navmesh import navi, navmeshes
from fo4_import.spike.exterior import Exterior
from fo4_import.spike.imods import ImageSpaces
from fo4_import.spike.idle_markers import IdleMarkers
from fo4_import.spike.interiors import scope
from fo4_import.spike.placement import map_markers, place, placement
from fo4_import.spike.npcs import Npcs
from fo4_import.spike.packages import Packages, beds
from fo4_import.spike.poses import Poses
from fo4_import.spike.sounds import Sounds
from fo4_import.spike.swaps import Swaps
from fo4_import.spike.factions import write_all as write_factions
from fo4_import.spike.globals import write_all as write_globals
from fo4_import.spike.locations import Locations, encounter_zones
from fo4_import.spike.items import ENGINE_IDS, ITEM_TYPES, Items, index, shared_engine_ids
from fo4_import.nif import weapon
from fo4_import.spike import records as R
from fo4_import.spike import voice
from fo4_import.spike.dialogue import CELL_FO4
from fo4_import.spike.say_topics import SayTopics, actor_values, conditions_of
from fo4_import.spike.script import compile_into
from fo4_import.spike.quest import objective_globals, quest_record
from fo4_import.spike.statics import tree_assets, write_assets
from fo4_import.pipeline import elric_cache
from fo4_import.pipeline.converters import PLACED, placed_types
from fo4_import.pipeline.export_index import export_records
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from script_convert.context_setup import load_records
from tes5_import.base.tes5_reader import first_sub, records, sub_map, walk
from tes5_import.base.writer import pack_subrecord
from tes5_import.dialogue.unlocks import build_unlock_plan

MASTERS = ['Fallout4.esm', FALLOUT4_HELPER_PLUGIN, 'XDI.esm']
#: Master index of the helper plugin (TES4Helpers.esl).
HELPER_INDEX = 1
#: XDI's menu keyword (conversation menus show more than four options).
XDI_KEYWORD = MASTERS.index('XDI.esm') << 24 | R.XDI_KEYWORD
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
#: derive_formid site of a generated record (CellBuilder.new_id; key: its owner and count there).
MADE_SITE = 'FNV made'
#: The types whose engine objects FO4 may share.
SHARED_TYPES = ('STAT', 'MISC')
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
#: The bit every vanilla FO4 omni light carries.
LIGHT_BASE = 0x1
#: FNV LIGH flags: flicker or flicker slow; pulse or pulse slow; either slow.
MOVING_LIGHT, PULSING_LIGHT, SLOW_LIGHT = 0x8 | 0x40, 0x80 | 0x100, 0x40 | 0x100
#: FO4 flicker (period, intensity, movement): vanilla's most common, FNV's fFlickerMovement (8) as movement.
FLICKER = (0.33, 0.45, 8.0)
#: A steady light's flicker fields, as vanilla's most common omni light.
STEADY = (1.0, 0.0, 0.0)
#: CELL DATA flag of a cell with water (both games).
HAS_WATER = 0x2
#: XCLL fog max: FNV fog has no cap (see lighting()); vanilla FO4 writes 1.0 in 307 of 606 interiors.
FOG_MAX = 1.0
#: XCLL fog clip distance: none, as 578 of 606 vanilla FO4 interiors (FO4 shows bright background past a clip).
NO_CLIP = 0.0


def world_model(rec: dict) -> str:
    """An FNV base record's world model ('' for none)."""
    return rec.get('Model.MODL') or rec.get('Male.WorldModel.MODL') or ''


def _bounds(rec: dict) -> tuple:
    """An FNV record's OBND."""
    return tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))


def _floats(rec: dict, prefix: str, keys: tuple) -> tuple:
    """`rec[prefix + key]` for each key, as floats."""
    return tuple(float(rec[prefix + k]) for k in keys)


def _color(cell: dict, key: str) -> bytes:
    """An FNV XCLL colour as FO4 byte colours (RGB, 0)."""
    return bytes(int(cell[f'XCLL.{key}{c}']) for c in 'RGB') + b'\0'


def lighting(cell: dict, template: bytes) -> bytes:
    """FO4 XCLL: FNV's colours, fog, directional light and fog power over `template`, inheriting nothing.

    FNV's ambient colour also fills FO4's six directional ambient colours and
    its fog colour the far and both height-fog colours (FNV has no height fog);
    fog max is 1 (FNV's fog has no cap) and the clip distance 0, so past the
    far distance only fog shows, as in FNV; other FO4-only fields keep `template`'s.
    Fog power is FNV's x 2.2: FO4 mixes fog in linear light, FNV in display colours.
    See: docs/fork/fo4_pipeline.md#interiors
    """
    out = bytearray(template)
    out[0:12] = _color(cell, 'Ambient') + _color(cell, 'Directional') + _color(cell, 'Fog')
    out[12:40] = struct.pack('<2f2i3f', *_floats(cell, 'XCLL.', ('FogNear', 'FogFar')),
                             int(cell['XCLL.DirectionalRotXY']), int(cell['XCLL.DirectionalRotZ']),
                             float(cell['XCLL.DirectionalFade']), NO_CLIP,
                             float(cell['XCLL.FogPower']) * DISPLAY_GAMMA)
    out[40:64] = _color(cell, 'Ambient') * 6
    out[72:80] = _color(cell, 'Fog') + struct.pack('<f', FOG_MAX)
    out[88:92] = bytes(4)
    out[100:108] = _color(cell, 'Fog') * 2
    return bytes(out)


def light_data(rec: dict) -> tuple:
    """pack_ligh's light of FNV LIGH `rec`: radius, colour, flags, FNV's falloff exponent and FOV, flicker.

    A flickering light takes vanilla's most common flicker (31 of 182) with
    FNV's flicker movement, a pulsing one its period and intensity without
    movement; a slow one twice the period, as FNV halves its flicker clock.
    See: docs/fork/fo4_pipeline.md#lights
    """
    fnv = int(rec['DATA.Flags'])
    period = FLICKER[0] * (2 if fnv & SLOW_LIGHT else 1)
    flicker = ((period, *FLICKER[1:]) if fnv & MOVING_LIGHT else (period, FLICKER[1], 0.0) if fnv & PULSING_LIGHT
               else STEADY)
    return (int(rec['DATA.Radius']), tuple(int(rec[f'DATA.Color.{c}']) for c in 'RGB'), light_flags(fnv),
            float(rec.get('DATA.FalloffExponent', 1.0)), float(rec.get('DATA.FOV', 90.0)), flicker)


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
        self.top, self.owned = ENGINE_IDS, collections.Counter()
        own = self.writer.own_index << 24
        self.writer.reserve_source_ids({own | r.form_id & 0xFFFFFF for r in records(fnv_esm(), bodies=())})
        self.made, self.meshes, self.items, self.activators, self.scripts = {}, {}, None, None, None
        self.actor_ids, self.npc_ids, self.say, self.packages, self.objectives = {}, {}, None, None, {}
        self.globals, self.factions, self.zones, self.places, self.locations = {}, {}, {}, {}, None
        self.swaps, self.imods, self.poses, self.parts, self.weapons = None, None, None, None, set()
        self.equipment, self.load_doors, self.imagespaces = None, {}, set()
        self.fo4 = FALLOUT4_ESM.read_bytes()
        self.idle_markers = IdleMarkers(self.fo4)
        self.keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                         for r, _ in walk(self.fo4, b'KYWD')}
        self.counts = collections.Counter()

    def fnv_id(self, fnv) -> int:
        """FormID of FNV record `fnv` (int or hex) made 1:1: FNV's own object id."""
        oid = (int(fnv, 16) if isinstance(fnv, str) else fnv) & 0xFFFFFF
        self.top = max(self.top, oid + 1)
        return self.writer.own_index << 24 | oid

    def new_id(self, owner: str) -> int:
        """A generated record's FormID, hashed from its `owner` (FNV data) and count.

        See: docs/fork/fo4_spikes.md#formids
        """
        n = self.owned[owner]
        self.owned[owner] += 1
        return self.writer.derive_formid(MADE_SITE, f'{owner} {n}' if n else owner)

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

    def base(self, fnv_fid: int) -> 'int | None':
        """The FO4 base for an FNV base FormID, made once by its type's converter (pipeline.converters.PLACED);
        None: not converted."""
        if fnv_fid < ENGINE_IDS:
            return self.items.shared.get(fnv_fid)
        if fnv_fid not in self.made:
            sig, rec = self.bases.get(fnv_fid) or self._item_base(fnv_fid)
            self.made[fnv_fid] = getattr(self, PLACED[sig])(fnv_fid, sig, rec) if sig in PLACED else None
        return self.made[fnv_fid]

    def _item_base(self, fnv_fid: int) -> tuple:
        """(type, record) of an FNV item base items.item() makes; (None, None) if not."""
        found = self.items.records.get(fnv_fid, (None, None))
        return found if found[0] in placed_types('item') else (None, None)

    def item(self, fnv_fid: int, _sig, _rec) -> 'int | None':
        """Converter: an FNV misc item or container as itself (spike.items)."""
        return self.items.item(fnv_fid)

    def idle(self, _fnv_fid: int, _sig, rec: dict) -> 'int | None':
        """Converter: FNV idle marker `rec`'s vanilla stand-in (idle_markers)."""
        made = self.idle_markers.of(rec)
        self.counts['idle marker ' + ('placed' if made else 'left out')] += 1
        return made

    def sound(self, fnv_fid: int, _sig, _rec) -> int:
        """Converter: an FNV sound marker (spike.sounds)."""
        return self.sounds.marker(fnv_fid)

    def record(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """Converter: `rec`'s FO4 record (_make); None for no mesh, light or script."""
        return self._make(sig, rec, self.fnv_id(fnv_fid)) if sig in ('LIGH', 'ACTI') or world_model(rec) else None

    def tree(self, fnv_fid: int, _sig, rec: dict) -> int:
        """Converter: the FO4 static for FNV TREE `rec`, its mesh generated from its SpeedTree; FormID hashed
        from FNV's."""
        fid = self.writer.derive_formid(TREE_SITE, f'{fnv_fid:08X}')
        model, bounds = self.meshes[world_model(rec)] = tree_assets(self.export_dir, rec, self.data_dir)
        self.writer.add_record('STAT', R.pack_stat(fid, f'FNV_{rec["EditorID"]}', model, bounds or _bounds(rec)))
        self.counts['TREE'] += 1
        return fid

    def pickup(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """Converter: the FO4 item for placed FNV item `rec`; without one, its static (FNV's FormID)."""
        item = self.items.item(fnv_fid)
        if item is not None or not world_model(rec):
            return item
        return self._make(sig, rec, self.fnv_id(fnv_fid))

    def _make(self, sig: str, rec: dict, fid: int) -> int:
        """Write the FO4 record for FNV base `rec` of type `sig` on FormID `fid`; its FormID."""
        edid = f'FNV_{rec["EditorID"]}'
        model, bounds = self.mesh(world_model(rec)) if world_model(rec) else ('', None)
        bounds = bounds or _bounds(rec)
        if sig == 'LIGH':
            record = R.pack_ligh(fid, edid, _bounds(rec), model, light_data(rec), float(rec.get('FNAM.Fade', 1.0)))
        elif sig == 'FURN':
            marks = markers(str(self.export_dir / 'meshes' / world_model(rec).replace('/', '\\').lower()))
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
        made = write_assets(self.export_dir, world_model(rec), self.data_dir, load=True) \
            if sig == 'DOOR' and plain is not None else None
        self.load_doors[fnv_fid] = plain
        if made is not None:
            self.meshes[f'{world_model(rec)}#load'] = made
            fid = self.load_doors[fnv_fid] = self.writer.derive_formid(LOAD_DOOR_SITE, f'{fnv_fid:08X}')
            self.writer.add_record('DOOR', self._door(fid, f'FNV_{rec["EditorID"]}Load', rec, made))
            self.counts['load doors made static'] += 1
        return self.load_doors[fnv_fid]


def _static(sig: str, fid: int, edid: str, model: str, bounds: tuple) -> tuple:
    """(FO4 type, record): an FNV MSTT as a movable static, anything else as a static."""
    if sig == 'MSTT':
        return 'MSTT', R.pack_mstt(fid, edid, model, bounds)
    return 'STAT', R.pack_stat(fid, edid, model, bounds)


def find_cell(export_dir: Path, edid: str) -> dict:
    """The FNV interior CELL record with EditorID `edid`."""
    for rec in export_records(export_dir, 'CELL'):
        if rec.get('EditorID') == edid:
            return rec
    raise SystemExit(f'no CELL {edid}')


def placed_bases(export_dir: Path, used: set) -> dict:
    """{FNV FormID: (type, record)} of the used bases this spike converts."""
    out = {}
    for sig in placed_types('record', 'pickup', 'tree', 'sound', 'idle'):
        for rec in export_records(export_dir, sig):
            fid = int(rec['FormID'], 16)
            if fid in used:
                out[fid] = (sig, rec)
    return out


def _linked(door_refs: list, ids: dict) -> dict:
    """{door ref: its teleport} of doors whose partner is in `ids`."""
    return {r['FormID']: (ids[r['XTEL.Door']], *place(r, 'XTEL.')) for r in door_refs if r['XTEL.Door'] in ids}


def _doors(builder: CellBuilder, door_refs: list, links: dict, ids: dict) -> tuple:
    """Stand-in doors in QASmoke for the cell's teleport doors: (their REFRs, {door ref: its teleport}).

    A door whose partner is converted leads to it; for another, a stand-in
    leads to where the FNV door's partner led into the cell (the cell door's
    own position when the partner is not in the export).
    """
    qa_refs, teleports = b'', _linked(door_refs, ids)
    for i, ref in enumerate(r for r in door_refs if r['FormID'] not in teleports):
        pos = (DOOR_START[0] + i * DOOR_SPACING, DOOR_START[1], DOOR_START[2])
        stand_in, partner = builder.new_id(f'DOOR stand-in {ref["FormID"]}'), links.get(ref['XTEL.Door'], ref)
        inside = place(partner, 'XTEL.') if partner is not ref else place(ref)
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
    return b''.join(builder.creatures.placed(edid, pos, rot) for edid, pos, rot in QA_CREATURES)


def _built(builder: CellBuilder, refs: list) -> list:
    """The references _placed() writes as themselves, the only ones linked to.
    See: docs/fork/fo4_pipeline.md#audit
    """
    return [r for r in refs if int(r['NAME'], 16) not in builder.parts.parts
            and builder.base(int(r['NAME'], 16)) is not None]


def _placed(builder: CellBuilder, refs: list, ids: dict, teleports: dict) -> tuple:
    """(persistent, temporary) REFRs of the cell's converted references."""
    persistent, temporary, owners = b'', b'', {**builder.factions, **builder.npc_ids}
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
        record = R.pack_refr(ids[ref['FormID']], base, *place(ref), float(ref.get('XSCL.Scale', 1.0)), radius,
                             teleports.get(ref['FormID']), keep, placement(int(ref['FormID'], 16), builder.ref_ids, owners) + _lock(builder, ref)
                             + builder.emittance.xemi(ref),
                             bool(int(ref['RecordFlags']) & R.INITIALLY_DISABLED), ids.get(ref.get('XLKR.LinkedRef'), 0))
        persistent, temporary = (persistent + record, temporary) if keep else (persistent, temporary + record)
        builder.counts['placed'] += 1
    return persistent, temporary


def _lock(builder: CellBuilder, ref: dict) -> bytes:
    """The XLOC of a locked FNV reference (level, its key as a FO4 KEYM, flags); b'' when it has no lock.

    FO4 numbers lock levels as FNV does (0, 25, 50, 75, 100; 255 requires the key).
    See: docs/fork/fo4_pipeline.md#locks
    """
    if 'XLOC.Level' not in ref:
        return b''
    fnv_key = int(ref.get('XLOC.Key', '0'), 16)
    key = (builder.items.item(fnv_key) or 0) if fnv_key else 0
    builder.counts['locked references'] += 1
    return pack_subrecord('XLOC', struct.pack('<B3xIB3xI', int(ref['XLOC.Level']), key, int(ref.get('XLOC.Flags', 0)), 0))


def _part_refs(builder: CellBuilder, ref: dict) -> bytes:
    """The REFRs of FNV SCOL reference `ref`'s parts, on hashed FormIDs (scol.PART_SITE)."""
    position, angle = place(ref)
    scale, out = float(ref.get('XSCL.Scale', 1.0)), b''
    disabled = bool(int(ref['RecordFlags']) & R.INITIALLY_DISABLED)
    for index, (part, placement) in enumerate(builder.parts.parts[int(ref['NAME'], 16)]):
        base = builder.base(part)
        if base is None:
            builder.counts['SCOL part skipped'] += 1
            continue
        at, turn, size = compose(position, angle, scale, placement)
        fid = builder.writer.derive_formid(PART_SITE, (ref['FormID'], index))
        out += R.pack_refr(fid, base, at, turn, size, persistent=False, disabled=disabled)
        builder.counts['SCOL parts placed'] += 1
    builder.counts['SCOL references split'] += 1
    return out


def _vanilla(fo4: bytes, fids: set) -> dict:
    """{FormID: Record} of the Fallout4.esm records `fids` (CELL, IMGS, NPC_, CONT)."""
    return {rec.form_id: rec for rec, _ in walk(fo4, b'CELL', b'IMGS', b'NPC_', b'CONT')
            if rec.form_id in fids}


def _imagespace(builder: CellBuilder, export_dir: Path, cell: dict, base_body: bytes):
    """The FO4 imagespace made once from the FNV cell's (FNV's grading in a LUT); None if the cell names none."""
    if 'XCIM.Imagespace' not in cell:
        builder.counts['cell without an FNV imagespace'] += 1
        return None
    fid = builder.fnv_id(cell['XCIM.Imagespace'])
    if fid not in builder.imagespaces:
        fnv = next(r for r in export_records(export_dir, 'IMGS') if r['FormID'] == cell['XCIM.Imagespace'])
        lut = write_lut(bytes.fromhex(fnv['DNAM']), fnv['EditorID'], builder.data_dir, base_hdr(base_body))
        builder.writer.add_record('IMGS', pack_imgs(fid, f'FNV_{fnv["EditorID"]}', base_body, lut))
        builder.imagespaces.add(fid)
        builder.counts[f'imagespace: {fnv["EditorID"]}'] += 1
    return fid


def _navmesh(builder: CellBuilder, export_dir: Path, pathing: dict, ids: dict) -> dict:
    """{FNV cell: FO4 NAVM records} of the FNV navmeshes in `pathing`'s cells, linked and registered in NAVI."""
    recs = [r for r in export_records(export_dir, 'NAVM') if r.get('DATA.Cell') in pathing]
    records, infos = navmeshes(recs, pathing, ids, builder.fnv_id)
    if infos:
        builder.writer.add_record('NAVI', navi(builder.fo4, infos))
        builder.counts['NAVM'] += len(recs)
    return records


def _form_map(builder: CellBuilder, ref_ids: dict, recs: list, quests: dict) -> dict:
    """FNV to FO4 forms: references, quests, player, objectives, globals, factions."""
    return {**builder.globals, **builder.factions, **{int(k, 16): v for k, v in ref_ids.items()}, PLAYER: PLAYER,
            **builder.objectives,
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
        topics = {dial: builder.new_id(f'DIAL {rec["FormID"]} {dial}') for dial in say.topics(rec)}
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
    """The built lines' FNV recordings as .fuz under each NPC's converted voice type (voice_types); files in
    any other folder of the plugin's voice directory are stale."""
    folders = export_dir / 'sound' / 'voice' / 'falloutnv.esm'
    voices = [(folders / fnv.lower(), fo4) for fo4, fnv in sorted(builder.npcs.voices.made.items())]
    todo = voice.jobs(builder.say.voiced, voices, data_dir, plugin)
    ours = data_dir / 'Sound' / 'Voice' / plugin
    builder.counts['stale voice files removed'] = voice.remove_stale(todo, [p for p in ours.glob('*') if p.is_dir()])
    builder.counts['voice files written'] = voice.convert([job for job in todo if not job[1].exists()],
                                                          FALLOUT4_DIR / 'Tools' / 'LipGen' / 'LipGenerator')


def _object_makers(builder: CellBuilder, export_dir: Path, scripts_dir: 'Path | None', refs: list,
                   every: list) -> None:
    """Give `builder` its item, activator and package makers; `refs` are the cell's FNV references, `every` all
    the build's (packages sit in their seats)."""
    builder.sounds, builder.globals = Sounds(builder, export_dir), write_globals(builder, export_dir)
    builder.factions = write_factions(builder, export_dir)
    records = index(export_dir, ITEM_TYPES)
    consumables, builder.equipment = Consumables(builder, HELPER_INDEX), Equipment(builder)
    equipment = builder.equipment
    makers = {'ALCH': consumables.alch, 'AMMO': consumables.ammo, 'WEAP': equipment.weap, 'ARMO': equipment.armo}
    stand_ins = replacements.items(builder.table, builder.fo4, builder.masters, builder.plugin_dirs)
    builder.items = Items(builder, records, shared_engine_ids(builder.fo4, {**builder.bases, **records},
                                                              SHARED_TYPES), makers, stand_ins)
    builder.scripts = ObjectScripts(builder, export_dir, scripts_dir, HELPER_INDEX)
    builder.activators = Activators(builder, export_dir)
    builder.creatures = Creatures(builder, export_dir, builder.data_dir)
    seats = [r for r in every if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN']
    builder.packages = Packages(builder, export_dir, {int(r['FormID'], 16) for r in seats}, beds(builder, seats))
    builder.swaps = Swaps(builder, export_dir, {r['EditorID'].lower(): world_model(builder.bases[int(r['NAME'], 16)][1])
                                                for r in refs if r.get('EditorID') and int(r['NAME'], 16) in builder.bases})
    builder.imods = ImageSpaces(builder)
    furniture = [(place(r), str(export_dir / 'meshes' / world_model(builder.bases[int(r['NAME'], 16)][1]).lower()))
                 for r in refs if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN']
    builder.poses = Poses(builder, {r['EditorID']: place(r) for r in refs if r.get('EditorID')}, furniture)


def _cell_quests(builder: CellBuilder, export_dir: Path, every: list, ids: dict) -> tuple:
    """(CELL_QUESTS records, {EditorID: FO4 FormID}); the scripts learn them and `every` reference by name."""
    quest_recs = [r for r in export_records(export_dir, 'QUST') if r.get('EditorID') in CELL_QUESTS]
    quests = {r['EditorID']: builder.fnv_id(r['FormID']) for r in quest_recs}
    builder.scripts.named.update({**{r['EditorID']: ids[r['FormID']] for r in every if r.get('EditorID') and r['FormID'] in ids}, **quests})
    builder.objectives = objective_globals(builder, quest_recs)
    return quest_recs, quests


def build(export_dir: Path, out: Path, data_dir: Path, cell_edid: str,
          scripts_dir: 'Path | None' = None, exterior: tuple = None, table: 'dict | None' = None,
          plugin_dirs: tuple = ()) -> collections.Counter:
    """Write the plugin and assets for the FNV interior cell `cell_edid`; counts of what was made.

    `scripts_dir` holds the converted scripts (attached, compiled into <data_dir>/Scripts). `exterior` is
    (worldspace, (x, y) low, (x, y) high): that rectangle of cells too. Every interior a door leads into is
    built as well (interiors.reached); actors and quests are the cell's. `table` is the replacement table,
    its other plugins found in `plugin_dirs`.
    """
    cell = find_cell(export_dir, cell_edid)
    all_refs = export_records(export_dir, 'REFR')
    refs = [r for r in all_refs if r.get('ParentCELL') == cell['FormID']]
    links = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    world = Exterior(export_dir, all_refs, *exterior) if exterior else None
    outside = world.refs if world else []
    interiors, every = scope(export_dir, all_refs, cell, outside)
    used = {int(r[key], 16) for r in every + outside for key in ('NAME', 'XEMI.Emittance') if key in r}
    parts = Parts(used)
    builder = CellBuilder(export_dir, data_dir, placed_bases(export_dir, used | parts.fids()), table, plugin_dirs)
    builder.parts, builder.emittance = parts, Emittance(builder, export_dir)
    _object_makers(builder, export_dir, scripts_dir, refs, every + outside)
    ids = {r['FormID']: builder.fnv_id(r['FormID']) for r in _built(builder, every)}
    ext_ids = {r['FormID']: builder.fnv_id(r['FormID']) for r in _built(builder, outside)}
    quest_recs, quests = _cell_quests(builder, export_dir, every, ids)
    vanilla = _vanilla(builder.fo4, {CELL_FO4, BASE_IMAGESPACE, TEST_CHEST})
    actors = _people(builder, export_dir, (interiors, world),
                     {**_form_map(builder, {**ids, **ext_ids}, quest_recs, quests), **_cells(builder, interiors, world)},
                     {**ids, **ext_ids})
    qa_refs, teleports = _doors(builder, [r for r in every if 'XTEL.Door' in r], links, {**ids, **ext_ids})
    qa_refs += _test_chest(builder, vanilla[TEST_CHEST]) + _qa_creatures(builder, export_dir, data_dir)
    teleports.update(_linked([r for r in outside if 'XTEL.Door' in r], ids))
    builder.ref_ids = {**ids, **ext_ids, **builder.actor_ids}
    _places(builder, export_dir, world, (all_refs, outside, interiors))
    persistent, temporary = _placed(builder, refs, ids, teleports)
    _quests(builder, export_dir, quest_recs, quests, {**ids, **builder.actor_ids})
    character.build(builder, export_dir, data_dir, out.name, HELPER_INDEX)
    pathing = {c['FormID']: (0, builder.fnv_id(c['FormID'])) for c in interiors}
    navmesh = _navmesh(builder, export_dir, {**pathing, **(world.pathing(builder) if world else {})}, {**ids, **ext_ids})
    rooms = _rooms(builder, (interiors, every), (ids, teleports), navmesh, (persistent + builder.poses.placed, temporary),
                   actors)
    _cell_group(builder, export_dir, vanilla, rooms, qa_refs)
    if world:
        for ref in world.placement_order():
            builder.base(int(ref['NAME'], 16))
        builder.writer.add_raw_group('WRLD', world.group(builder, lambda r: _placed(builder, r, ext_ids, teleports),
                                                         data_dir, navmesh, actors))
    return _finish(builder, export_dir, data_dir, out, scripts_dir)


def _rooms(builder: CellBuilder, scoped: tuple, placing: tuple, navmesh: dict, first: tuple, actors: dict) -> list:
    """[(cell, persistent, temporary)] of the interiors in `scoped` (cells, their references), each with its
    navmeshes and `actors` {FNV cell: (persistent, temporary)}: the first's references are `first`, the others'
    placed with `placing` (ids, teleports)."""
    interiors, every = scoped
    placed = [first] + [_placed(builder, [r for r in every if r['ParentCELL'] == c['FormID']], *placing)
                        for c in interiors[1:]]
    out = []
    for c, (p, t) in zip(interiors, placed):
        people = actors.get(c['FormID'], (b'', b''))
        out.append((c, p + people[0], t + people[1] + navmesh.get(c['FormID'], b'')))
    return out


def _cells(builder: CellBuilder, interiors: list, world) -> dict:
    """{FNV cell: FO4 cell} of the built interiors and `world`'s (or None's) cells."""
    return {int(c['FormID'], 16): builder.fnv_id(c['FormID'])
            for c in interiors + (list(world.cells.values()) if world else [])}


def _people(builder: CellBuilder, export_dir: Path, scoped: tuple, form_map: dict, ids: dict) -> dict:
    """{FNV cell: (persistent, temporary)} ACHRs of the FNV NPCs and creatures placed in the built cells (npcs.py);
    `scoped` is (the interiors, the exterior block or None)."""
    interiors, world = scoped
    inside = {c['FormID'] for c in interiors}

    def cell_of(ref: dict) -> 'str | None':
        """The FNV cell a built actor stands in; None outside the build."""
        cell = ref.get('ParentCELL')
        return cell if cell in inside or (world and world.holds(ref)) else None
    builder.npcs = Npcs(builder, export_dir, form_map, builder.creatures)
    return builder.npcs.placed(export_records(export_dir, 'ACHR') + export_records(export_dir, 'ACRE'), cell_of, ids,
                               {**builder.factions, **builder.npc_ids})


def _cell_group(builder: CellBuilder, export_dir: Path, vanilla: dict, rooms: list, qa_refs: bytes):
    """Add the CELL group: each FNV interior of `rooms` [(cell, persistent, temporary)] and QASmoke with its
    stand-in doors."""
    qa_record = pack_fo4_record('CELL', CELL_FO4, vanilla[CELL_FO4].flags, vanilla[CELL_FO4].body)
    cells = [(_interior(builder, export_dir, cell, vanilla), builder.fnv_id(cell['FormID']), persistent, temporary)
             for cell, persistent, temporary in rooms]
    builder.writer.add_raw_group('CELL', R.pack_interior_cells(cells + [(qa_record, CELL_FO4, qa_refs, b'')]))


def _places(builder: CellBuilder, export_dir: Path, world, scoped: tuple) -> None:
    """Write the encounter zones and `world`'s locations; `builder.places` maps each interior to its location.
    `scoped` is (every reference, the exterior block's, the interiors built).
    See: docs/fork/fo4_pipeline.md#locations
    """
    builder.zones = encounter_zones(builder, export_dir, {**builder.factions, **builder.npc_ids})
    if world:
        builder.locations = Locations(builder, world.world, map_markers(builder.ref_ids))
        builder.places = builder.locations.interiors(*scoped)


def _zone(builder: CellBuilder, cell: dict) -> int:
    """The FO4 encounter zone of FNV cell `cell`; 0 without one."""
    return builder.zones.get(int(cell.get('XEZN.EncounterZone', '0'), 16), 0)


def _interior(builder: CellBuilder, export_dir: Path, cell: dict, vanilla: dict) -> bytes:
    """The FO4 CELL of FNV interior `cell`: FNV's lighting, imagespace, water height and owner over QASmoke's."""
    template = sub_map(vanilla[CELL_FO4].body)
    imagespace = _imagespace(builder, export_dir, cell, vanilla[BASE_IMAGESPACE].body)
    edid, flags = cell['EditorID'], int(cell['DATA.Flags'])
    water = float(cell['XCLW.WaterHeight']) if flags & HAS_WATER and 'XCLW.WaterHeight' in cell else 0.0
    return R.pack_cell(builder.fnv_id(cell['FormID']), f'FNV_{edid}', cell.get('FULL', edid), flags & 0xFF,
                       lighting(resolved(export_dir, cell), template[b'XCLL']), struct.unpack('<I', template[b'LTMP'])[0],
                       imagespace or struct.unpack('<I', template[b'XCIM'])[0], water,
                       {**builder.factions, **builder.npc_ids}.get(int(cell.get('XOWN.Owner', '0'), 16), 0),
                       (builder.places.get(cell['FormID'], 0), _zone(builder, cell)))


def _finish(builder: CellBuilder, export_dir: Path, data_dir: Path, out: Path, scripts_dir) -> collections.Counter:
    """Collision, lowered skeletons, voices and sounds, the texture BA2 and scripts, then the plugin; the counts."""
    failed = elric_cache.finish([data_dir / 'Meshes' / model for model, _ in builder.meshes.values()])
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
    builder.writer.next_object_id = builder.top
    out.parent.mkdir(parents=True, exist_ok=True)
    builder.writer.write(str(out))
    return builder.counts
