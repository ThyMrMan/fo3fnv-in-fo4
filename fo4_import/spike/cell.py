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
import time
from pathlib import Path

from fo4_import.base.ba2_pack import sound_root, staging_root
from fo4_import.spike.plugin_rename import drop_old_plugins, is_master, move_renamed, retarget_faces
from fo4_import.base.master_overrides import held_by, master_records
from fo4_import.base.source_ids import SourceIds, built_plugins, dependent_masters, key_light, master_ledgers
from fo4_import.base.ledger import ID, Ledger, LedgerWriter, ledger_path
from fo4_import.base.install import FALLOUT4_ESM, masters_of, source_esm, source_walk, use_source
from fo4_import.base.source import plugin_stem
from fo4_import.base.source_fault import without_fault
from fo4_import.base.support_records import pack_gmst
from fo4_import.base.writer import pack_fo4_record, pack_quest
from fo4_import.spike.consumables import Consumables
from fo4_import.casino.records import Casino
from fo4_import.spike.hardcore import Hardcore
from fo4_import.spike.creatures import Creatures
from fo4_import.spike.combat_styles import CombatStyles
from fo4_import.spike.combat_perk import combat_rules
from fo4_import.spike.equipment import Equipment
from fo4_import.spike.projectiles import Projectiles
from fo4_import.spike.destruction import Destruction
from fo4_import.spike.region_watch import RegionWatch
from fo4_import.spike.effect_shaders import EffectShaders
from fo4_import.spike.guns import turned
from fo4_import.spike.scol import PART_SITE, Parts, compose
from fo4_import.spike.emittance import Emittance
from fo4_import.spike.lighting_template import resolved
from fo4_import.spike.imagespace import BASE_IMAGESPACE, DISPLAY_GAMMA, cinematic, pack_imgs, write_lut
from fo4_import.spike.activators import Activators
from fo4_import.spike.actor_dialogue import ActorDialogue
from fo4_import.spike.crafting import Crafting
from fo4_import.spike.glow_cards import glow_cards
from fo4_import.spike.light_roles import ShadowLights
from fo4_import.spike.imposter_gate import ImposterGate
from fo4_import.spike import character, facegen, new_game, replacements, terrain_lod
from fo4_import.spike.attach import ObjectScripts
from fo4_import.spike.conversation import Conversations, Hub, hub, opener_forms, outside_lines
from fo4_import.spike.furniture import enter_motions, furniture, furniture_idles, markers
from fo4_import.spike.furniture_poses import FurniturePoses
from fo4_import.spike.navmesh import navi, navmeshes
from fo4_import.spike.exterior import Exterior
from fo4_import.spike.idles import Idles
from fo4_import.spike.imods import ImageSpaces
from fo4_import.spike.idle_markers import EMPTY, IdleMarkers
from fo4_import.spike.interiors import by_cell, scope
from fo4_import.spike.vendors import merchants, with_chests, write_vendors
from fo4_import.spike.conditions import use_actor_values
from fo4_import.spike.script import use_prefix
from fo4_import.spike.script_packages import PROPERTY as SCRIPT_PACKAGES, quest_id as script_packages_quest
from fo4_import.spike.patrol_topics import PatrolTopics
from fo4_import.spike.placement import map_markers, open_rooms, place, placement, starts_disabled
from fo4_import.spike.npcs import ACHR_KEY, NPC_KEY, Npcs
from fo4_import.spike.object_lod import ObjectLod
from fo4_import.spike.packages import Packages, beds
from fo4_import.spike.perks import Perks
from fo4_import.spike.type_tests import TypeKeywords
from fo4_import.spike.poses import Poses
from fo4_import.spike.sounds import Sounds, looping_sounds
from fo4_import.spike.swaps import Swaps
from fo4_import.spike.factions import write_all as write_factions
from fo4_import.spike.globals import write_all as write_globals
from fo4_import.spike.locations import Locations, encounter_zones
from fo4_import.spike.items import ENGINE_IDS, ITEM_TYPES, Items, index, shared_engine_ids
from fo4_import.spike import records as R
from fo4_import.spike import voice
from fo4_import.spike.dialogue import CELL_FO4
from fo4_import.spike.dialogue_trace import register as register_trace
from fo4_import.spike.say_topics import SayTopics, conditions_of, script_vars
from fo4_import.spike.quest import LISTENER_ALIAS, SPEAKER_ALIAS, objective_globals, quest_record, quest_var_globals
from fo4_import.base.vmad import quest_fragments
from fo4_import.spike.quest_scope import QuestScope
from fo4_import.spike.named_refs import named_markers
from fo4_import.spike.condition_forms import condition_map
from fo4_import.spike.locks import lock_vmad
from fo4_import.spike.readiness import Readiness
from fo4_import.spike.reputation import write_reputations
from fo4_import.spike.standings import Standings
from fo4_import.spike.challenges import Challenges
from fo4_import.spike.statics import prop_assets, tree_assets, write_assets
from fo4_import.spike.readables import Readables
from fo4_import.spike.decals import Decals
from fo4_import.spike.mines import Mines
from fo4_import.spike.music import AUDIO_MARKER, music_of
from fo4_import.spike.radiation import hazard_ref
from fo4_import.spike.radio import Radio, placements as radio_placements
from fo4_import.spike.talking_activators import Talkers
from fo4_import.spike.acoustics import AcousticSpaces
from fo4_import.spike.placeable_water import PlaceableWater
from fo4_import.pipeline.stage_timer import charged, timed
from fo4_import.spike.build_finish import VOICE_CACHE, finish
from fo4_import.pipeline import master_copies
from fo4_import.pipeline.light_choice import Choice
from fo4_import.pipeline.converters import PLACED, placed_types
from fo4_import.pipeline.export_index import (Layered, asset_root, export_file, export_records, held_types,
                                              own_records, plugin_sources)
from script_convert.constants import FALLOUT4_HELPER_PLUGIN
from script_convert.context_setup import load_records
from tes5_import.base.tes5_reader import first_sub, records, sub_map, walk
from tes5_import.base.writer import pack_subrecord
from tes5_import.dialogue.unlocks import build_unlock_plan

MASTERS = ['Fallout4.esm', FALLOUT4_HELPER_PLUGIN]
#: Master index of the helper plugin (FalloutHelpers.esl).
HELPER_INDEX = 1
#: The player's reference, the same FormID in both games.
PLAYER = 0x14
#: Started by hand (setstage FNV_VCG00 0 starts the rest), not with the game: they take the Pip-Boy, show tutorials.
HAND_STARTED = frozenset({'VCG00', 'VCG01', 'CGTutorial'})
#: Record key and EditorID of the generated quest holding the shared greeting (_greetings).
GREETINGS_KEY, GREETINGS_EDID = 'GREETINGS', 'Greetings'
#: FO4's shortest padded length of a voiced line (2.5 s), set to a silent line's (fo4_spikes.md#silent-line).
PADDED_SETTING = 'fDialoguePaddedAudioLengthMin'
#: The script closing a door behind the NPC that opened it (docs/fork/fo4_pipeline.md#door-closer).
DOOR_CLOSER = 'F3NV_DoorCloser'
#: derive_formid site of the statics made from FNV TREE records (key: the TREE's FormID).
TREE_SITE = 'FNV TREE'
#: FormID site of a load door's static copy of an FNV DOOR (CellBuilder.load_door).
LOAD_DOOR_SITE = 'FNV DOOR load'
#: FormID site of a dependent build's copy of a master's record its built plugin left out (key: the FNV FormID).
COPY_SITE = 'FNV master record copy'
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
    far distance only fog shows; other FO4-only fields keep `template`'s.
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
                 plugin_dirs: tuple = (), light: bool = False):
        """A builder writing assets into `data_dir`; `bases` is {FNV FormID: (type, record)}; `table` the
        replacement table (spike.replacements; its other plugins become masters, found in `plugin_dirs`);
        `light`: a light plugin (LedgerWriter.make_light)."""
        self.export_dir, self.data_dir, self.bases = export_dir, data_dir, bases
        self.table, self.plugin_dirs = table if table is not None else replacements.load(), plugin_dirs
        source_masters = masters_of(source_esm())
        self.built = built_plugins(source_masters, (data_dir, *plugin_dirs))
        self.masters = dependent_masters(self.built, replacements.extra_masters(self.table), MASTERS)
        self.writer = LedgerWriter(masters=self.masters, is_esm=False, description='FNV cell spike')
        self.ids = SourceIds(source_masters, self.masters, self.writer.own_index)
        self.top, self.owned = ENGINE_IDS, collections.Counter()
        self.fnv_types = {r.form_id: r.sig.decode() for r in (r for r, _ in source_walk(bodies=()))}
        if light:
            self.writer.make_light()
        else:
            self.writer.reserve_source_ids({self.ids.fo4(fid) for fid in self.fnv_types if self.ids.is_own(fid)})
        self.in_masters = held_by(self.built, self.masters) if self.built else None
        self.made, self.meshes, self.items, self.activators, self.scripts = {}, {}, None, None, None
        self.faulted = set()
        self.actor_ids, self.npc_ids, self.say, self.packages, self.objectives = {}, {}, None, None, {}
        self.quest_vars, self.actor_refs = {}, {}
        self.globals, self.factions, self.zones, self.places, self.regions = {}, {}, {}, {}, {}
        self.swaps, self.imods, self.poses, self.parts, self.weapons = None, None, None, None, set()
        self.equipment, self.load_doors, self.imagespaces = None, {}, set()
        self.weather_ids, self.weather_templates, self.weather_regions, self.acoustics = {}, {}, None, None
        self.world_imagespace, self.weather_imagespaces, self.built_worlds = 0, {}, frozenset()
        self.hazards, self.music, self.decals, self.perks, self.forms = None, None, None, None, {}
        self.radio, self.land_textures, self.region_watch = None, {}, None
        self.type_keywords = TypeKeywords(self.writer)
        self.started = time.time()
        self.fo4 = FALLOUT4_ESM.read_bytes()
        self.idle_markers = IdleMarkers(self.fo4)
        self.keywords = {(first_sub(r.body, b'EDID') or b'').rstrip(b'\0').decode(): r.form_id
                         for r, _ in walk(self.fo4, b'KYWD')}
        self.furniture_idles, self.readiness = furniture_idles(export_records(export_dir, 'IDLE')), Readiness()
        self.enter_motions = enter_motions(asset_root(export_dir, 'meshes'))
        self.counts, self.readables, self.mines, self.keyed = collections.Counter(), None, None, set()
        self.object_lod = ObjectLod(self)

    def fnv_id(self, fnv) -> int:
        """FormID of FNV record `fnv` (int or hex) made 1:1: its object id, in the FO4 plugin of the source plugin
        owning it (source_ids); a master's record its built plugin left out is this build's copy, hashed from its
        FNV FormID (COPY_SITE).
        See: docs/fork/fo4_plugin_layout.md#dlc
        """
        fid = int(fnv, 16) if isinstance(fnv, str) else fnv
        if self.ids.is_own(fid):
            self.top = max(self.top, (fid & 0xFFFFFF) + 1)
            return self.ids.fo4(fid)
        fo4 = self.ids.held(fid)
        if self.in_masters is None or fo4 in self.in_masters:
            return fo4
        return self.writer.derive_formid(COPY_SITE, f'{fid:08X}')

    def new_id(self, owner: str, key: 'str | None' = None) -> int:
        """A generated record's FormID: hashed from its authored `key`, or from its `owner` (FNV data) and count.
        A key keeps the id its owner and count gave until the ledger holds it; two records keyed alike raise.

        See: docs/fork/fo4_pipeline.md#formid-ledger
        """
        n = self.owned[owner]
        self.owned[owner] += 1
        counted = f'{owner} {n}' if n else owner
        if key is None:
            self.counts['FormIDs from a counted key'] += bool(n)
            return self.writer.derive_formid(MADE_SITE, counted)
        if key in self.keyed:
            raise ValueError(f'two generated records keyed {key!r}')
        self.keyed.add(key)
        return self.writer.derive_formid(MADE_SITE, key, legacy=counted)

    def first_id(self, owner: str) -> int:
        """The FormID new_id(owner) gives first, not taken."""
        return self.writer.derive_formid(MADE_SITE, owner)

    def _asset(self, key: str, make, *args, **kwargs) -> tuple:
        """meshes[`key`], made once by make(*args, **kwargs); ('', None), the record left without the model, for
        one with a source fault (counted once).
        See: docs/fork/fo4_build_speed.md#faults
        """
        if key not in self.meshes and key not in self.faulted:
            made = without_fault(make, *args, **kwargs)
            if made is None:
                self.faulted.add(key)
                self.counts['models left out (a source fault)'] += 1
            else:
                self.meshes[key] = made
        return self.meshes.get(key, ('', None))

    def mesh(self, model: str) -> tuple:
        """(FO4 model path, bounds) of an FNV model, converted once (_asset)."""
        return self._asset(model, write_assets, self.export_dir, model, self.data_dir)

    def weapon_mesh(self, model: str, pose: dict) -> tuple:
        """mesh() of an FNV weapon model in its held `pose` as its own `<name>_weapon.nif`, dressed as a weapon after
        Elric (nif.weapon); the model placed as a static keeps its own file."""
        made = self._asset(f'{model}#weapon', write_assets, self.export_dir, model, self.data_dir, pose,
                           animated=False, suffix='_weapon')
        self.weapons.update({made[0]} - {''})
        return made

    def prop_mesh(self, model: str, pose: dict, bone: str) -> tuple:
        """mesh() of an FNV idle prop in `pose` hung from `bone` (prop_assets)."""
        return self._asset(f'{model}#prop', prop_assets, self.export_dir, model, self.data_dir, pose, bone)

    def base(self, fnv_fid: int) -> 'int | None':
        """The FO4 base for an FNV base FormID, made once by its type's converter (pipeline.converters.PLACED);
        None: not converted. While it is made, its own script naming it reads its FNV-derived FormID.
        See: docs/fork/fo4_pipeline.md#base-properties
        """
        if fnv_fid < ENGINE_IDS:
            return self.items.shared.get(fnv_fid)
        if fnv_fid not in self.made:
            sig, rec = self.bases.get(fnv_fid) or self._item_base(fnv_fid)
            self.made[fnv_fid] = self.fnv_id(fnv_fid)
            self.made[fnv_fid] = charged(f'base {sig}', getattr(self, PLACED[sig]), fnv_fid, sig, rec) \
                if sig in PLACED else None
        return self.made[fnv_fid]

    def _item_base(self, fnv_fid: int) -> tuple:
        """(type, record) of an FNV item base items.item() makes; (None, None) if not."""
        found = self.items.records.get(fnv_fid, (None, None))
        return found if found[0] in placed_types('item') else (None, None)

    def item(self, fnv_fid: int, _sig, _rec) -> 'int | None':
        """Converter: an FNV misc item or container as itself (spike.items)."""
        return self.items.item(fnv_fid)

    def idle(self, fnv_fid: int, _sig, rec: dict) -> 'int | None':
        """Converter: idle marker `rec`'s vanilla stand-in, else the empty marker."""
        made, plays = self.idle_markers.of(rec)
        self.counts['idle marker placed' if made else f'idle marker placed empty: {plays}'] += 1
        return made or self.idle_markers.vanilla[EMPTY]

    def sound(self, fnv_fid: int, _sig, _rec) -> int:
        """Converter: an FNV sound marker (spike.sounds)."""
        return self.sounds.marker(fnv_fid)

    def water(self, fnv_fid: int, _sig, rec: dict) -> int:
        """Converter: an FNV placeable water's FO4 tile activator (placeable_water)."""
        return self.placeable_water.record(self.fnv_id(fnv_fid), rec)

    def decal(self, fnv_fid: int, _sig, rec: dict) -> int:
        """Converter: an FNV decal texture set (spike.decals)."""
        self.decals = self.decals or Decals(self)
        return self.decals.record(self.fnv_id(fnv_fid), rec)

    def mine(self, fnv_fid: int, _sig, _rec) -> 'int | None':
        """Converter: a placed FNV mine's projectile as FO4's (spike.mines)."""
        self.mines = self.mines or Mines(self, self.export_dir)
        return self.mines.projectile(fnv_fid)

    def transmitter(self, fnv_fid: int, _sig, rec: dict) -> 'int | None':
        """Converter: a talking activator (spike.talking_activators), or a Pip-Boy station's transmitter
        (spike.radio), else None."""
        return self.talkers.base(fnv_fid, rec) or self.radio.base(fnv_fid, rec)

    def readable(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """Converter: an FNV book, note or terminal (spike.readables)."""
        self.readables = self.readables or Readables(self)
        return self.readables.base(fnv_fid, sig, rec)

    def record(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """Converter: `rec`'s FO4 record (_make); None for no mesh, light or script, or a model no export layer
        holds (counted: Classic Pack's statics name mod-variant meshes FNV never shipped) or with a source fault; a
        light or activator with such a model is made without it (Honest Hearts' hot plate wears Dead Money's)."""
        lost = self._lost(world_model(rec)) if world_model(rec) else ''
        if lost:
            kept = sig in ('LIGH', 'ACTI')
            self.counts[f'{sig} {"made without" if kept else "left out for"} its mesh ({lost})'] += 1
            rec = {k: v for k, v in rec.items() if k != 'Model.MODL'} if kept else None
        if rec is None:
            return None
        return self._make(sig, rec, self.fnv_id(fnv_fid)) if sig in ('LIGH', 'ACTI') or world_model(rec) else None

    def _lost(self, model: str) -> str:
        """Why FNV `model` cannot be placed ('' when mesh() made it)."""
        if not export_file(self.export_dir, 'meshes', model.replace('/', '\\').lower()).is_file():
            return 'in no archive'
        return '' if self.mesh(model)[0] else 'a source fault'

    def tree(self, fnv_fid: int, _sig, rec: dict) -> int:
        """Converter: the FO4 static for FNV TREE `rec`, its mesh generated from its SpeedTree and its billboard
        as object LOD (ObjectLod.tree); FormID hashed from FNV's."""
        fid = self.writer.derive_formid(TREE_SITE, f'{fnv_fid:08X}')
        model, bounds = self.meshes[world_model(rec)] = tree_assets(self.export_dir, rec, self.data_dir)
        edid = f'FNV_{rec["EditorID"]}'
        lod = self.object_lod.tree(fid, rec, edid, model)
        self.writer.add_record('STAT', R.pack_stat(fid, edid, model, bounds or _bounds(rec), *lod))
        self.counts['TREE'] += 1
        return fid

    def pickup(self, fnv_fid: int, sig: str, rec: dict) -> 'int | None':
        """Converter: the FO4 item for placed FNV item `rec`; without one, its static (FNV's FormID)."""
        item = self.items.item(fnv_fid)
        if item is not None or not world_model(rec):
            return item
        return self._make(sig, rec, self.fnv_id(fnv_fid))

    def _make(self, sig: str, rec: dict, fid: int) -> int:
        """Write the FO4 record for FNV base `rec` of type `sig` on FormID `fid`; its FormID. FNV furniture whose
        mesh has no markers, which nothing can use, is a static."""
        edid = f'FNV_{rec["EditorID"]}'
        model, bounds = self.mesh(world_model(rec)) if world_model(rec) else ('', None)
        bounds = bounds or _bounds(rec)
        if sig == 'LIGH':
            record = R.pack_ligh(fid, edid, _bounds(rec), model, light_data(rec), float(rec.get('FNAM.Fade', 1.0)),
                                 self.sounds.field(rec, 'SNAM.Sound'))
            self.shadows.add(rec, record)
        elif sig == 'FURN' and (marks := markers(str(export_file(self.export_dir, 'meshes',
                                                                 world_model(rec).replace('/', '\\').lower())))):
            record = furniture(fid, rec, model, bounds, marks, self.keywords,
                               self.furniture_idles.get(rec['FormID'].upper(), ()), self.enter_motions,
                               self.scripts.vmad(int(rec.get('SCRI', '0'), 16)), self.furniture_poses)
        elif sig == 'ACTI':
            sig, record = self._activator(fid, rec, model, bounds)
        elif sig == 'DOOR':
            record = self._door(fid, edid, rec, (model, bounds))
        else:
            loop = self.sounds.descriptor(looping_sounds().get(int(rec['FormID'], 16), 0))
            lod = self.object_lod.stat(fid, rec, edid, model) if sig == 'STAT' and not loop else (0, ())
            sig, record = _static(sig, fid, edid, model, bounds, loop, lod, self.destruction.of(int(rec['FormID'], 16)))
        self.writer.add_record(sig, record)
        self.counts[sig] += 1
        return fid

    def _activator(self, fid: int, rec: dict, model: str, bounds: tuple) -> tuple:
        """(signature, record) of FNV activator `rec`: a crafting station, a static when it only loops its mesh
        (Activators.ambient), else an ACTI."""
        if self.crafting.station_of(rec):
            return 'FURN', self.crafting.station(fid, rec, model, bounds)
        dest = self.destruction.of(int(rec['FormID'], 16))
        if self.activators.ambient(rec, world_model(rec)):
            return _static('STAT', fid, f'FNV_{rec["EditorID"]}', model, bounds, self.sounds.field(rec, 'SNAM'),
                           dest=dest)
        return 'ACTI', self.activators.record(fid, rec, model, bounds, dest)

    def _door(self, fid: int, edid: str, rec: dict, mesh: tuple) -> bytes:
        """FNV DOOR `rec` on `fid`, `mesh` (model, bounds); its script, DOOR_CLOSER."""
        vmad = self.scripts.vmad(int(rec.get('SCRI', '0'), 16), ((DOOR_CLOSER, {}, {}),))
        return R.pack_door(fid, edid, rec.get('FULL', ''), *mesh, int(rec.get('FNAM.Flags', 0)), vmad,
                           tuple(self.sounds.field(rec, key) for key in ('SNAM.Open', 'ANAM.Close', 'BNAM.Loop')))

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


def _static(sig: str, fid: int, edid: str, model: str, bounds: tuple, loop: int = 0, lod: tuple = (0, ()),
            dest: bytes = b'') -> tuple:
    """(type, record): MSTT for an MSTT, `loop` or destruction subrecords `dest`, else STAT with `lod` (flags,
    MNAM)."""
    if sig == 'MSTT' or loop or dest:
        return 'MSTT', R.pack_mstt(fid, edid, model, bounds, loop, dest)
    return 'STAT', R.pack_stat(fid, edid, model, bounds, *lod)


def find_cell(export_dir: Path, edid: str) -> dict:
    """The FNV interior CELL record with EditorID `edid`."""
    for rec in export_records(export_dir, 'CELL'):
        if rec.get('EditorID') == edid:
            return rec
    raise SystemExit(f'no CELL {edid}')


def placed_bases(export_dir: Path, used: set) -> dict:
    """{FNV FormID: (type, record)} of the used bases this spike converts (items are found through _item_base)."""
    out = {}
    for sig in (s for s in placed_types() if PLACED[s] != 'item'):
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


@timed('doors')
def _teleports(builder: CellBuilder, scoped: tuple, links: dict, ids: dict, chest) -> tuple:
    """(QASmoke's REFRs, {door ref: its teleport}) of the build's doors: `scoped` (interior, exterior references),
    each leading to its partner when built (`ids`). With the test chest's template `chest`, an interior door whose
    partner is not built leads to a QASmoke stand-in (_doors) and QASmoke gets the chest; without it, such a door
    keeps no teleport. Doors leading out of the build are counted."""
    inner, outer = ([r for r in refs if 'XTEL.Door' in r] for refs in scoped)
    qa_refs, teleports = _doors(builder, inner, links, ids) if chest is not None else (b'', _linked(inner, ids))
    qa_refs += _test_chest(builder, chest) if chest is not None else b''
    teleports.update(_linked(outer, ids))
    builder.counts['doors leading out of the build'] = sum(1 for r in inner + outer if r['XTEL.Door'] not in ids)
    return qa_refs, teleports


def _test_chest(builder: CellBuilder, template) -> bytes:
    """QASmoke's test chest (vanilla QA chests' footlocker) with every converted weapon and armor piece; its REFR."""
    subs = sub_map(template.body)
    fid = builder.writer.derive_formid(TEST_SITE, 'CONT')
    builder.writer.add_record('CONT', R.pack_cont(
        fid, 'FNV_TestChest', 'FNV test chest', subs[b'MODL'].rstrip(b'\0').decode(),
        struct.unpack('<6h', subs[b'OBND']), builder.equipment.test_items(TEST_ROUNDS)
        + builder.equipment.ammo_mods.test_items(TEST_ROUNDS), 0, 0.0))
    return R.pack_refr(builder.writer.derive_formid(TEST_SITE, 'REFR'), fid, TEST_CHEST_POS, (0.0, 0.0, 0.0))


def _built(builder: CellBuilder, refs: list) -> list:
    """The references _placed() writes as themselves, the only ones linked to.
    See: docs/fork/fo4_pipeline.md#audit
    """
    return [r for r in refs if int(r['NAME'], 16) not in builder.parts.parts
            and builder.base(int(r['NAME'], 16)) is not None and int(r['FormID'], 16) not in open_rooms()]


@timed('references')
def _ref_ids(builder: CellBuilder, refs: list) -> dict:
    """{FNV reference: FO4 FormID} of `refs` _placed() writes."""
    return {r['FormID']: builder.fnv_id(r['FormID']) for r in _built(builder, refs)}


@timed('placed references')
def _placed(builder: CellBuilder, refs: list, ids: dict, teleports: dict) -> tuple:
    """(persistent, temporary) REFRs of the cell's converted references."""
    persistent, temporary, owners = b'', b'', {**builder.factions, **builder.npc_ids}
    shadowed = builder.shadows.chosen(refs)
    for ref in refs:
        base = (builder.load_door if ref['FormID'] in teleports else builder.base)(int(ref['NAME'], 16))
        hazard = hazard_ref(builder, ref, _persistent(ref))
        persistent, temporary = (persistent + hazard, temporary) if _persistent(ref) else (persistent, temporary + hazard)
        if int(ref['NAME'], 16) in builder.parts.parts:
            parts = _part_refs(builder, ref)
            persistent, temporary = (persistent + parts, temporary) if _persistent(ref) else (persistent, temporary + parts)
            continue
        if base is None:
            builder.counts[f'skipped {_base_type(builder, int(ref["NAME"], 16))}'] += 1
            continue
        base = builder.shadows.base_of(ref, builder.crafting.base_of(ref, base), shadowed)
        if int(ref['FormID'], 16) in open_rooms():
            builder.counts['rooms and portals left out (a portal to no room)'] += 1
            continue
        fnv_ref = int(ref['FormID'], 16)
        keep, card = _persistent(ref) or ref['FormID'] in teleports, fnv_ref in glow_cards(builder.export_dir)
        gated = card and builder.imposter_gate.gated(fnv_ref)
        radius = float(ref['XRDS.Radius']) if 'XRDS.Radius' in ref and builder.bases.get(
            int(ref['NAME'], 16), ('',))[0] == 'LIGH' else None
        record = R.pack_refr(ids[ref['FormID']], base, *_placed_at(builder, ref), float(ref.get('XSCL.Scale', 1.0)), radius,
                             teleports.get(ref['FormID']), keep, placement(int(ref['FormID'], 16), builder.ref_ids, owners,
                                                                           arrivals=builder.patrols.arrivals) + _lock(builder, ref)
                             + builder.emittance.xemi(ref) + builder.radio.xrdo(ref),
                             starts_disabled(ref, builder.ref_ids) or gated,
                             builder.ref_ids.get(ref.get('XLKR.LinkedRef'), 0),
                             door_link=builder.door_links.get(ids[ref['FormID']]), sig=ref['Signature'], vmad=lock_vmad(builder, ref),
                             full_lod=card)
        persistent, temporary = (persistent + record, temporary) if keep else (persistent, temporary + record)
        if gated:
            builder.imposter_gate.add(fnv_ref, ids[ref['FormID']])
        builder.object_lod.add(record, int(ref['RecordFlags']))
        builder.counts['placed'] += 1
    return persistent, temporary


def _base_type(builder: CellBuilder, fnv: int) -> str:
    """FNV base `fnv`'s record type; audio markers and engine forms named."""
    if fnv == AUDIO_MARKER:
        return 'audio marker (built as a music region)'
    return builder.fnv_types.get(fnv, f'engine form {fnv:08X}' if fnv < ENGINE_IDS else 'missing base')


def _placed_at(builder: CellBuilder, ref: dict) -> tuple:
    """(position, rotation) of FNV reference `ref`; a terminal's heading takes back its mesh's turn (Terminals.turn;
    a tilted one, counted, only about Z), a converted gun its mesh's (guns.turned).
    See: docs/fork/fo4_spikes.md#placed-guns
    """
    pos, rot = place(ref)
    readables = getattr(builder, 'readables', None)
    turn = readables.terminals.turn(ref) if readables else 0.0
    builder.counts['terminal tilted, turned about Z only'] += bool(turn and (rot[0] or rot[1]))
    fnv, equipment = int(ref['NAME'], 16), getattr(builder, 'equipment', None)
    if equipment is None or fnv not in equipment.weapon_ammo:
        return pos, (rot[0], rot[1], rot[2] + turn)
    builder.counts['placed guns turned as their mesh'] += 1
    return turned(pos, rot, float(ref.get('XSCL.Scale', 1.0)), equipment.guns.turn(fnv))


def _lock(builder: CellBuilder, ref: dict) -> bytes:
    """The XLOC of a locked FNV reference (level, its key as a FO4 KEYM, flags), or of a terminal its base locks
    (spike.readables); b'' when it has no lock.

    FO4 numbers lock levels as FNV does (0, 25, 50, 75, 100; 255 requires the key).
    See: docs/fork/fo4_pipeline.md#locks
    """
    if 'XLOC.Level' not in ref:
        readables = getattr(builder, 'readables', None)
        return readables.lock(ref) if readables else b''
    fnv_key = int(ref.get('XLOC.Key', '0'), 16)
    key = (builder.items.item(fnv_key) or 0) if fnv_key else 0
    builder.counts['locked references'] += 1
    return pack_subrecord('XLOC', struct.pack('<B3xIB3xI', int(ref['XLOC.Level']), key, int(ref.get('XLOC.Flags', 0)), 0))


def _persistent(ref: dict) -> bool:
    """Whether FNV reference `ref` is flagged persistent."""
    return bool(int(ref['RecordFlags']) & 0x400)


def _part_refs(builder: CellBuilder, ref: dict) -> bytes:
    """The REFRs of FNV SCOL reference `ref`'s parts, on hashed FormIDs (scol.PART_SITE), persistent as `ref` is."""
    position, angle = place(ref)
    scale, out = float(ref.get('XSCL.Scale', 1.0)), b''
    disabled = starts_disabled(ref, builder.ref_ids)
    for index, (part, placement) in enumerate(builder.parts.parts[int(ref['NAME'], 16)]):
        base = builder.base(part)
        if base is None:
            builder.counts['SCOL part skipped'] += 1
            continue
        at, turn, size = compose(position, angle, scale, placement)
        fid = builder.writer.derive_formid(PART_SITE, (ref['FormID'], index))
        record = R.pack_refr(fid, base, at, turn, size, persistent=_persistent(ref), disabled=disabled)
        builder.object_lod.add(record, int(ref['RecordFlags']))
        out += record
        builder.counts['SCOL parts placed'] += 1
    builder.counts['SCOL references split'] += 1
    return out


@timed('vanilla records')
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
        lut = write_lut(cinematic(bytes.fromhex(fnv['DNAM'])), fnv['EditorID'], builder.data_dir)
        builder.writer.add_record('IMGS', pack_imgs(fid, f'FNV_{fnv["EditorID"]}', base_body, lut))
        builder.imagespaces.add(fid)
        builder.counts[f'imagespace: {fnv["EditorID"]}'] += 1
    return fid


@timed('navmesh')
def _navmesh(builder: CellBuilder, export_dir: Path, pathing: dict, ids: dict) -> dict:
    """{FNV cell: FO4 NAVM records} of the FNV navmeshes in `pathing`'s cells, linked and registered in NAVI;
    each door's navmesh triangle in `builder.door_links`."""
    recs = [r for r in export_records(export_dir, 'NAVM') if r.get('DATA.Cell') in pathing]
    records, infos, builder.door_links = navmeshes(recs, pathing, ids, builder.fnv_id)
    if infos:
        builder.writer.add_record('NAVI', navi(builder.fo4, infos))
        builder.counts['NAVM'] += len(recs)
    return records


@timed('form map')
def _form_map(builder: CellBuilder, ref_ids: dict, recs: list, quests: dict) -> dict:
    """FNV to FO4 forms: references and placed actors, quests, player, objectives, globals, factions, reputations,
    the packages written."""
    packages = {int(k, 16): v for k, v in builder.packages.made.items() if v} if builder.packages else {}
    return {**builder.globals, **builder.factions, **builder.actor_refs, **{int(k, 16): v for k, v in ref_ids.items()},
            **packages, PLAYER: PLAYER,
            **builder.objectives, **builder.quest_vars, **builder.reputation_slots, **builder.hardcore.form_map(),
            **builder.casino.form_map(),
            **{int(r['FormID'], 16): quests[r['EditorID']] for r in recs}}


@timed('quests')
def _quests(builder: CellBuilder, export_dir: Path, recs: list, quests: dict, ref_ids: dict) -> None:
    """Write FNV quests `recs` (FO4 ids in `quests`) with their lines; `ref_ids` maps FNV references.

    A line's conditions see the cell's references, actors' bases, these
    quests, the player, actor values and the items FO4 shares or stands in. Conversations are built once every script's
    `TES4Talk_<topic>` scene is known; they share one Hub (every quest's lines
    and topic list), the greeting goes to its own quest (_greetings), NPC-to-NPC chats to ADIA quests.
    """
    say = builder.say
    lines = [line for rec in recs for line in say.infos.get(rec['FormID'].upper(), [])]
    form_map = condition_map(builder, _form_map(builder, ref_ids, recs, quests),
                             [*lines, *builder.idles.ambient_records()], HELPER_INDEX)
    form_map.update(builder.talkers.form_map(form_map))
    builder.idles.form_map = builder.forms = form_map
    shared = _hub(builder, export_dir, say, recs, quests, form_map)
    done = []
    for rec in recs:
        fid = quests[rec['EditorID']]
        topics = {dial: builder.new_id(f'DIAL {rec["FormID"]} {dial}') for dial in say.topics(rec)}
        builder.scripts.named.update({say.dials[d]['EditorID']: t for d, t in topics.items()})
        branch, blobs = say.build(rec, fid, topics, form_map) if topics else (None, [])
        talks = Conversations(say, rec, fid, form_map, shared)
        radio = builder.radio.program(rec, fid, form_map, ref_ids) or ((), [], [], ())
        done.append((fid, rec, [branch] if branch else [], blobs + radio[1], talks, radio))
    builder.packages.named_by_quests(builder.scripts, recs)
    records = [quest_record(fid, rec, builder.scripts, ref_ids, talks.has_lines(),
                            rec['EditorID'] not in HAND_STARTED, radio[0], radio[3])
               for fid, rec, _branches, _blobs, talks, radio in done]
    built, pending = _greetings(builder, say, form_map, shared)
    for (fid, rec, branches, blobs, talks, radio), record in zip(done, records):
        built |= {prop for prop, scene in list(builder.scripts.talks.items())
                  if prop not in built and talks.talk(prop, scene)}
        builder.writer.add_record('QUST', pack_quest(record, fid, branches, blobs + talks.topics,
                                                     talks.scenes + radio[2]))
        builder.counts['QUST'] += 1
        builder.counts['SCEN'] += len(talks.scenes)
    for prop in set(builder.scripts.talks) - built:
        builder.counts[f'{prop}: no lines in the cell quests'] += 1
    ActorDialogue(builder, say, form_map, shared).write()
    for quest, topics, scenes in pending:
        _greetings_quest(builder, quest, max((p for _, p in shared.quests.values()), default=0), topics, scenes)
    builder.counts['SCEN'] += len(shared.home.scenes)
    builder.patrols.write()
    if say.once.stages:
        builder.writer.add_record('QUST', say.once.record())
        builder.counts['Say Once markers'] = len(say.once.stages)
    builder.talkers.write(form_map)


def _hub(builder: CellBuilder, export_dir: Path, say: SayTopics, recs: list, quests: dict, form_map: dict) -> Hub:
    """The cell quests' Hub, listing only topics with a line whose conditions convert; a topic an AddTopic
    reveals is gated on the unlock global the scripts set, as the script converter's unlock plan names it."""
    plan = build_unlock_plan(load_records(str(export_dir), ('DIAL', 'INFO', 'QUST', 'SCPT')))
    shared = hub(say, recs, quests, plan['added'])
    shared.outside, shared.outside_topics = outside_lines(say, shared.lines)
    shared.topics = tuple(d for d in shared.topics if any(
        r['ParentDIAL'].upper() == d and conditions_of(r, form_map, say.script_vars) is not None
        for r in shared.lines.values()))
    shared.gates = {d: builder.scripts.global_(plan['gated'][int(d, 16) & 0xFFFFFF]) for d in shared.topics
                    if int(d, 16) & 0xFFFFFF in plan['gated']}
    builder.counts['topics listed'] = len(shared.topics)
    return shared


def _all_talks(found: dict, talks) -> set:
    """The `TES4Talk_<topic>` properties of `found` ({property: scene}) that Conversations `talks` built, including
    those a built scene's own scripts add to `found` while it is built."""
    done, built = set(), set()
    while todo := [(prop, scene) for prop, scene in list(found.items()) if prop not in done]:
        for prop, scene in todo:
            done.add(prop)
            built |= {prop} if talks.talk(prop, scene) else set()
    return built


def _greetings(builder: CellBuilder, say: SayTopics, form_map: dict, shared: Hub) -> tuple:
    """Build the generated, start-game quest holding the greeting every built quest's GREETING lines share, and
    every step any quest reaches (Hub.home); (the `TES4Talk_<topic>` scenes it built, [(quest, topics, scenes)]
    to write once every quest is built, at the built quests' highest priority).

    Its FormID and record keys come from GREETINGS_KEY, never from a built
    quest, so adding quests to the build moves none of them.
    See: docs/fork/fo4_pipeline.md#quest-scope
    """
    fid = builder.new_id(f'QUST {GREETINGS_KEY}')
    talks = shared.home = Conversations(say, {'FormID': GREETINGS_KEY, 'EditorID': GREETINGS_EDID}, fid, form_map,
                                        shared)
    built = _all_talks(builder.scripts.talks, talks)
    home = _opener_home(builder, fid)
    opener = talks.greeting(builder.packages.greets, builder.packages.topics, builder.packages.once.write_list(), home)
    talks.topics += [opener] if opener and not home else []
    talks.player_hello()
    builder.writer.add_record('GMST', pack_gmst(builder.new_id(f'GMST {PADDED_SETTING}'), PADDED_SETTING,
                                                voice.SILENT_SECONDS))
    register_trace(builder.scripts)
    return built, [((fid, GREETINGS_EDID), talks.topics, talks.scenes)] + ([((home[0], home[2]), [opener], [])]
                                                                          if opener and home else [])


def _greetings_quest(builder: CellBuilder, quest: tuple, priority: int, topics: list, scenes: list) -> None:
    """Write start-game quest `quest` (FormID, EditorID) with its talk aliases."""
    aliases = [(SPEAKER_ALIAS, 'Speaker', None), (LISTENER_ALIAS, 'Listener', None)]
    record = R.pack_fnv_quest(quest[0], f'FNV_{quest[1]}', '', priority, quest_fragments('', []), [], [], aliases, True)
    builder.writer.add_record('QUST', pack_quest(record, quest[0], [], topics, scenes))


def _opener_home(builder: CellBuilder, shared: int) -> 'tuple | None':
    """None when greetings quest `shared` is the build's own; else its own start-game quest for the greeting
    opener (FormID, key, EditorID, the speakers the masters' opener already names), since that one names only
    the masters' speakers.
    See: docs/fork/fo4_plugin_layout.md#dlc-greeting
    """
    if shared >> 24 == builder.writer.own_index:
        return None
    theirs = builder.writer.from_master(MADE_SITE, f'INFO greeting {GREETINGS_KEY}')
    found = master_records(builder.built, {theirs: b'INFO'}, builder.masters) if theirs else {}
    skip = opener_forms(found[theirs][1]) if theirs in found else frozenset()
    key = f'{GREETINGS_KEY} {plugin_stem(builder.export_dir)}'
    return builder.new_id(f'QUST {key}'), key, f'{GREETINGS_EDID}_{plugin_stem(builder.export_dir)}', skip


@timed('makers')
def _object_makers(builder: CellBuilder, export_dir: Path, scripts_dir: 'Path | None', refs: list,
                   every: list) -> None:
    """Give `builder` its item, activator and package makers; `refs` are the cell's FNV references, `every` all
    the build's (packages sit in their seats)."""
    builder.sounds, builder.globals = Sounds(builder, export_dir), write_globals(builder, export_dir)
    builder.shadows, builder.imposter_gate = ShadowLights(builder, export_dir), ImposterGate(builder)
    builder.factions, builder.faction_names = write_factions(builder, export_dir)
    builder.script_vars = script_vars(export_dir)
    records = index(export_dir, ITEM_TYPES)
    builder.perks, (builder.criticals, builder.combat) = Perks(builder, export_dir, HELPER_INDEX), combat_rules(
        builder, HELPER_INDEX)
    builder.projectiles, builder.effect_shaders = Projectiles(builder), EffectShaders(builder)
    builder.destruction = Destruction(builder)
    builder.hardcore, builder.casino = Hardcore(builder, export_dir, HELPER_INDEX), Casino(builder, export_dir)
    builder.consumables, builder.equipment = Consumables(builder, HELPER_INDEX), Equipment(builder)
    consumables, equipment = builder.consumables, builder.equipment
    makers = {'ALCH': consumables.alch, 'AMMO': consumables.ammo, 'WEAP': equipment.weap, 'ARMO': equipment.armo,
              'IMOD': equipment.weapon_mods.loose}
    stand_ins = replacements.items(builder.table, builder.fo4, builder.masters, builder.plugin_dirs)
    builder.items = Items(builder, records, shared_engine_ids(builder.fo4, {**builder.bases, **records},
                                                              SHARED_TYPES), makers, stand_ins)
    builder.scripts = ObjectScripts(builder, export_dir, _script_dirs(builder, scripts_dir), HELPER_INDEX)
    builder.scripts.named[SCRIPT_PACKAGES] = script_packages_quest(builder)
    reputations, builder.reputation_slots = write_reputations(builder, export_dir)
    builder.challenges = Challenges(builder, export_dir)
    builder.scripts.named.update({**reputations, **builder.perks.named(), **builder.challenges.named(),
                                  **builder.hardcore.named(), **builder.casino.named()})
    builder.activators, builder.crafting = Activators(builder, export_dir), Crafting(builder, export_dir, HELPER_INDEX, every)
    builder.radio, builder.talkers = Radio(builder, export_dir), Talkers(builder, export_dir)
    builder.region_watch = RegionWatch(builder, export_dir)
    builder.patrols = PatrolTopics(builder, export_dir)
    builder.combat_styles = CombatStyles(builder, export_dir)
    builder.creatures = Creatures(builder, export_dir, builder.data_dir)
    seats = [r for r in every if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN']
    builder.packages = Packages(builder, export_dir, {int(r['FormID'], 16) for r in seats}, beds(builder, seats),
                                every, HELPER_INDEX)
    builder.swaps = Swaps(builder, export_dir, {r['EditorID'].lower(): world_model(builder.bases[int(r['NAME'], 16)][1])
                                                for r in every if r.get('EditorID') and int(r['NAME'], 16) in builder.bases})
    builder.imods = ImageSpaces(builder)
    furniture = [(place(r), str(export_file(export_dir, 'meshes', world_model(builder.bases[int(r['NAME'], 16)][1]).lower())))
                 for r in refs if builder.bases.get(int(r['NAME'], 16), ('',))[0] == 'FURN']
    builder.poses = Poses(builder, {r['EditorID']: place(r) for r in refs if r.get('EditorID')}, furniture)
    builder.idles = Idles(builder, export_dir)
    builder.furniture_poses = FurniturePoses(builder, export_dir)


@timed('quest scope')
def _cell_quests(builder: CellBuilder, export_dir: Path, refs: list, cell_of, cells: dict) -> tuple:
    """(the build's quest records (quest_scope), {EditorID: FO4 FormID}); before any base's script is filled,
    the scripts learn by name the quests, their scripted topics, factions, objective globals, `refs` whose base
    converts (items and containers too), the actors in built cells (`cell_of`) and their NPC bases, and the built
    `cells`."""
    placed_actors = [r for sig in ('ACHR', 'ACRE') for r in export_records(export_dir, sig) if cell_of(r)]
    held = {int(r['FormID'], 16) for r in own_records(export_dir, 'QUST')} if builder.built else set()
    quest_recs = QuestScope(export_dir, builder.scripts.dir).included(builder.bases, refs, placed_actors, held)
    builder.counts['QUST in the build'] = len(quest_recs)
    quests = {r['EditorID']: builder.fnv_id(r['FormID']) for r in quest_recs}
    converts = builder.bases.keys() | {int(r['FormID'], 16) for sig in placed_types('item')
                                       for r in export_records(export_dir, sig)}
    placed = {r['EditorID']: builder.fnv_id(r['FormID']) for r in refs if r.get('EditorID')
              and int(r['NAME'], 16) in converts and int(r['NAME'], 16) not in builder.parts.parts}
    builder.actor_refs = {int(r['FormID'], 16): builder.first_id(ACHR_KEY.format(r['FormID'])) for r in placed_actors}
    builder.actor_refs.update({int(r['NAME'], 16): builder.first_id(NPC_KEY.format(int(r['NAME'], 16)))
                               for r in placed_actors if r['Signature'] == 'ACHR'})
    actors = {r['EditorID']: builder.actor_refs[int(r['FormID'], 16)] for r in placed_actors if r.get('EditorID')}
    actors.update({r['EditorID']: builder.actor_refs[int(r['FormID'], 16)] for r in export_records(export_dir, 'NPC_')
                   if r.get('EditorID') and int(r['FormID'], 16) in builder.actor_refs})
    say = builder.say = SayTopics(builder, export_dir)
    topics = {say.dials[d]['EditorID']: builder.first_id(f'DIAL {r["FormID"]} {d}') for r in quest_recs
              for d in say.topics(r)}
    builder.scripts.named.update({**cells, **placed, **actors, **builder.faction_names, **topics, **quests})
    builder.objectives = objective_globals(builder, quest_recs)
    builder.quest_vars = quest_var_globals(builder, export_dir, quest_recs)
    return quest_recs, quests


@timed('rest of the build')
def build(export_dir: Path, out: Path, data_dir: Path, cell_edid: str,
          scripts_dir: 'Path | None' = None, exteriors: tuple = (), table: 'dict | None' = None,
          plugin_dirs: tuple = (), test_cell: bool = True, light: Choice = Choice()) -> collections.Counter:
    """Write the plugin and assets for the FNV interior cell `cell_edid` (None: none, a DLC of held content
    only); counts of what was made.

    `scripts_dir` holds the converted scripts. `exteriors` lists (worldspace, (x, y) low, (x, y) high), that
    rectangle of its cells (None, None: all). Every interior a door leads into is built too. `table` is the
    replacement table, its plugins in `plugin_dirs`; `test_cell` adds QASmoke's test chest and stand-in doors;
    `light`: light_choice.
    """
    sources = plugin_sources(export_dir)
    use_source(sources[0][0], sources[1:])
    use_prefix(export_dir)
    use_actor_values(export_dir)
    cell = find_cell(export_dir, cell_edid) if cell_edid else None
    all_refs = export_records(export_dir, 'REFR') + export_records(export_dir, 'PGRE')
    refs = [r for r in all_refs if cell and r.get('ParentCELL') == cell['FormID']]
    links = {r['FormID']: r for r in all_refs if 'XTEL.Door' in r}
    worlds = [Exterior(export_dir, all_refs, *spec) for spec in exteriors]
    interiors, every, outside, sold = _scoped(export_dir, all_refs, cell, worlds)
    builder = _builder(export_dir, data_dir, every + outside, (table, plugin_dirs), ledger_path(out), light)
    _renamed(builder, data_dir, out.name)
    _object_makers(builder, export_dir, scripts_dir, refs, every + outside)
    builder.vendors = write_vendors(builder, export_dir, sold)
    quest_recs, quests = _cell_quests(builder, export_dir, every + outside, _in_build(interiors, worlds),
                                      _cell_names(builder, export_dir, interiors, worlds))
    ids, ext_ids = _ref_ids(builder, every), _ref_ids(builder, outside)
    vanilla = _vanilla(builder.fo4, {CELL_FO4, BASE_IMAGESPACE, TEST_CHEST})
    base = {**_form_map(builder, {**ids, **ext_ids}, quest_recs, quests), **_cells(builder, interiors, worlds)}
    actors = _people(builder, export_dir, (interiors, worlds), condition_map(builder, base, [], HELPER_INDEX),
                     {**ids, **ext_ids})
    _held_content(builder, export_dir)
    qa_refs, teleports = _teleports(builder, (every, outside), links, {**ids, **ext_ids},
                                    vanilla[TEST_CHEST] if test_cell else None)
    builder.ref_ids = {**ids, **ext_ids, **builder.actor_ids}
    _places(builder, export_dir, worlds, (all_refs, interiors))
    pathing = {c['FormID']: (0, builder.fnv_id(c['FormID'])) for c in interiors}
    navmesh = _navmesh(builder, export_dir, {**pathing, **_world_pathing(builder, worlds)}, {**ids, **ext_ids})
    persistent, temporary = _placed(builder, refs, ids, teleports)
    _quests(builder, export_dir, quest_recs, quests, {**ids, **ext_ids, **builder.actor_ids})
    _rules(builder, export_dir, data_dir, out)
    _gameplay(builder, export_dir, quests)
    rooms = _rooms(builder, (interiors, every), (ids, teleports), navmesh,
                   (persistent + builder.poses.placed, temporary) if cell else None, actors)
    _cell_group(builder, export_dir, vanilla, rooms, qa_refs)
    _world_groups(builder, worlds, (lambda r: _placed(builder, r, ext_ids, teleports), data_dir, navmesh, actors))
    return finish(builder, export_dir, data_dir, out, scripts_dir, HELPER_INDEX)


def _script_dirs(builder: CellBuilder, scripts_dir: 'Path | None'):
    """`scripts_dir`, layered over its masters' converted scripts beside it."""
    if scripts_dir is None or not builder.built:
        return scripts_dir
    return Layered((Path(scripts_dir), *(Path(scripts_dir).parent / p.name for p in builder.built)))


@timed('held content')
def _held_content(builder: CellBuilder, export_dir: Path) -> None:
    """In a build of a source with masters (a DLC), make every base and item its plugin holds, its own and its
    overrides: a DLC's content is what it holds, not what its placed references reach. `builder.held` keeps the
    FO4 FormIDs they are and were made as, the only master records it may override (master_overrides).
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    builder.held = set()
    for sig in held_types(export_dir) if builder.built else ():
        for rec in own_records(export_dir, sig):
            fid = int(rec['FormID'], 16)
            builder.held.add(builder.ids.fo4(fid))
            if sig in PLACED:
                builder.bases.setdefault(fid, (sig, rec))
            made = builder.base(fid) if sig in PLACED else builder.items.item(fid) if sig in ITEM_TYPES else None
            builder.held.add(made)
            builder.counts[f'held {sig} {"made" if made else "not made"}'] += sig in PLACED or sig in ITEM_TYPES


def _world_pathing(builder: CellBuilder, worlds: list) -> dict:
    """Exterior.pathing() of every built worldspace, merged."""
    return {cell: path for world in worlds for cell, path in world.pathing(builder).items()}


@timed('worlds')
def _world_groups(builder: CellBuilder, worlds: list, placing: tuple) -> None:
    """Add each built worldspace's WRLD group: its bases made in placement order, then Exterior.group(`placing`:
    place, data folder, navmeshes, actors), and for a worldspace the plugin owns its object LOD input list
    (object_lod) and its terrain LOD; a master's worldspace keeps the master build's. `builder.built_worlds` lists
    their FNV FormIDs (a child worldspace links its parent only when built).
    See: docs/fork/fo4_plugin_layout.md#dlc-lod
    """
    builder.built_worlds = frozenset(int(world.world['FormID'], 16) for world in worlds)
    for world in worlds:
        for ref in world.placement_order():
            builder.base(int(ref['NAME'], 16))
        owned = builder.ids.is_own(int(world.world['FormID'], 16))
        if owned:
            builder.object_lod.begin(world.fo4_edid)
        builder.writer.add_raw_group('WRLD', world.group(builder, *placing))
        if not owned:
            builder.counts["master worldspaces left to the master's LOD"] += 1
            continue
        builder.counts['object LOD references'] += builder.object_lod.write(placing[1])
        builder.counts['terrain LOD tiles'] += terrain_lod.write(world.export_dir, placing[1], world.world['EditorID'],
                                                                 world.fo4_edid)


@timed('renamed files')
def _renamed(builder: CellBuilder, data_dir: Path, plugin: str) -> None:
    """Write `plugin` as a master when it is an .esm; move the voice and FaceGen folders an older build filed
    under its other extension, and drop that plugin file (plugin_rename).
    See: docs/fork/fo4_plugin_layout.md#saves
    """
    builder.writer.is_esm = is_master(plugin)
    staged, sounds = staging_root(data_dir), sound_root(data_dir)
    parents = [data_dir / folder for folder in facegen.FACEGEN_DIRS] + [
        staged / facegen.FACEGEN_DIRS[1], sounds / 'Sound' / 'Voice', sounds / VOICE_CACHE, data_dir / 'Sound' / 'Voice']
    builder.counts['renamed plugin folders moved'] = move_renamed(plugin, parents)
    builder.counts['renamed plugin files removed'] = drop_old_plugins(data_dir, plugin)
    builder.counts['FaceGen NIFs retargeted to the plugin'] = retarget_faces(data_dir / facegen.FACEGEN_DIRS[0] / plugin, plugin)


@timed('setup')
def _builder(export_dir: Path, data_dir: Path, placed: list, table: tuple, ledger: Path,
             light: Choice) -> CellBuilder:
    """The CellBuilder of the build placing FNV references `placed`: their bases and static collections' parts,
    `table` (replacement table, its plugin folders), its FormIDs kept by the ledger file `ledger` (none when
    `light` switched the plugin's type), light plugins' records through their ledgers.
    See: docs/fork/fo4_pipeline.md#formid-ledger
    """
    used = {int(r[key], 16) for r in placed for key in ('NAME', 'XEMI.Emittance') if key in r}
    parts = Parts(used)
    builder = CellBuilder(export_dir, data_dir, placed_bases(export_dir, used | parts.fids()), *table, light.light)
    kept = Ledger(ledger)
    if light.fresh_ids:
        kept.drop(ID)
    builder.writer.use_ledger(kept)
    ledgers = master_ledgers(builder.masters[:builder.writer.own_index], (data_dir, *table[1]))
    builder.writer.use_master_ledgers(ledgers, builder.in_masters)
    key_light(builder.ids, builder.writer, builder.built, builder.masters, ledgers)
    builder.writer.compare_masters = bool(builder.built)
    master_copies.share(builder)
    builder.parts, builder.emittance = parts, Emittance(builder, export_dir)
    water = builder.placeable_water = PlaceableWater(builder, export_dir)
    parts.parts.update({fid: water.parts(fid, rec) for fid, (sig, rec) in builder.bases.items() if sig == 'PWAT'})
    return builder


@timed('gameplay')
def _gameplay(builder: CellBuilder, export_dir: Path, quests: dict) -> None:
    """Crafting and the new game quest, after the items and quests exist."""
    builder.crafting.build()
    new_game.build(builder, export_dir, quests)


@timed('rooms')
def _rooms(builder: CellBuilder, scoped: tuple, placing: tuple, navmesh: dict, first: tuple, actors: dict) -> list:
    """[(cell, persistent, temporary)] of the interiors in `scoped` (cells, their references), each with its
    navmeshes and `actors` {FNV cell: (persistent, temporary)}: the named cell's references are `first`, the
    others' placed with `placing` (ids, teleports); `first` None: no named cell (its seats are counted, not
    placed)."""
    interiors, inside = scoped[0], by_cell(scoped[1])
    if first is None:
        builder.counts['seat references left out (no named cell)'] += bool(builder.poses.placed)
    named = [first] if first is not None else []
    placed = named + [_placed(builder, inside[c['FormID']], *placing) for c in interiors[len(named):]]
    out = []
    for c, (p, t) in zip(interiors, placed):
        people = actors.get(c['FormID'], (b'', b''))
        out.append((c, p + people[0], t + people[1] + navmesh.get(c['FormID'], b'')))
    return out


@timed('scope')
def _scoped(export_dir: Path, all_refs: list, cell: dict, worlds: list) -> tuple:
    """(interiors, their references, the worldspaces' references, the built vendors (vendors.merchants)) of a
    build from `cell`: interiors.scope() with the vendors' merchant containers, and each of `worlds` with the
    persistent references past it its actors' packages name (named_refs)."""
    outside = [r for world in worlds for r in world.refs]
    interiors, every = scope(export_dir, all_refs, cell, outside)
    sold = merchants(export_dir, _in_build(interiors, worlds))
    interiors, every = with_chests(export_dir, interiors, every, [chest for _, chest in sold])
    cell_of = _in_build(interiors, worlds)
    actors = [r for sig in ('ACHR', 'ACRE') for r in export_records(export_dir, sig) if cell_of(r)] if worlds else []
    for n, world in enumerate(worlds):
        placed = {r['FormID'] for w in worlds for r in w.refs}
        world.add_persistent(named_markers(export_dir, actors, world.persistent_cell, placed))
        world.add_persistent(radio_placements(export_dir, all_refs, world, n == 0))
    return interiors, every, [r for world in worlds for r in world.refs], sold


def _exterior_cells(worlds: list) -> list:
    """Every built worldspace's grid cells (FNV CELL records)."""
    return [c for world in worlds for c in world.cells.values()]


def _cell_names(builder: CellBuilder, export_dir: Path, interiors: list, worlds: list) -> dict:
    """{EditorID: FO4 form} of the built interiors, named exterior cells and worldspaces, over the masters' ones
    their built plugins hold (Cell and WorldSpace script properties); every built cell and worldspace, by FNV
    FormID, in `builder.cell_ids`.
    See: docs/fork/fo4_pipeline.md#worldspace-properties
    """
    cells = interiors + _exterior_cells(worlds) + [w.world for w in worlds]
    whole = cells + [{'FormID': w.persistent_cell} for w in worlds]
    builder.cell_ids = {int(c['FormID'], 16): builder.fnv_id(c['FormID']) for c in whole}
    own = {c['EditorID']: builder.fnv_id(c['FormID']) for c in cells if c.get('EditorID')}
    return {**_master_places(builder, export_dir), **own}


def _master_places(builder: CellBuilder, export_dir: Path) -> dict:
    """{EditorID: FO4 form} of the masters' named cells, worldspaces and references their built plugins hold;
    none without.
    See: docs/fork/fo4_pipeline.md#master-references
    """
    if builder.in_masters is None:
        return {}
    found = ((r['EditorID'], builder.ids.fo4(int(r['FormID'], 16))) for sig in ('CELL', 'WRLD', 'REFR')
             for r in export_records(export_dir, sig) if r.get('EditorID') and not builder.ids.is_own(int(r['FormID'], 16)))
    return {edid: fid for edid, fid in found if fid in builder.in_masters}


def _cells(builder: CellBuilder, interiors: list, worlds: list) -> dict:
    """{FNV cell: FO4 cell} of the built interiors and worldspaces' cells."""
    return {int(c['FormID'], 16): builder.fnv_id(c['FormID']) for c in interiors + _exterior_cells(worlds)}


@timed('people')
def _people(builder: CellBuilder, export_dir: Path, scoped: tuple, form_map: dict, ids: dict) -> dict:
    """{FNV cell: (persistent, temporary)} actors in built cells `scoped` (_in_build); then the packages script
    properties reserved before the NPCs' forms were known."""
    builder.npcs = Npcs(builder, export_dir, form_map, builder.creatures)
    placed = builder.npcs.placed(export_records(export_dir, 'ACHR') + export_records(export_dir, 'ACRE'),
                                 _in_build(*scoped), ids, {**builder.factions, **builder.npc_ids},
                                 _on_ground(scoped[1]) if scoped[1] else None)
    builder.packages.write_pending(builder.npcs.form_map)
    return placed


def _on_ground(worlds: list):
    """on_ground(ref, position): Exterior.on_ground of the built worldspace holding `ref`; the position as it is
    elsewhere."""
    def on_ground(ref: dict, pos: tuple) -> tuple:
        """`pos` raised onto the ground of the worldspace holding `ref`."""
        return next((world.on_ground(ref, pos) for world in worlds if world.holds(ref)), pos)
    return on_ground


def _in_build(interiors: list, worlds: list):
    """cell_of(actor ref): the FNV cell it stands in among `interiors` and `worlds`' cells, None outside the
    build."""
    inside = {c['FormID'] for c in interiors}

    def cell_of(ref: dict) -> 'str | None':
        """The FNV cell a built actor stands in; None outside the build."""
        cell = ref.get('ParentCELL')
        return cell if cell in inside or any(world.holds(ref) for world in worlds) else None
    return cell_of


@timed('interiors')
def _cell_group(builder: CellBuilder, export_dir: Path, vanilla: dict, rooms: list, qa_refs: bytes):
    """Add the CELL group: each FNV interior of `rooms` [(cell, persistent, temporary)] and, when it has any of
    `qa_refs` (stand-in doors, the test chest), QASmoke; none when it would hold no cell."""
    qa_record = pack_fo4_record('CELL', CELL_FO4, vanilla[CELL_FO4].flags, vanilla[CELL_FO4].body)
    cells = [(_interior(builder, export_dir, cell, vanilla), builder.fnv_id(cell['FormID']), persistent, temporary)
             for cell, persistent, temporary in rooms]
    qa_smoke = [(qa_record, CELL_FO4, qa_refs, b'')] if qa_refs else []
    if cells or qa_smoke:
        builder.writer.add_raw_group('CELL', R.pack_interior_cells(cells + qa_smoke))


@timed('locations')
def _places(builder: CellBuilder, export_dir: Path, worlds: list, scoped: tuple) -> None:
    """Write the encounter zones and each of `worlds`' locations; `builder.places` maps each interior to the
    location of the first worldspace leading into it, `builder.regions` FNV map regions to theirs. `scoped` is
    (every reference, the interiors built).
    See: docs/fork/fo4_pipeline.md#locations
    """
    builder.zones = encounter_zones(builder, export_dir, {**builder.factions, **builder.npc_ids})
    markers = map_markers(builder.ref_ids)
    for world in reversed(worlds):
        world.locations = Locations(builder, world.world, markers)
        builder.places.update(world.locations.interiors(scoped[0], world.refs, scoped[1]))
        builder.regions.update(world.locations.by_region)


def _zone(builder: CellBuilder, cell: dict) -> int:
    """The FO4 encounter zone of FNV cell `cell`; 0 without one."""
    return builder.zones.get(int(cell.get('XEZN.EncounterZone', '0'), 16), 0)


def _interior(builder: CellBuilder, export_dir: Path, cell: dict, vanilla: dict) -> bytes:
    """The FO4 CELL of FNV interior `cell`: FNV's lighting, imagespace, water height and owner over QASmoke's."""
    template = sub_map(vanilla[CELL_FO4].body)
    imagespace = _imagespace(builder, export_dir, cell, vanilla[BASE_IMAGESPACE].body)
    edid, flags = cell.get('EditorID') or f'Cell{cell["FormID"]}', int(cell['DATA.Flags'])
    water = float(cell['XCLW.WaterHeight']) if flags & HAS_WATER and 'XCLW.WaterHeight' in cell else 0.0
    return R.pack_cell(builder.fnv_id(cell['FormID']), f'FNV_{edid}', cell.get('FULL', edid), flags & 0xFF,
                       lighting(resolved(export_dir, cell), template[b'XCLL']), struct.unpack('<I', template[b'LTMP'])[0],
                       imagespace or struct.unpack('<I', template[b'XCIM'])[0], water,
                       {**builder.factions, **builder.npc_ids}.get(int(cell.get('XOWN.Owner', '0'), 16), 0),
                       (builder.places.get(cell['FormID'], 0), _zone(builder, cell)),
                       music_of(builder).interior(int(cell['FormID'], 16), int(cell.get('XCMO.Music', '0'), 16))
                       + _acoustics(builder).xcas(int(cell['FormID'], 16)))


def _acoustics(builder: CellBuilder) -> AcousticSpaces:
    """`builder`'s acoustic spaces, made on first use."""
    builder.acoustics = builder.acoustics or AcousticSpaces(builder)
    return builder.acoustics


@timed('perks and character')
def _rules(builder: CellBuilder, export_dir: Path, data_dir: Path, out: Path) -> None:
    """Perks, the character system and the standings."""
    builder.perks.write(builder.forms, builder.say.script_vars)
    builder.equipment.write_enchantments()
    builder.consumables.addictions.write_spells()
    builder.scripts.write_gated_messages(builder.forms, builder.say.script_vars)
    character.build(builder, export_dir, data_dir, out.name, HELPER_INDEX)
    Standings(builder, export_dir).build()


