"""FNV's NPCs as Fallout 4 NPCs, placed where FNV places them.

Each FNV NPC base becomes a copy of a vanilla body for its race and sex
(BODIES), with FNV's name, factions, AI packages, script, outfit (its worn
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
from fo4_import.base.install import FALLOUT4_DIR, FALLOUT4_ESM
from fo4_import.base.writer import pack_fo4_record
from fo4_import.face import hair, sculpt, tint
from fo4_import.face.sculpt import FACE_SHAPE
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.work_cache import cached, lookup, store
from fo4_import.spike.face_fits import FIT_SITES, bases, fit_key, take
from fo4_import.spike import records as R
from fo4_import.spike.face_fit import sculpt_fit, tint_fit
from fo4_import.spike.facegen import skin_tone_layers
from fo4_import.spike.head_parts import choose, head_parts_edit
from fo4_import.spike.placement import place, placement
from fo4_import.spike.voice_types import with_voice
from fo4_import.spike.actor_data import CREATURE_FLAGS, NPC_FLAGS, hit_proof, starts_dead, with_actor_data
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: (ghoul, female) -> the Fallout4.esm NPC a converted NPC starts from: DocWeathers, DoctorAmari, Jones, Holly.
BODIES = {(False, False): 0x12FCCB, (False, True): 0x09A680, (True, False): 0x3F239, (True, True): 0x3F23A}
#: Body subrecords a converted NPC leaves out: factions, crime faction, short name (subtitles), scripts (Jones').
BODY_TIES = frozenset({b'SNAM', b'CRIF', b'SHRT', b'VMAD'})
#: FNV ACBS template flags: traits (race, face, sex, voice), factions, AI packages, inventory, script.
USE_TRAITS, USE_FACTIONS, USE_PACKAGES, USE_INVENTORY, USE_SCRIPT = 0x1, 0x4, 0x20, 0x100, 0x200
#: FNV ACBS template flags: stats (level band), AI data, base data (essential, respawn).
USE_STATS, USE_AI_DATA, USE_BASE_DATA = 0x2, 0x10, 0x80
#: FNV's ten template parts (traits ... script), the same bits in FO4's ACBS; TPTA slots; ACBS byte (xEdit).
TEMPLATE_PARTS, TEMPLATE_SLOTS, ACBS_TEMPLATE = 0x3FF, 13, 14
#: Fallout4.esm's Citizen, the commonest class of its human NPCs that set one (323); DocWeathers' is a turret's.
HUMAN_CLASS = 0x1326B
#: FNV CSSD Weapon Restrictions -> Fallout4.esm style: Melee Only csRaider01Melee, Ranged Only csRaiderRanged.
COMBAT_STYLES = {'1': 0x47165, '2': 0x3183B}
#: The tags vanilla's ZNAM (all 1,745) and ECOR (all 1,339) come right before.
ZNAM_BEFORE, ECOR_BEFORE = (b'NAM5',), (b'FCPL', b'RCLR', b'PRKZ', b'PRKR', b'PRPS', b'FTYP', b'NTRM', b'COCT')
#: The tags vanilla's PRKZ and PRKR come right before (xEdit's NPC_ order; AIDT is in every NPC).
PERKS_BEFORE = (b'PRPS', b'FTYP', b'NTRM', b'COCT', b'CNTO', b'AIDT')
#: derive_formid site of an NPC's outfit (key: the FNV NPC's FormID).
OUTFIT_SITE = 'FNV OTFT'
#: FNV ACBS flag Female; reference record flag Persistent.
FEMALE, PERSISTENT = 0x1, 0x400
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
    [(item, count)]."""
    def edit(subs: bytes) -> bytes:
        """The subrecords with the outfit and inventory replaced."""
        out = b''
        for tag, data in subrecords(subs):
            if tag == b'COCT' and carried:
                out += pack_subrecord('COCT', struct.pack('<I', len(carried)))
                out += b''.join(pack_subrecord('CNTO', struct.pack('<Ii', item, count)) for item, count in carried)
            elif tag == b'DOFT' and outfit:
                out += pack_subrecord('DOFT', struct.pack('<I', outfit))
            elif tag not in (b'COCT', b'CNTO', b'COED', b'DOFT'):
                out += pack_subrecord(tag.decode(), data)
        return out
    return edit


def with_template(template: int, flags: int):
    """A record edit making an NPC a template actor: ACBS template `flags` (FNV's bits are FO4's, TEMPLATE_PARTS),
    TPLT `template` and TPTA naming it for each flagged part, before RNAM as vanilla orders them."""
    flags &= TEMPLATE_PARTS
    tpta = b''.join(struct.pack('<I', template if flags >> bit & 1 else 0) for bit in range(TEMPLATE_SLOTS))

    def edit(subs: bytes) -> bytes:
        """The subrecords with the template set."""
        out = b''
        for tag, data in subrecords(subs):
            if tag == b'ACBS':
                data = data[:ACBS_TEMPLATE] + struct.pack('<H', flags) + data[ACBS_TEMPLATE + 2:]
            elif tag == b'RNAM':
                out += pack_subrecord('TPLT', struct.pack('<I', template)) + pack_subrecord('TPTA', tpta)
            if tag not in (b'TPLT', b'TPTA'):
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


def _traits_templated(rec: dict) -> bool:
    """Whether FNV actor record `rec` takes its traits from its template."""
    return 'TPLT.Template' in rec and bool(int(rec.get('ACBS.TemplateFlags', 0)) & USE_TRAITS)


class Npcs:
    """FO4 NPCs for FNV NPC bases, each written once, and their placed actors."""

    def __init__(self, builder, export_dir: Path, form_map: dict, creatures):
        """Index FNV's NPCs and races; `form_map` maps the FNV forms packages name, `creatures` (creatures.py)
        makes the placed creatures' bases."""
        self.builder, self.export_dir, self.form_map, self.creatures = builder, export_dir, form_map, creatures
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'NPC_')}
        self.races = {int(r['FormID'], 16): r.get('EditorID', '') for r in export_records(export_dir, 'RACE')}
        self.bodies = {rec.form_id: rec for rec, _ in walk(builder.fo4, b'NPC_') if rec.form_id in BODIES.values()}
        self.assets, self.made, self.voices = None, {}, creatures.voices
        self.lists = {int(r['FormID'], 16): r for sig in ('LVLN', 'LVLC') for r in export_records(export_dir, sig)}
        self.made_lists, self.tone_layers = {}, skin_tone_layers(builder.fo4)
        self.styles = {int(r['FormID'], 16): r.get('CSSD.WeaponRestrictions') for r in export_records(export_dir, 'CSTY')}

    def source(self, fnv: int, flag: int) -> 'dict | None':
        """The NPC `fnv` takes part `flag` from (template_source); None if a list."""
        rec = self.records.get(fnv)
        found, left = template_source(self.records, rec, flag) if rec is not None else (None, True)
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
        body = self.bodies[BODIES[ghoul, female]]
        morphs, edit = (self._face(traits, female) if face else (b'', None))
        fid = self.builder.new_id(NPC_KEY.format(fnv))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, body.body, body.flags, f'FNV_{npc["EditorID"]}', npc.get('FULL', ''),
            (FACE_SHAPE if face else frozenset()) | BODY_TIES, morphs,
            composed(edit, with_class, with_factions(self._factions(fnv)), self._packages(fnv), self._inventory(fnv),
                     with_voice(self.voices.of(int(traits.get('VTCK.Voice', '0'), 16))), self._actor_data(fnv),
                     self._combat_style(traits), with_perks(self.builder.perks.teammates.held_by(fnv)))))
        self.builder.counts['NPC_'] += 1
        self.builder.npc_ids[fnv] = fid
        return fid

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
        parts = (with_factions(self._factions(fnv)), self._packages(fnv), self._inventory(fnv),
                 self._actor_data(fnv)) if fnv in self.records else (self.creatures.actor_data(npc, npc, npc),
                                                                     *self.creatures.own_parts(npc, templated=True))
        body = None if fnv in self.records else self.creatures.stand_in(fnv)
        fid = self._template_actor(fnv, npc, template, int(npc.get('ACBS.TemplateFlags', 0)), parts, body)
        self.builder.npc_ids[fnv] = fid
        return fid

    def _template_actor(self, fnv: int, rec: dict, template: int, flags: int, parts: tuple, body=None) -> int:
        """Write a template actor for FNV form `fnv` (`rec`) on `template` with `flags`, then `parts` edits; a copy
        of `body` (a creature's stand-in, whose class and combat style it keeps), else the male NPC body."""
        body, fid = body or self.bodies[BODIES[False, False]], self.builder.new_id(NPC_KEY.format(fnv))
        self.builder.writer.add_record('NPC_', R.clone_npc(
            fid, body.body, body.flags, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''), BODY_TIES, b'',
            composed(*parts, with_template(template, flags), None if body is not self.bodies[BODIES[False, False]]
                     else with_class)))
        self.builder.counts['NPC_ (template actor)'] += 1
        return fid

    def _creature(self, fnv: int) -> 'int | None':
        """The FO4 base of FNV creature or leveled creature list `fnv` (made once); None when it does not convert."""
        if fnv not in self.made:
            rec = self.creatures.records.get(fnv)
            if fnv in self.lists:
                listed = self._list(fnv)
                self.made[fnv] = listed and self._template_actor(fnv, self.lists[fnv], listed, TEMPLATE_PARTS, ())
            elif rec is not None and _traits_templated(rec):
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
            return self._creature(fnv)
        return self._list(fnv) if fnv in self.lists else None

    def _list(self, fnv: int) -> 'int | None':
        """FNV leveled NPC list `fnv` as an FO4 LVLN of its entries that convert, on FNV's FormID; None if none do."""
        if fnv not in self.made_lists:
            rec, fid = self.lists[fnv], self.builder.fnv_id(f'{fnv:08X}')
            self.made_lists[fnv] = fid
            entries = [(level, self._template(form), count) for level, form, count in _entries(rec)]
            entries = [e for e in entries if e[1] is not None]
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
            made = items.item(item)
            if made is not None and items.wearable(item):
                worn.append(made)
            elif made is not None:
                carried.append((made, int(rec[f'Item[{i}].Count'])))
        return with_inventory(self._outfit(fnv, worn), carried)

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

    def _combat_style(self, traits: dict):
        """The edit giving FNV NPC `traits` (its traits source, which holds ZNAM in FNV) the FO4 style of its
        style's weapon restriction (COMBAT_STYLES); None when it keeps the default.
        See: docs/fork/fo4_pipeline.md#combat-styles
        """
        restriction = self.styles.get(int(traits.get('ZNAM.CombatStyle', '0'), 16))
        if restriction not in COMBAT_STYLES:
            return None
        self.builder.counts[f'NPC_ combat style (FNV weapon restriction {restriction})'] += 1
        return R.with_sub(b'ZNAM', struct.pack('<I', COMBAT_STYLES[restriction]), ZNAM_BEFORE)

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
        out = {}
        for cell, ref in built:
            base = self._base_of(int(ref['NAME'], 16))
            if base is None:
                self.builder.counts[self._unbuilt(ref)] += 1
                continue
            slot = out.setdefault(cell, [b'', b''])
            slot[0 if int(ref['RecordFlags']) & PERSISTENT else 1] += self._actor(ref, base, ids, owners)
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
        """The FO4 ACHR of FNV actor `ref` on `base`, with its script, parents and linked reference."""
        fnv = int(ref['NAME'], 16)
        achr = self.builder.new_id(ACHR_KEY.format(ref['FormID']))
        self.builder.actor_ids[ref['FormID']] = achr
        self.builder.scripts.named[ref.get('EditorID', '')] = achr
        script = (self.source(fnv, USE_SCRIPT) if fnv in self.records else self.creatures.records.get(fnv)) or {}
        vmad = self.builder.scripts.vmad(int(script['SCRI'], 16)) if 'SCRI' in script else b''
        linked = ids.get(ref.get('XLKR.LinkedRef'), 0)
        extra = placement(int(ref['FormID'], 16), ids, owners, pose=False)
        extra += pack_subrecord('XLKR', struct.pack('<II', 0, linked)) if linked else b''
        self.builder.counts['ACHR'] += 1
        flags = int(ref['RecordFlags']) & (PERSISTENT | R.INITIALLY_DISABLED)
        flags |= starts_dead(self.records.get(fnv) or self.creatures.records.get(fnv) or {})
        pos, rot = place(ref)
        return R.pack_achr(achr, base, self.lift(ref, pos), rot, vmad, extra, flags)


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
