"""FNV's NPCs as Fallout 4 NPCs, placed where FNV places them.

Each FNV NPC base becomes a copy of a vanilla body for its race and sex
(the replacement table's body rules), with FNV's name, factions, AI packages, script, outfit (its worn
items) and inventory (the rest); a human whose sex has a calibration (both
are measured by sculpt_calibration) also takes FNV's face fitted to FO4's
sculpt regions, tints and head parts. A template (TPLT) is followed for
each part its flags take from it; an NPC whose traits come from a leveled
list becomes an FO4 template actor on the converted list. Every actor
placed in a built cell is written in that cell, with FNV's persistent and
initially disabled flags. Before any is written, the faces the build will
fit and the work cache lacks are taken from the installed published fits
(face_fits) or fitted in worker processes (warm_faces).

See: docs/fork/fo4_pipeline.md#npcs
See: docs/fork/fo4_tool_audit.md#first-build
"""

import contextlib
import mmap
import os
import struct
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from core.process_job import join_pool_job
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM, source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.face import hair, sculpt, tint
from fo4_import.face.sculpt import FACE_SHAPE
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import cached, lookup, store
from fo4_import.spike.face_fits import FIT_SITES, bases, fit_key, take
from fo4_import.spike import records as R
from fo4_import.spike.entry_condition import condition_of
from fo4_import.spike.face_fit import sculpt_fit, tint_fit
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.head_parts import choose, head_parts_edit
from fo4_import.spike.npc_skills import with_skills
from fo4_import.spike.placement import place, placement, starts_disabled
from fo4_import.spike.stand_in_fields import checked
from fo4_import.spike.voice_types import with_voice
from fo4_import.spike.void_actors import VOID_FOLDER, VoidActors
from fo4_import.spike.actor_data import (ACBS_TEMPLATE, NPC_FLAGS, STARTS_DEAD, UNIQUE, hit_proof, starts_dead,
                                         with_actor_data)
from fo4_import.spike.ragdoll_pose import Poses, ragdolls
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Body subrecords a converted NPC leaves out: factions, crime faction, short name (subtitles), scripts (Jones').
BODY_TIES = frozenset({b'SNAM', b'CRIF', b'SHRT', b'VMAD', b'LTPT', b'LTPC'})
#: FNV ACBS template flags: traits (race, face, sex, voice), factions, AI packages, inventory, script.
USE_TRAITS, USE_FACTIONS, USE_PACKAGES, USE_INVENTORY, USE_SCRIPT = 0x1, 0x4, 0x20, 0x100, 0x200
#: FNV and FO4 template flag Model/Animation.
USE_MODEL = 0x40
#: FNV ACBS template flags: stats (level band), AI data, base data (essential, respawn).
USE_STATS, USE_AI_DATA, USE_BASE_DATA = 0x2, 0x10, 0x80
#: FNV's ten template parts (traits ... script), the same bits in FO4's ACBS; TPTA slots; ACBS byte (xEdit).
TEMPLATE_PARTS, TEMPLATE_SLOTS = 0x3FF, 13
#: FO4's template parts FNV lacks (Def Pack List, Attack Data, Keywords), and all thirteen.
USE_DEF_PACKS, USE_ATTACKS, USE_KEYWORDS, ALL_PARTS = 0x400, 0x800, 0x1000, 0x1FFF
#: Fallout4.esm's Citizen, the commonest class of its human NPCs that set one (323); DocWeathers' is a turret's.
HUMAN_CLASS = 0x1326B
#: The tags vanilla's ECOR (all 1,339) comes right before.
ECOR_BEFORE = (b'FCPL', b'RCLR', b'PRKZ', b'PRKR', b'PRPS', b'FTYP', b'NTRM', b'COCT')
#: The tags vanilla's PRKZ and PRKR come right before (xEdit's NPC_ order; AIDT is in every NPC).
PERKS_BEFORE = (b'PRPS', b'FTYP', b'NTRM', b'COCT', b'CNTO', b'AIDT')
#: The tag an NPC_'s VMAD comes right before (it follows EDID).
VMAD_BEFORE = (b'OBND',)
#: derive_formid site of an NPC's outfit (key: the FNV NPC's FormID).
OUTFIT_SITE = 'FNV OTFT'
#: FNV ACBS flag Female; reference record flags Persistent and No AI Acquire (the same bits in FO4's ACHR).
FEMALE, PERSISTENT, NO_AI_ACQUIRE = 0x1, 0x400, 0x2000000
#: new_id keys of a converted NPC and its placed actor (the spike's, kept so no FormID moves).
NPC_KEY, ACHR_KEY = 'NPC_ {:08X} STH', 'ACHR {} STH'
#: Face-fit worker processes at most: each holds about 1.26 GB, and BLAS already spreads one fit over every core.
FACE_WORKERS = 6
#: OpenBLAS threads this process loaded with, which face workers start with too (docs/fork/fo4_pipeline.md#audit-fixes).
MAIN_BLAS_THREADS = os.environ.get('OPENBLAS_NUM_THREADS') or str(os.cpu_count() or 1)
#: A face worker process's head part assets (_start_face_worker).
_worker = {}


def face_work(export_dir: Path, edid: str, female: bool, assets) -> tuple:
    """The makers of FIT_SITES' values for FNV NPC `edid` (head parts among `assets`)."""
    return (lambda: sculpt_fit(export_dir, edid, female), lambda: tint_fit(export_dir, edid, female),
            lambda: choose(export_dir, edid, assets, sculpt.load_basis(female)[2]))


def fit_face(export_dir: Path, npc: dict, female: bool, assets) -> 'tuple | None':
    """(sculpt fit, tint fit, head part choice) of FNV NPC `npc` through the work cache; None uncalibrated."""
    key = fit_key(npc, female)
    if key is None:
        return None
    return tuple(cached(site, module, key, make)
                 for (site, module), make in zip(FIT_SITES, face_work(export_dir, npc['EditorID'], female, assets)))


def head_assets(esm) -> hair.Fo4Assets:
    """Head parts of Fallout4.esm `esm` (bytes or a map) and the game's archives."""
    return hair.Fo4Assets(esm, Archives(FALLOUT4_DIR / 'Data'))


@contextlib.contextmanager
def _blas_threads(count: str):
    """OPENBLAS_NUM_THREADS set to `count` for the processes spawned inside, as it was after."""
    old = os.environ.get('OPENBLAS_NUM_THREADS')
    os.environ['OPENBLAS_NUM_THREADS'] = count
    try:
        yield
    finally:
        if old is None:
            os.environ.pop('OPENBLAS_NUM_THREADS', None)
        else:
            os.environ['OPENBLAS_NUM_THREADS'] = old


def _start_face_worker() -> None:
    """A face worker's start: join the pool job; index head parts (mapped esm)."""
    join_pool_job()
    with open(FALLOUT4_ESM, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as esm:
        _worker['assets'] = head_assets(esm)


def _fit_in_worker(job: tuple) -> 'dict | None':
    """{FIT_SITES index: value} of the fits `job` = (export dir, NPC record, female, indices) asks for; None
    when one fails, left to fail where the build uses it."""
    export_dir, npc, female, wanted = job
    makers = face_work(export_dir, npc['EditorID'], female, _worker['assets'])
    try:
        return {i: makers[i]() for i in wanted}
    except Exception:
        return None


def faction_snams(rec: dict, factions: dict) -> bytes:
    """FO4 SNAMs of the factions FNV NPC or creature `rec` lists, through `factions` {FNV: FO4}."""
    out = b''
    for i in range(int(rec.get('FactionCount', 0))):
        faction = factions.get(int(rec[f'Faction[{i}].FormID'], 16))
        if faction:
            out += pack_subrecord('SNAM', struct.pack('<Ib', faction, int(rec[f'Faction[{i}].Rank'])))
    return out


def with_class(subs: bytes) -> bytes:
    """A converted human's subrecords with CNAM (class) HUMAN_CLASS."""
    return b''.join(pack_subrecord(tag.decode(), struct.pack('<I', HUMAN_CLASS) if tag == b'CNAM' else data)
                    for tag, data in subrecords(subs))


def with_factions(snams: bytes):
    """A record edit putting faction subrecords `snams` right after ACBS, as FO4 orders them."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with the factions after ACBS."""
        out = b''
        for tag, data in subrecords(subs):
            out += pack_subrecord(tag.decode(), data) + (snams if tag == b'ACBS' else b'')
        return out
    return edit


def with_inventory(outfit: int, carried: list):
    """A record edit replacing the body's default outfit with `outfit` (0: none) and its inventory with `carried`
    [(item, count, condition or None)], a COED after an item with a condition; a body without items gets them
    before AIDT, as vanilla orders them."""
    block = (pack_subrecord('COCT', struct.pack('<I', len(carried))) + b''.join(
        pack_subrecord('CNTO', struct.pack('<Ii', item, count)) + R.pack_coed(condition)
        for item, count, condition in carried)) if carried else b''

    def edit(subs: bytes) -> bytes:
        """The subrecords with the outfit and inventory replaced."""
        found = list(subrecords(subs))
        at = b'COCT' if any(tag == b'COCT' for tag, _ in found) else b'AIDT'
        out = b''
        for tag, data in found:
            out += block if tag == at else b''
            if tag == b'DOFT' and outfit:
                out += pack_subrecord('DOFT', struct.pack('<I', outfit))
            elif tag not in (b'COCT', b'CNTO', b'COED', b'DOFT'):
                out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def with_template(template: int, flags: int, traits: int = 0):
    """A record edit making an NPC a template actor: FO4 ACBS template `flags` (ALL_PARTS), TPLT `template` and
    TPTA naming it for each flagged part, before RNAM as vanilla orders them. The clone's attack race (ATKR) goes,
    so attacks follow the race its template gives, and its Unique flag (FNV has none). `traits`, when given, is
    the Traits slot's own template, as 653 vanilla template actors name one."""
    flags &= ALL_PARTS
    slots = [template if flags >> bit & 1 else 0 for bit in range(TEMPLATE_SLOTS)]
    slots[0] = traits if traits and flags & USE_TRAITS else slots[0]
    tpta = struct.pack(f'<{TEMPLATE_SLOTS}I', *slots)

    def edit(subs: bytes) -> bytes:
        """The subrecords with the template set."""
        out = b''
        for tag, data in subrecords(subs):
            if tag == b'ACBS':
                data = struct.pack('<I', struct.unpack_from('<I', data)[0] & ~UNIQUE) + data[4:]
                data = data[:ACBS_TEMPLATE] + struct.pack('<H', flags) + data[ACBS_TEMPLATE + 2:]
            elif tag == b'RNAM':
                out += pack_subrecord('TPLT', struct.pack('<I', template)) + pack_subrecord('TPTA', tpta)
            if tag not in (b'TPLT', b'TPTA', b'ATKR'):
                out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def with_perks(perks: list):
    """A record edit giving an NPC `perks` at rank 1 (PRKZ, a PRKR each) where vanilla orders them; None for none.
    See: docs/fork/fo4_perks.md#teammate-perks
    """
    if not perks:
        return None
    block = pack_subrecord('PRKZ', struct.pack('<I', len(perks)))
    block += b''.join(pack_subrecord('PRKR', struct.pack('<IB', perk, 1)) for perk in perks)

    def edit(subs: bytes) -> bytes:
        """The subrecords with the perks before the first of PERKS_BEFORE."""
        out, placed = b'', False
        for tag, data in subrecords(subs):
            if tag in PERKS_BEFORE and not placed:
                out, placed = out + block, True
            out += pack_subrecord(tag.decode(), data)
        return out if placed else out + block
    return edit


def composed(*edits):
    """One record edit applying `edits` (None skipped) in order; None when there are none."""
    present = [e for e in edits if e is not None]

    def edit(subs: bytes) -> bytes:
        """The subrecords after every edit."""
        for step in present:
            subs = step(subs)
        return subs
    return edit if present else None


def template_source(records: dict, rec: dict, flag: int) -> tuple:
    """(the record of `records` {FormID: record} actor record `rec` takes template part `flag` from, following
    TPLT while its template flags take `flag`; whether the chain left `records` (a leveled list or another
    type), the record then being the last one in them)."""
    while int(rec.get('ACBS.TemplateFlags', 0)) & flag and 'TPLT.Template' in rec:
        nxt = records.get(int(rec['TPLT.Template'], 16))
        if nxt is None:
            return rec, True
        rec = nxt
    return rec, False


def _entries(rec: dict) -> list:
    """[(level, FormID hex, count)] of FNV leveled list `rec`'s entries."""
    return [(int(rec[f'Entry[{i}].Level']), rec[f'Entry[{i}].FormID'], int(rec[f'Entry[{i}].Count']))
            for i in range(int(rec.get('EntryCount', 0) or 0))]


def body_kind(ghoul: bool, female: bool) -> str:
    """The body rule key (replacements.BODY_KINDS) of a ghoul or human."""
    return f"{'ghoul' if ghoul else 'human'}_{'female' if female else 'male'}"


def bodies(fo4: bytes, rules: dict) -> dict:
    """{body kind: the Fallout4.esm NPC_ record} of the table's body `rules` {kind: Replacement}, by EditorID."""
    wanted = {}
    for kind, entry in rules.items():
        wanted.setdefault(entry.edid.lower(), []).append(kind)
    found = {}
    for rec, _ in walk(fo4, b'NPC_'):
        edid = (dict(subrecords(rec.body)).get(b'EDID') or b'').rstrip(b'\0').decode('cp1252').lower()
        found.update({kind: rec for kind in wanted.get(edid, ())})
    missing = sorted(set(rules) - set(found))
    if missing:
        raise ValueError(f'replacement bodies not in Fallout4.esm: {[rules[k].edid for k in missing]}')
    return found


def with_script(scripts, scpt: int, extra: tuple = ()):
    """VMAD edit: FNV script `scpt` (0: none) and `extra`; None for neither."""
    return R.with_sub(b'VMAD', scripts.vmad(scpt, extra), VMAD_BEFORE)


def without_keywords(subs: bytes) -> bytes:
    """NPC_ subrecords `subs` without their keyword list (KSIZ, KWDA)."""
    return b''.join(pack_subrecord(t.decode(), d) for t, d in subrecords(subs) if t not in (b'KSIZ', b'KWDA'))


def script_of(rec: 'dict | None') -> int:
    """FNV record `rec`'s script FormID; 0 without one."""
    return int((rec or {}).get('SCRI', '0'), 16)


def _traits_templated(rec: dict) -> bool:
    """Whether FNV actor record `rec` takes its traits from its template."""
    return 'TPLT.Template' in rec and bool(int(rec.get('ACBS.TemplateFlags', 0)) & USE_TRAITS)


def _model_templated(rec: dict) -> bool:
    """Whether FNV actor record `rec` takes its model and animations from its template."""
    return 'TPLT.Template' in rec and bool(int(rec.get('ACBS.TemplateFlags', 0)) & USE_MODEL)


class Npcs:
    """FO4 NPCs for FNV NPC bases, each written once, and their placed actors."""

    def __init__(self, builder, export_dir: Path, form_map: dict, creatures):
        """Index FNV's NPCs and races; `form_map` maps the FNV forms packages name, `creatures` (creatures.py)
        makes the placed creatures' bases."""
        self.builder, self.export_dir, self.form_map, self.creatures = builder, export_dir, form_map, creatures
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'NPC_')}
        self.races = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'RACE')}
        self.bodies = bodies(builder.fo4, builder.table.rules.body)
        self.assets, self.made, self.voices = None, {}, creatures.voices
        self.lists = {int(r['FormID'], 16): r for sig in ('LVLN', 'LVLC') for r in export_records(export_dir, sig)}
        self.made_lists, self.tone_layers = {}, skin_tone_layers(builder.fo4)
        self.voids, self.void_lists, self.poses = VoidActors(builder), set(), None

    def source(self, fnv: int, flag: int) -> 'dict | None':
        """The NPC or creature `fnv` takes part `flag` from (template_source); None if a list."""
        records = self.records if fnv in self.records else self.creatures.records
        rec = records.get(fnv)
        found, left = template_source(records, rec, flag) if rec is not None else (None, True)
        return None if left else found

    def base(self, fnv: int) -> 'int | None':
        """The FO4 NPC for FNV NPC `fnv`, written once (_make); None if not made."""
        if fnv not in self.made:
            self.made[fnv] = self._make(fnv)
        return self.made[fnv]

    def _make(self, fnv: int) -> 'int | None':
        """Write the FO4 NPC of FNV NPC `fnv` (class notes); its FormID."""
        npc, traits = self.records[fnv], self.source(fnv, USE_TRAITS)
        if traits is None:
            return self._templated(fnv)
        ghoul, female, face = self._kind(traits)
        body = self.bodies[body_kind(ghoul, female)]
        morphs, edit = (self._face(traits, female) if face else (b'', None))
        fid = self.builder.new_id(NPC_KEY.format(fnv))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, body.body, body.flags, f'FNV_{npc["EditorID"]}', npc.get('FULL', ''),
            (FACE_SHAPE if face else frozenset()) | BODY_TIES, morphs,
            composed(edit, with_class, with_factions(self._factions(fnv)), self._packages(fnv), self._inventory(fnv),
                     with_voice(self.voices.of(int(traits.get('VTCK.Voice', '0'), 16))), self._actor_data(fnv),
                     self.builder.combat_styles.edit(traits), with_perks(self.builder.perks.teammates.held_by(fnv)),
                     self._skills(fnv), with_script(self.builder.scripts, script_of(self.source(fnv, USE_SCRIPT))),
                     self._listed_template(fnv))))
        self.builder.counts['NPC_'] += 1
        self.builder.npc_ids[fnv] = fid
        return fid

    def _listed_template(self, fnv: int):
        """with_template for the parts FNV NPC `fnv`, its traits its own, takes from a leveled list (source() None),
        its template being the list's FO4 copy; None when no part is listed or the template is not built.
        See: docs/fork/fo4_pipeline.md#npcs
        """
        npc = self.records[fnv]
        flags = int(npc.get('ACBS.TemplateFlags', 0)) & TEMPLATE_PARTS
        listed = sum(bit for bit in (1 << i for i in range(TEMPLATE_SLOTS)) if flags & bit and self.source(fnv, bit) is None)
        template = self._template(npc['TPLT.Template']) if listed else None
        self.builder.counts['NPC_ with a listed template'] += bool(template)
        return with_template(template, listed) if template else None

    def _kind(self, traits: dict) -> tuple:
        """(ghoul, female, fitted: a human whose sex has both bases) of `traits`."""
        ghoul = 'ghoul' in self.races.get(int(traits.get('RNAM.Race', '0'), 16), '').lower()
        female = bool(int(traits.get('ACBS.Flags', 0)) & FEMALE)
        return ghoul, female, not ghoul and len(bases(female)) == 2

    def _templated(self, fnv: int) -> 'int | None':
        """Write FNV NPC or creature `fnv`, whose traits come from a leveled list or a template, as an FO4 template
        actor: the male body with FNV's template flags and template (with_template), an NPC's own parts where FNV
        keeps them."""
        npc = self.records.get(fnv) or self.creatures.records[fnv]
        template = self._template(npc.get('TPLT.Template', '0'))
        if template is None:
            self.builder.counts['NPC_ skipped (template not built)'] += 1
            return None
        body = None if fnv in self.records else self.creatures.stand_in(fnv)
        armed, guns = (False, None) if fnv in self.records else self.creatures.own_guns(npc)
        parts = (with_factions(self._factions(fnv)), self._packages(fnv), self._inventory(fnv),
                 self._actor_data(fnv), self._skills(fnv)) if fnv in self.records else (
                     None if body else without_keywords, self.creatures.actor_data(npc, npc, npc),
                     self._packages(fnv), *self.creatures.own_parts(npc, templated=True), guns,
                     self.creatures.inventory(npc, body or self.bodies[body_kind(False, False)],
                                              bool(body) and self.creatures.keeps_look(fnv), armed))
        parts += (self._template_style(npc), self._template_script(npc))
        traits = 0 if fnv in self.records else self.creatures.traits_variant(npc) or 0
        fid = self._template_actor(fnv, npc, template, self._template_flags(npc), parts, body, traits)
        self.builder.npc_ids[fnv] = fid
        return fid

    def _template_style(self, rec: dict):
        """ZNAM edit of template actor `rec`: its traits' style; None from a list.
        See: docs/fork/fo4_pipeline.md#combat-styles
        """
        traits, left = self._traits(rec)
        return None if left else self.builder.combat_styles.edit(traits)

    def _traits(self, rec: dict) -> tuple:
        """(record, left) `rec`'s traits chain reaches (template_source)."""
        records = self.records if int(rec['FormID'], 16) in self.records else self.creatures.records
        return template_source(records, rec, USE_TRAITS)

    def _template_flags(self, rec: dict) -> int:
        """FO4 template flags of template actor `rec`: FNV's ten, Traits too for a creature whose model comes from
        its template (its race and skin do in FO4); with Traits, also Attack Data, Def Pack List and Keywords,
        except a creature whose traits come from a creature keeps its own keywords (Creatures.own_parts).
        See: docs/fork/fo4_creature_audit.md#template-slots
        """
        flags = int(rec.get('ACBS.TemplateFlags', 0)) & TEMPLATE_PARTS
        creature = int(rec['FormID'], 16) in self.creatures.records
        flags |= USE_TRAITS if creature and flags & USE_MODEL else 0
        if not flags & USE_TRAITS:
            return flags
        own = creature and not self._traits(rec)[1]
        return flags | USE_ATTACKS | USE_DEF_PACKS | (0 if own else USE_KEYWORDS)

    def _template_script(self, rec: dict):
        """The VMAD edit of template actor `rec`: its own FNV script and, when its list can draw the void, the
        void check; neither when FNV takes its script from the template (FO4's Script slot gives that).
        See: docs/fork/fo4_creature_audit.md#void
        """
        if int(rec.get('ACBS.TemplateFlags', 0)) & USE_SCRIPT:
            return None
        void = self.voids.check() if self._draws_void(int(rec['TPLT.Template'], 16)) else ()
        return with_script(self.builder.scripts, script_of(rec), void)

    def _draws_void(self, fnv: int) -> bool:
        """Whether FNV form `fnv` (a template or list entry) can give a void creature's traits: a void creature,
        a list holding one (made by _list), or a creature whose traits come from such a form."""
        if fnv in self.lists:
            return fnv in self.void_lists
        rec = self.creatures.records.get(fnv)
        if rec is None or fnv in self.records:
            return False
        if self.creatures.label(fnv) == VOID_FOLDER:
            return True
        return _traits_templated(rec) and self._draws_void(int(rec['TPLT.Template'], 16))

    def _template_actor(self, fnv: int, rec: dict, template: int, flags: int, parts: tuple, body=None,
                        traits: int = 0) -> int:
        """Write a template actor for FNV form `fnv` (`rec`) on `template` with `flags`, then `parts` edits; a copy
        of `body` (a creature's stand-in, whose class and combat style it keeps), else the male NPC body; its
        Traits slot naming `traits` when given (with_template)."""
        male = self.bodies[body_kind(False, False)]
        body, fid = body or male, self.builder.new_id(NPC_KEY.format(fnv))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, body.body, body.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), BODY_TIES, b'',
            checked(self.builder.counts, body.body, rec['EditorID'],
                    composed(*parts, with_template(template, flags, traits), None if body is not male else with_class))))
        self.builder.counts['NPC_ (template actor)'] += 1
        return fid

    def _creature(self, fnv: int) -> 'int | None':
        """The FO4 base of FNV creature or leveled creature list `fnv` (made once); None when it does not convert."""
        if fnv not in self.made:
            rec = self.creatures.records.get(fnv)
            if fnv in self.lists:
                listed = self._list(fnv)
                self.made[fnv] = listed and self._template_actor(fnv, self.lists[fnv], listed, ALL_PARTS, ())
            elif rec is not None and (_traits_templated(rec) or _model_templated(rec) and not self.creatures.converts(fnv)):
                self.made[fnv] = self._templated(fnv)
            else:
                packages = (self.builder.packages.for_npc(self.creatures.source(rec, USE_PACKAGES), self.form_map)
                            if self.creatures.converts(fnv) else [])
                self.made[fnv] = self.creatures.base(fnv, packages) if self.creatures.converts(fnv) else None
        return self.made[fnv]

    def _template(self, fnv_hex: str) -> 'int | None':
        """The FO4 form of FNV template `fnv_hex`: an NPC (base()) or a leveled list (_list()); None if neither."""
        fnv = int(fnv_hex, 16)
        if fnv in self.records:
            return self.base(fnv)
        if fnv in self.creatures.records:
            return self.voids.actor() if self.creatures.label(fnv) == VOID_FOLDER else self._creature(fnv)
        return self._list(fnv) if fnv in self.lists else None

    def _list(self, fnv: int) -> 'int | None':
        """FNV leveled NPC list `fnv` as an FO4 LVLN of its entries that convert, on FNV's FormID; None if none do."""
        if fnv not in self.made_lists:
            rec, fid = self.lists[fnv], self.builder.fnv_id(f'{fnv:08X}')
            self.made_lists[fnv] = fid
            entries = [(level, self._template(form), count) for level, form, count in _entries(rec)]
            entries = [e for e in entries if e[1] is not None]
            if any(self._draws_void(int(form, 16)) for _, form, _ in _entries(rec)):
                self.void_lists.add(fnv)
            self.made_lists[fnv] = fid if entries else None
            if entries:
                self.builder.writer.add_record('LVLN', R.pack_leveled(
                    'LVLN', fid, f'FNV_{rec["EditorID"]}', int(rec.get('LVLD.ChanceNone', 0)),
                    int(rec.get('LVLF.Flags', 0)), entries))
                self.builder.counts['LVLN'] += 1
        return self.made_lists[fnv]

    def _actor_data(self, fnv: int):
        """The edit giving FNV NPC `fnv` its (or its templates') flags, level band and AI data (actor_data)."""
        npc = self.records[fnv]
        flags = int((self.source(fnv, USE_BASE_DATA) or npc).get('ACBS.Flags', 0))
        female = int((self.source(fnv, USE_TRAITS) or npc).get('ACBS.Flags', 0)) & FEMALE
        stats = {**(self.source(fnv, USE_STATS) or npc), 'ACBS.Flags': flags & ~FEMALE | female}
        proof = hit_proof(self.export_dir, self.source(fnv, USE_SCRIPT) or npc)
        return with_actor_data(stats, self.source(fnv, USE_AI_DATA) or npc, NPC_FLAGS, proof)

    def _skills(self, fnv: int):
        """FNV NPC `fnv`'s (or stats template's) skills edit; None from a list."""
        stats = self.source(fnv, USE_STATS)
        return with_skills(int(stats['FormID'], 16), self.builder.scripts.helper_index) if stats else None

    def _factions(self, fnv: int) -> bytes:
        """FO4 SNAMs of FNV NPC `fnv`'s (or template's) factions and vendor one."""
        vendor = getattr(self.builder, 'vendors', {}).get(fnv)
        own = pack_subrecord('SNAM', struct.pack('<Ib', vendor, 0)) if vendor else b''
        return faction_snams(self.source(fnv, USE_FACTIONS) or {}, self.builder.factions) + own

    def _inventory(self, fnv: int):
        """The edit giving FNV NPC `fnv` (or its template) its worn items as an outfit, the rest as inventory."""
        rec, items = self.source(fnv, USE_INVENTORY) or {}, self.builder.items
        worn, carried = [], []
        for i in range(int(rec.get('ItemCount', 0))):
            item = int(rec[f'Item[{i}].FormID'], 16)
            made, entry = items.item(item), (int(rec[f'Item[{i}].Count']), condition_of(int(rec['FormID'], 16), i))
            if made is not None and items.wearable(item):
                worn.append((item, made, entry))
            elif made is not None:
                carried.append((made, *entry))
        dressed = self._dressed([item for item, _, _ in worn])
        carried += [(made, *entry) for item, made, entry in worn if item not in dressed]
        return with_inventory(self._outfit(fnv, [made for item, made, _ in worn if item in dressed]), carried)

    def _dressed(self, items: list) -> set:
        """The FNV items of `items` an NPC wears, as FNV equips them: per biped slot the armor with the best
        rating, then value; a leveled list always (its slots are known only when it is drawn).
        See: docs/fork/fo4_pipeline.md#outfit-slots
        """
        records, fields = self.builder.items.records, self.builder.equipment.fnv
        armor = [i for i in items if records.get(i, (None,))[0] == 'ARMO']
        best = sorted(armor, key=lambda i: (-fields.get(i, {}).get('rating', 0), -fields.get(i, {}).get('value', 0)))
        taken, out = 0, {i for i in items if i not in armor}
        for item in best:
            slots = int(records[item][1].get('BMDT.BipedFlags', 0) or 0)
            if not slots & taken:
                taken |= slots
                out.add(item)
        return out

    def _outfit(self, fnv: int, worn: list) -> int:
        """An outfit of `worn` for FNV NPC `fnv`, written; 0 when it wears nothing."""
        if not worn:
            return 0
        fid = self.builder.writer.derive_formid(OUTFIT_SITE, fnv)
        body = pack_subrecord('EDID', f'FNV_{self.records[fnv]["EditorID"]}Outfit\0'.encode('cp1252'))
        body += pack_subrecord('INAM', b''.join(struct.pack('<I', f) for f in sorted(set(worn))))
        self.builder.writer.add_record('OTFT', pack_fo4_record('OTFT', fid, 0, body))
        self.builder.counts['OTFT'] += 1
        return fid

    def _packages(self, fnv: int):
        """The edit giving FNV NPC `fnv` its (or its template's) AI packages and combat override list."""
        rec, packages = self.source(fnv, USE_PACKAGES) or {}, self.builder.packages
        listed = R.packages_edit(packages.for_npc(rec, self.form_map))
        combat = packages.combat_list(rec)
        return composed(listed, R.with_sub(b'ECOR', struct.pack('<I', combat) if combat else b'', ECOR_BEFORE))

    def _head_assets(self) -> hair.Fo4Assets:
        """Fallout4.esm's head parts and the game's archives (hair.Fo4Assets), read once."""
        self.assets = self.assets or head_assets(self.builder.fo4)
        return self.assets

    def _face(self, npc: dict, female: bool) -> tuple:
        """(sculpt morphs, edit giving tints and head parts) of FNV NPC `npc`'s face fitted on its sex's basis."""
        fitted = fit_face(self.export_dir, npc, female, self._head_assets())
        if fitted is None:
            self.builder.counts['face fit skipped (no calibration)'] += 1
            return b'', None
        sculpted, tinted, chosen = fitted
        self.builder.counts['face fitted'] += 1
        return (sculpted or (b'',))[0], composed(_tint_edit(tinted, female, self.tone_layers),
                                                 head_parts_edit(chosen, self.assets))

    def warm_faces(self, fnvs: list, workers: int = 0) -> int:
        """Fit in `workers` processes (FACE_WORKERS at most by default) the faces the bases of FNV forms `fnvs`
        need (_faces) that the work cache lacks and the installed published fits can't give (face_fits.take),
        stored under its keys so base() only reads them; how many.
        See: docs/fork/fo4_pipeline.md#audit-fixes
        See: docs/fork/fo4_pipeline.md#published-face-fits
        """
        jobs, keys = [], []
        for npc, female in sorted(self._faces(fnvs).values(), key=lambda f: (f[1], f[0].get('RNAM.Race', ''),
                                                                               f[0]['FormID'])):
            key, missing = fit_key(npc, female), object()
            wanted = [i for i, site in enumerate(FIT_SITES) if lookup(*site, key, missing) is missing]
            taken, count = take(npc, female, key, wanted) if wanted else (True, '')
            if not taken:
                jobs.append((self.export_dir, npc, female, wanted))
                keys.append(key)
            if count:
                self.builder.counts[count] += 1
        if not jobs:
            return 0
        workers = min(len(jobs), workers or max(1, min(FACE_WORKERS, (os.cpu_count() or 2) - 1)))
        with _blas_threads(MAIN_BLAS_THREADS), ProcessPoolExecutor(max_workers=workers,
                                                                   initializer=_start_face_worker) as pool:
            for key, made in zip(keys, pool.map(_fit_in_worker, jobs, chunksize=1)):
                for i, value in (made or {}).items():
                    store(*FIT_SITES[i], key, value)
        self.builder.counts['faces fitted in worker processes'] += len(jobs)
        return len(jobs)

    def _faces(self, fnvs: list) -> dict:
        """{traits FormID: (traits record, female)} of the faces base() fits making the bases of FNV forms `fnvs`
        and of the templates and leveled list entries those reach."""
        todo, seen, out = list(fnvs), set(), {}
        while todo:
            fnv = todo.pop()
            if fnv not in seen:
                seen.add(fnv)
                todo += self._reaches(fnv, out)
        return out

    def _reaches(self, fnv: int, faces: dict) -> list:
        """The forms whose bases get made with FNV form `fnv`'s (its template, its list's entries: as _make,
        _templated, _creature and _list follow them); the face its base fits, if any, goes in `faces`."""
        if fnv in self.lists:
            return [int(form, 16) for _, form, _ in _entries(self.lists[fnv])]
        traits = self.source(fnv, USE_TRAITS) if fnv in self.records else None
        if traits is not None:
            _, female, face = self._kind(traits)
            faces.update({int(traits['FormID'], 16): (traits, female)} if face else {})
            return []
        rec = self.records.get(fnv) or self.creatures.records.get(fnv) or {}
        follows = fnv in self.records or _traits_templated(rec)
        return [int(rec['TPLT.Template'], 16)] if follows and 'TPLT.Template' in rec else []

    def placed(self, refs: list, cell_of, ids: dict, owners: dict, lift=None) -> dict:
        """{FNV cell: (persistent, temporary) ACHRs} of the actors `refs` placed in built cells (`cell_of(ref)`, None
        outside them), their faces fitted first (warm_faces); enable parents and linked references through `ids`
        {FNV hex: FO4}, owners through `owners`; each position through `lift(ref, pos)` (Exterior.on_ground)."""
        self.lift = lift or (lambda ref, pos: pos)
        built = [(cell, ref) for ref in sorted(refs, key=lambda r: r['FormID']) if (cell := cell_of(ref))]
        self.warm_faces([int(ref['NAME'], 16) for _, ref in built])
        bases = {}
        for _, ref in built:
            bases[ref['FormID']] = self._base_of(int(ref['NAME'], 16))
            if bases[ref['FormID']] is None:
                self.builder.counts[self._unbuilt(ref)] += 1
                continue
            self.builder.actor_ids[ref['FormID']] = self.builder.new_id(ACHR_KEY.format(ref['FormID']))
        links, out = {**ids, **self.builder.actor_ids}, {}
        for cell, ref in built:
            if bases[ref['FormID']] is not None:
                slot = out.setdefault(cell, [b'', b''])
                slot[0 if int(ref['RecordFlags']) & PERSISTENT else 1] += self._actor(ref, bases[ref['FormID']],
                                                                                      links, owners)
        return {cell: tuple(slot) for cell, slot in out.items()}

    def _base_of(self, fnv: int) -> 'int | None':
        """The FO4 base of FNV NPC, creature or creature list `fnv`; None if none."""
        return self.base(fnv) if fnv in self.records else self._creature(fnv)

    def _unbuilt(self, ref: dict) -> str:
        """The count key of placed actor `ref` whose base converts to nothing: its creature's skeleton folder
        (Creatures.label), else the base's EditorID."""
        fnv = int(ref['NAME'], 16)
        if fnv in self.creatures.records:
            return f'{ref["Signature"]} skipped (no FO4 base): {self.creatures.label(fnv)}'
        rec = self.records.get(fnv) or self.lists.get(fnv) or {}
        return f'{ref["Signature"]} skipped (no FO4 base): {rec.get("EditorID", ref["NAME"])}'

    def _actor(self, ref: dict, base: int, ids: dict, owners: dict) -> bytes:
        """The FO4 ACHR of FNV actor `ref` on `base` (its FormID from placed()), with its script, parents and linked
        reference through `ids` (actors included), No AI Acquire and scale; one placed dead takes FNV's ragdoll
        pose on its FO4 skeleton (spike.ragdoll_pose)."""
        fnv = int(ref['NAME'], 16)
        achr = self.builder.actor_ids[ref['FormID']]
        self.builder.scripts.named[ref.get('EditorID', '')] = achr
        vanilla = fnv in self.creatures.records and base in self.creatures.as_is.values()
        vmad = self.builder.scripts.vmad(script_of(self.creatures.records[fnv])) if vanilla else b''
        linked = ids.get(ref.get('XLKR.LinkedRef'), 0)
        extra = placement(int(ref['FormID'], 16), ids, owners, pose=False)
        extra += pack_subrecord('XLKR', struct.pack('<II', 0, linked)) if linked else b''
        self.builder.counts['ACHR'] += 1
        flags = int(ref['RecordFlags']) & (PERSISTENT | NO_AI_ACQUIRE)
        flags |= R.INITIALLY_DISABLED if starts_disabled(ref, ids) else 0
        flags |= starts_dead(self.records.get(fnv) or self.creatures.records.get(fnv) or {})
        extra = (self._pose(int(ref['FormID'], 16), fnv, base) if flags & STARTS_DEAD else b'') + extra
        pos, rot = place(ref)
        pos, scale = self.lift(ref, pos), float(ref.get('XSCL.Scale', 1.0) or 1.0)
        look = self.creatures.speaker_look(fnv, achr, ref['FormID'], (pos, rot, scale, bool(flags & PERSISTENT),
                                                                      bool(flags & R.INITIALLY_DISABLED)))
        return R.pack_achr(achr, base, pos, rot, vmad, extra, flags, scale) + look

    def _pose(self, fnv_ref: int, fnv_base: int, base: int) -> bytes:
        """XRGD and XRGB of dead FNV reference `fnv_ref` (base `fnv_base`) on FO4 `base` (Poses, made once)."""
        if self.poses is None:
            fnv = {**self.lists, **self.creatures.records, **self.records}
            self.poses = Poses(self.builder, fnv, ragdolls(source_walk(b'ACHR', b'ACRE')))
        return self.poses.subrecords(fnv_ref, fnv_base, base)


def _tint_edit(fitted, female: bool, options: frozenset):
    """A record edit giving fitted tint layers and skin tone (tint_fit's result on `female`'s basis; Skin Tone
    options `options`); None without a fit."""
    if fitted is None:
        return None
    values, tone, _ = fitted
    basis = tint.load_basis(female)

    def edit(subs: bytes) -> bytes:
        """The record with the fitted tint layers and its skin tone scaled."""
        rest, kept = tint.without_tints(subs, options)
        rest = tint.with_tints(rest, tint.pack_layers(basis[1], values, kept, basis[3]))
        return tint.with_tone(rest, tone, options)
    return edit
