"""Cross-reference graph for TES4 FormID/EditorID/Script lookups."""

import mmap
import os
import re

from script_convert.constants import (
    PLACED_REF_SIGS, PLAYER_ALIAS_EXTENDS, SCHOOL_ENCHANT_SHADER,
    papyrus_script_name
)
from script_convert.target import variable_type
from script_convert.symbols import command_return_type
from script_convert.command_rows import (
    ACTOR_ONLY_FUNCTIONS, OBJREF_SHARED_FUNCTIONS
)
from tes5_import.base.mesh_bounds import get_mesh_physics_flags
from tes5_import.base.text_reader import parse_export_file, unescape_value
from tes5_import.record_types.world_falloutnv import FALLOUT_ONLY_SIGS
from asset_convert.game_paths import current_namespace
from core.plugin_masters import chain_index_maps, master_chain, master_dir
from core.worker_budget import worker_count
from core.worldspace_names import converted_worldspace_edid, renames_for

# ===========================================================================
# Cross-reference graph builder
# ===========================================================================

# Record types the scan skips entirely: they have no EditorIDs and can never
# be referenced from a script, and together they are ~85% of the export bytes
# (LAND.txt alone is ~1.4 GB).
_SCAN_SKIP_SIGS = {'LAND', 'PGRD', 'ROAD'}

# Byte size of one scan job; big files split across workers at this grain.
_SCAN_CHUNK_BYTES = 16 * 1024 * 1024


def _scan_chain(export_dir: str) -> tuple:
    """(`_export_dirs_with_masters`, the worldspace renames that chain applies)."""
    dirs = _export_dirs_with_masters(export_dir)
    return dirs, renames_for(dirs)


def _export_dirs_with_masters(export_dir: str) -> list:
    """`export_dir` preceded by its masters' export dirs, deepest first.

    Masters come FIRST so the last-wins merge lets an overriding plugin's own
    version of a record win. A master with no export is reported, not skipped silently.
    See: docs/reference/pipeline.md#master-resolution
    """
    dirs = []
    for name in master_chain(export_dir):
        d = master_dir(export_dir, name)
        if os.path.isdir(d):
            dirs.append(d)
        else:
            print(f"    WARNING: master export not found ({d}); "
                  f"script references to {name}'s records will not resolve")
    return dirs + [str(export_dir)]


def _new_scan_out() -> dict:
    return {
        'formid_to_edid': {}, 'edid_to_formid': {},
        'script_formid_to_edid': {}, 'script_formid_to_type': {},
        'record_scri': {}, 'record_base': {}, 'record_type': {},
        'quest_edids': set(), 'npc_formids': set(),
        'mgef_shaders': {}, 'spell_effects': {},
        'global_types': {}, 'global_values': {},
        'pack_type': {}, 'actor_packages': {},
        'actor_speed': {}, 'move_gmsts': {},
        'record_model': {},
        # CELL geometry, for GetInCell: {formid: (is_interior, wrld_fid, x, y)}.
        # An EXTERIOR cell cannot back a Papyrus `Cell` property (see
        # get_cell_family), so its membership test is made from these instead.
        'cell_geom': {},
        # BOOK FormIDs carrying an ENAM: the importer writes these as SCRL, not
        # BOOK, so a property typed from the source signature would not bind.
        'enchanted_books': set(),
        'trigger_blocks': {},
    }


#: Scan tables keyed by FormID.
_FID_KEYED = ('formid_to_edid', 'script_formid_to_edid', 'script_formid_to_type', 'record_scri', 'record_base',
              'record_type', 'record_model', 'cell_geom', 'pack_type', 'actor_packages', 'actor_speed')
#: Lowest FormID a plugin can own; the ids below it are the engine's and never move.
_FIRST_PLUGIN_ID = 0x800


def _master_rekeys(export_dir: str) -> dict:
    """{master dir: its index-byte map}, for masters numbered unlike `export_dir`."""
    return {folder: remap for folder, remap in chain_index_maps(export_dir)
            if any(theirs != ours for theirs, ours in remap.items())}


def _rekeyed_id(text: str, remap: dict) -> str:
    """A master's FormID restated in the dependent's numbering; anything else unchanged."""
    try:
        raw = int(text, 16)
    except (TypeError, ValueError):
        return text
    slot = remap.get(raw >> 24)
    if slot is None or raw < _FIRST_PLUGIN_ID:
        return text
    return '%08X' % (slot << 24 | raw & 0xFFFFFF)


def _rekey_scan(out: dict, remap: dict) -> dict:
    """One master's scan result with every FormID, key or value, moved through `remap`.

    See: docs/commentary/script_convert.md#master-ids-rekeyed
    """
    memo = {}

    def fid(text):
        """`text` rekeyed, remembered."""
        if text not in memo:
            memo[text] = _rekeyed_id(text, remap)
        return memo[text]

    for name in _FID_KEYED:
        out[name] = {fid(key): value for key, value in out[name].items()}
    for name in ('edid_to_formid', 'record_scri', 'record_base'):
        out[name] = {key: fid(value) for key, value in out[name].items()}
    for name in ('npc_formids', 'enchanted_books'):
        out[name] = {fid(value) for value in out[name]}
    out['actor_packages'] = {key: [fid(p) for p in packs] for key, packs in out['actor_packages'].items()}
    out['cell_geom'] = {key: (geom[0], fid(geom[1]), *geom[2:]) for key, geom in out['cell_geom'].items()}
    out['mgef_shaders'] = {key: (fid(shader), fid(ench), school)
                           for key, (shader, ench, school) in out['mgef_shaders'].items()}
    return out


_EFFECT_FIELD_RE = re.compile(r'Effect\[(\d+)\]\.(EFID|ActorValue)$')


def _int_or(text, default: int) -> int:
    """`text` as an int, or `default` when it is absent or not a number."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _spell_effect_list(rec: dict) -> list:
    """[(effect code, actor value int), ...] in Effect[n] order."""
    effects: list[tuple[str, int]] = []
    for key, val in rec.items():
        m = _EFFECT_FIELD_RE.match(key)
        if not m:
            continue
        idx = int(m.group(1))
        while len(effects) <= idx:
            effects.append(('', -1))
        code, av = effects[idx]
        effects[idx] = ((val, av) if m.group(2) == 'EFID'
                        else (code, _int_or(val, av)))
    return effects


def index_record_details(tables: dict, sig: str, formid: str, edid: str,
                         rec: dict, rekey=lambda v: v) -> None:
    """Fill the tables a record's own fields feed: model, MGEF shader, SPEL effects, GLOB, enchanted BOOK.

    `tables` maps table name -> dict/set (a scan result, or a graph's `vars()`), so the
    CLI scan and the importer's hand-built graph index these identically; `rekey`
    corrects a master record's id fields.
    See: docs/commentary/tes5_import_pipeline.md#phase-0-xref-mirrors-cli-scan
    """
    model = rec.get('Model.MODL')
    if model:
        tables['record_model'][formid] = model
    low = edid.lower() if edid else ''
    if sig == 'MGEF' and low:
        tables['mgef_shaders'][low] = (
            rekey(rec.get('DATA.EffectShader') or ''),
            rekey(rec.get('DATA.EnchantEffect') or ''),
            _int_or(rec.get('DATA.School'), -1))
    elif sig == 'SPEL' and low:
        effects = _spell_effect_list(rec)
        if effects:
            tables['spell_effects'][low] = effects
    elif sig == 'GLOB' and low:
        if rec.get('FNAM.Type'):
            tables['global_types'][low] = rec['FNAM.Type'].strip()
        try:
            tables['global_values'][low] = float(rec.get('FLTV.Value'))
        except (TypeError, ValueError):
            pass
    elif sig == 'BOOK' and (rec.get('ENAM') or '').strip().strip('0'):
        tables['enchanted_books'].add(formid)
    _index_move_speed(tables, sig, formid, low, rec)


#: The GMSTs of TES4's walk-speed formula: walk = Min + (Max - Min) * Speed / 100.
_MOVE_GMSTS = frozenset({'fmovecharwalkmin', 'fmovecharwalkmax',
                         'fmovecreaturewalkmin', 'fmovecreaturewalkmax'})


def _index_move_speed(tables: dict, sig: str, formid: str, low: str, rec: dict) -> None:
    """An actor's authored Speed attribute, or a walk-speed GMST's value."""
    if sig in ('NPC_', 'CREA'):
        speed = _int_or(rec.get('DATA.Speed'), None)
        if speed is not None:
            tables['actor_speed'][formid] = speed
    elif sig == 'GMST' and low in _MOVE_GMSTS:
        try:
            tables['move_gmsts'][low] = float(rec.get('DATA.Value'))
        except (TypeError, ValueError):
            pass




#: An OBSE `begin Function` header at a line start, in raw or export-escaped (`\n`) SCTX text.
_UDF_BLOCK_RE = re.compile(r'(?:^|\\n)(?:\s|\\t)*begin\s+function\b', re.I | re.M)
#: A trigger block header (OnTriggerEnter or OnTrigger) in raw or export-escaped SCTX text.
_TRIGGER_BLOCK_RE = re.compile(r'(?:^|\\n)(?:\s|\\t)*begin\s+(ontriggerenter|ontrigger)\b', re.I | re.M)

#: SCHR.Type of a quest script.
QUEST_SCRIPT_TYPE = 1


def is_function_script(sctx: str) -> bool:
    """True for an OBSE user-function script (raw or export-escaped SCTX)."""
    return bool(_UDF_BLOCK_RE.search(sctx or ''))


def authored_trigger_blocks(sctx: str) -> frozenset:
    """The trigger blocks a script authors: 'ontriggerenter' and/or 'ontrigger'."""
    return frozenset(b.lower() for b in _TRIGGER_BLOCK_RE.findall(sctx or ''))


def hosted_script_type(schr_type: int, sctx: str) -> int:
    """SCHR type a script is HOSTED as; an OBSE function script is a quest's.

    See: docs/commentary/script_convert.md#udf-host-quest
    """
    return QUEST_SCRIPT_TYPE if is_function_script(sctx) else schr_type


def _record_fields(lines: list) -> dict:
    """A record's KEY=VALUE lines as a dict; a repeated key keeps its last value."""
    return dict(line.rstrip().partition('=')[::2] for line in lines if '=' in line)


def _int_field(rec: dict, key: str, base: int = 10):
    """The field's leading number, or None when it is absent or not a number."""
    try:
        return int(rec[key].split()[0], base)
    except (KeyError, ValueError, IndexError):
        return None


def _scan_scpt(rec: dict, formid: str, edid: str, out: dict) -> None:
    """A script's EditorID, hosting type and authored trigger blocks."""
    if edid:
        out['script_formid_to_edid'][formid] = edid
    schr_type = _int_field(rec, 'SCHR.Type')
    if schr_type is not None:
        out['script_formid_to_type'][formid] = hosted_script_type(
            schr_type, rec.get('SCTX', ''))
    blocks = authored_trigger_blocks(rec.get('SCTX', ''))
    if edid and blocks:
        out['trigger_blocks'][edid.lower()] = blocks


def _scan_cell(rec: dict, formid: str, _edid: str, out: dict) -> None:
    """A cell's interior flag, worldspace and grid position, for GetInCell."""
    flags = _int_field(rec, 'DATA.Flags', 0)
    if flags is not None:
        out['cell_geom'][formid] = (bool(flags & 1), rec.get('ParentWRLD') or '',
                                    _int_field(rec, 'XCLC.X'), _int_field(rec, 'XCLC.Y'))


def _scan_actor(rec: dict, formid: str, _edid: str, out: dict) -> None:
    """An NPC_/CREA and its AI package list."""
    out['npc_formids'].add(formid)
    packs = [m.group(0) for k, v in rec.items() if k.startswith('AIPackage[')
             for m in [re.match(r'\w+', v)] if m]
    if packs:
        out['actor_packages'][formid] = packs


def _scan_pack(rec: dict, formid: str, _edid: str, out: dict) -> None:
    """A package's procedure type."""
    pkdt_type = _int_field(rec, 'PKDT.Type')
    if pkdt_type is not None:
        out['pack_type'][formid] = pkdt_type


def _scan_qust(_rec: dict, _formid: str, edid: str, out: dict) -> None:
    """A quest's EditorID."""
    if edid:
        out['quest_edids'].add(edid.lower())


#: Signature -> the indexer for the fields only that record type carries.
_SIG_SCANNERS = {'SCPT': _scan_scpt, 'CELL': _scan_cell, 'NPC_': _scan_actor,
                 'CREA': _scan_actor, 'PACK': _scan_pack, 'QUST': _scan_qust}


def _scan_record_lines(sig: str, lines: list, out: dict):
    """Scan one record's KEY=VALUE lines into the partial result dicts."""
    rec = _record_fields(lines)
    formid = rec.get('FormID')
    if not formid:
        return
    edid = rec.get('EditorID')
    if edid:
        out['formid_to_edid'][formid] = edid
        out['edid_to_formid'][edid.lower()] = formid
    scanner = _SIG_SCANNERS.get(sig)
    if scanner:
        scanner(rec, formid, edid, out)
    index_record_details(out, sig, formid, edid, rec)
    if rec.get('SCRI'):
        out['record_scri'][formid] = rec['SCRI']
    if rec.get('NAME') and sig in PLACED_REF_SIGS:
        out['record_base'][formid] = rec['NAME']
    out['record_type'][formid] = sig


def _scan_range(args: tuple) -> dict:
    """Scan the records whose BEGIN delimiter starts in [start, end).

    args = (fpath, sig, start, end). Module-level so it is picklable for
    ProcessPoolExecutor; boundary rule matches text_reader.parse_file_range.
    """

    from tes5_import.base.text_reader import (DELIM_BEGIN, DELIM_END,
                                              find_delim_line)

    fpath, sig, start, end = args
    out = _new_scan_out()
    try:
        f = open(fpath, 'rb')
    except OSError:
        return out
    with f:
        try:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:  # empty file
            return out
        try:
            begin = find_delim_line(mm, DELIM_BEGIN, start)
            while begin != -1 and begin < end:
                nl = mm.find(b'\n', begin)
                if nl < 0:
                    break
                rec_end = find_delim_line(mm, DELIM_END, nl + 1)
                if rec_end < 0:
                    break
                block = mm[nl + 1:rec_end].decode('utf-8', errors='replace')
                _scan_record_lines(sig, block.split('\n'), out)
                begin = find_delim_line(mm, DELIM_BEGIN,
                                         rec_end + len(DELIM_END))
        finally:
            mm.close()
    return out


def _model_is_held(model: str) -> bool:
    """Does the converted NIF of this AUTHORED model path hold a keyframed body (physics bit 1)?"""
    if not model:
        return False
    key = model.replace('\\\\', '/').replace('\\', '/').lower().lstrip('/')
    return bool(get_mesh_physics_flags(current_namespace() + '/' + key) & 2)


class CrossRefGraph:
    """Builds FormID->EditorID and EditorID->ScriptName lookup tables."""

    def __init__(self):
        self.formid_to_edid: dict[str, str] = {}
        self.edid_to_formid: dict[str, str] = {}
        #: Source worldspace EDID -> converted EDID; see core/worldspace_names.py.
        self.worldspace_renames: dict[str, str] = renames_for()
        self.script_formid_to_edid: dict[str, str] = {}
        self.script_formid_to_type: dict[str, int] = {}
        self.record_scri: dict[str, str] = {}  # record FormID -> SCRI FormID
        self.record_type: dict[str, str] = {}  # record FormID -> record Signature
        # record FormID -> Model.MODL path as authored (backslashes, any case).
        # Lets the script converter ask the CONVERTED mesh what its physics are
        # (held-until-scripted trap/breakaway), which the animation-group name
        # cannot tell it — see the playgroup release in converter.py.
        self.record_model: dict[str, str] = {}
        # CELL FormID -> (is_interior, parent WRLD FormID, grid X, grid Y).
        # Backs the exterior half of get_cell_family (see there).
        self.cell_geom: dict[str, tuple] = {}
        # BOOK records with an ENAM: written as SCRL, so `Book` would not bind.
        self.enchanted_books: set[str] = set()
        #: script EditorID (lower) -> the trigger blocks it authors ('ontriggerenter', 'ontrigger').
        self.trigger_blocks: dict[str, frozenset] = {}
        self.record_base: dict[str, str] = {}  # placed ref FormID -> base record FormID (NAME)
        # base FormID (upper) -> its ONE placed ref FormID; lazily inverted
        # from record_base by unique_placed_ref().
        self._base_to_unique_ref: 'dict[str, str] | None' = None
        self.quest_edids: set[str] = set()
        #: Fallout 4: the movies the build ships (fo4_import.base.bink.movie_key spellings).
        self.movies: frozenset = frozenset()
        self.npc_formids: set[str] = set()
        # Cross-script ref-as-int analysis: set of (script_name_lower, var_name_lower)
        # where the TES4 `ref` variable is only ever assigned/compared with integers
        self.ref_as_int: set[tuple[str, str]] = set()
        # Cross-script ref-as-BASE-FORM analysis: (script_low, var_low) where the
        # `ref` variable is assigned a BASE record (a MISC/SPEL/WEAP/... item),
        # not a placed reference. Papyrus rejects those into an ObjectReference
        # variable, and the assignment can live in a DIFFERENT script than the
        # declaration (moXscrXtrapXwritedynamicdata writes probe MISCs into
        # moXscrXtrapXmemorystorage.XCURRENTprobeID), so the owning script
        # cannot detect it alone. Such a variable is declared Form.
        self.ref_as_base_form: set[tuple[str, str]] = set()
        # Per-script ref-typed variable names (populated by build_ref_as_int_map)
        self.script_ref_vars: dict[str, set[str]] = {}
        # Cross-script variable accesses: script_name_lower -> set of var_name_lower
        # Variables that are accessed from OTHER scripts (need to be Properties)
        self.cross_script_vars: dict[str, set[str]] = {}
        # Per-script ALL variable declarations: script_name_lower -> dict(var_low -> type_str)
        self.script_all_vars: dict[str, dict[str, str]] = {}
        # Per-script `ref` variables the script itself uses as an ACTOR, i.e. it
        # calls an Actor-only method on them (`myRef.startcombat`).  Those are
        # the only remote ref vars a writer may downcast with `as Actor`; a ref
        # var that only ever holds a marker (MQ16OblivionGate1Script's
        # mySpawnMarker) stays ObjectReference and the cast would null it out.
        self.script_actor_vars: dict[str, set[str]] = {}
        # MGEF EditorID (lower) -> (EffectShader fid, EnchantEffect fid, school int)
        # Used to convert pme/PlayMagicEffectVisuals into EffectShader.Play().
        self.mgef_shaders: dict[str, tuple[str, str, int]] = {}
        # SPEL EditorID (lower) -> [(effect code, actor value int), ...]
        # Used to convert IsSpellTarget into a HasMagicEffect check on the
        # spell's first converted (Skyrim) magic effect.
        self.spell_effects: dict[str, list[tuple[str, int]]] = {}
        # GLOB EditorID (lower) -> TES4 FNAM type char ('s' short, 'l' long,
        # 'f' float).  Decides whether a GetValue() read needs an `as Int`:
        # truncating a float global silently breaks fractional comparisons.
        self.global_types: dict[str, str] = {}
        # GLOB EditorID (lower) -> FLTV value as authored by the plugin.
        # Needed because several TES4 timing idioms hardcode a REAL-SECONDS
        # constant that the author tuned against their own TimeScale (see
        # the chime debounce).  Nehrim ships TimeScale
        # 10, Oblivion 30, so the same script means different things in each.
        self.global_values: dict[str, float] = {}
        # PACK FormID -> PKDT.Type (0 Find, 1 Follow, 2 Escort, 3 Eat,
        # 4 Sleep, 5 Wander, 6 Travel, 7 Accompany, 8 Use Item At, 9 Ambush,
        # 10 Flee Not Combat, 11 Cast Magic — xEdit wbPackageTypeEnum).
        # TES4 `GetCurrentAIPackage` returns this code; Skyrim's
        # Actor.GetCurrentPackage() returns the Package form instead and no
        # Papyrus native exposes a package's type, so a numeric comparison is
        # reconstructed as a disjunction over the actor's own packages of that
        # type (get_actor_packages_of_type).
        self.pack_type: dict[str, int] = {}
        # NPC_/CREA FormID -> [PACK FormID, ...] in AIPackage[n] order.
        self.actor_packages: dict[str, list] = {}
        #: NPC_/CREA FormID -> authored DATA.Speed attribute.
        self.actor_speed: dict[str, int] = {}
        #: Walk-speed GMST (lower EditorID) -> value, for the TES4 speed formula.
        self.move_gmsts: dict[str, float] = {}

    def load_from_export(self, export_dir: str, workers: int = None):
        """Load the graph from `export_dir` and every transitive master's export, in the plugin's numbering.

        Masters merge first and the plugin last, so its own version of a record wins. Files are scanned
        in record-aligned byte ranges across a process pool.
        See: docs/commentary/script_convert.md#master-ids-rekeyed
        """
        if not os.path.isdir(export_dir):
            return

        jobs, remaps = [], []
        dirs, self.worldspace_renames = _scan_chain(export_dir)
        rekeys = _master_rekeys(export_dir)
        for d in dirs:
            for fname in sorted(os.listdir(d)):
                if not fname.endswith('.txt'):
                    continue
                sig = fname[:-4]
                if sig in _SCAN_SKIP_SIGS:
                    continue
                fpath = os.path.join(d, fname)
                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    continue
                for start in range(0, size, _SCAN_CHUNK_BYTES):
                    jobs.append((fpath, sig,
                                 start, min(start + _SCAN_CHUNK_BYTES, size)))
                    remaps.append(rekeys.get(d))

        if workers is None:
            workers = worker_count()
        workers = min(workers, max(1, len(jobs)))
        if workers <= 1 or len(jobs) <= 2:
            self._merge_scans(map(_scan_range, jobs), remaps)
        else:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as ex:
                self._merge_scans(ex.map(_scan_range, jobs), remaps)

    def _merge_scans(self, results, remaps: list) -> None:
        """Fold the scan results in job order (last wins), master ids restated."""
        for out, remap in zip(results, remaps):
            self._merge_scan(_rekey_scan(out, remap) if remap else out)

    def _merge_scan(self, out: dict):
        """Fold one scan-range result (see _scan_range) into this graph."""
        self.formid_to_edid.update(out['formid_to_edid'])
        self.edid_to_formid.update(out['edid_to_formid'])
        self.script_formid_to_edid.update(out['script_formid_to_edid'])
        self.script_formid_to_type.update(out['script_formid_to_type'])
        self.record_scri.update(out['record_scri'])
        self.record_base.update(out['record_base'])
        self.record_type.update(out['record_type'])
        self.record_model.update(out['record_model'])
        self.cell_geom.update(out['cell_geom'])
        self.enchanted_books.update(out['enchanted_books'])
        self.trigger_blocks.update(out['trigger_blocks'])
        self.quest_edids.update(out['quest_edids'])
        self.npc_formids.update(out['npc_formids'])
        self.mgef_shaders.update(out['mgef_shaders'])
        self.spell_effects.update(out['spell_effects'])
        self.global_types.update(out['global_types'])
        self.global_values.update(out['global_values'])
        self.pack_type.update(out['pack_type'])
        self.actor_packages.update(out['actor_packages'])
        self.actor_speed.update(out['actor_speed'])
        self.move_gmsts.update(out['move_gmsts'])

    def get_extends_class(self, script_formid: str) -> str:
        """The Papyrus extends class for a script.

        For a type-0 script the base must be one EVERY attaching record
        can bind, since Papyrus refuses a script whose declared base
        does not match the form.  A script attached ONLY to the player's
        base NPC_ extends the alias type instead, because the importer
        rehosts it on a quest's PlayerRef alias.

        See: docs/commentary/script_convert.md#player-base-script-needs-quest-alias
        """
        schr_type = self.script_formid_to_type.get(script_formid, 0)

        if schr_type == 1:
            return 'Quest'
        if schr_type == 256:
            return 'ActiveMagicEffect'

        attached = self.attached_records(script_formid)
        sigs = self.attached_signatures(script_formid)
        if 'QUST' in sigs:
            return 'Quest'

        if attached and all(self._is_player_base(f) for f in attached):
            return PLAYER_ALIAS_EXTENDS

        if sigs & {'NPC_', 'CREA'} and not (sigs - {'NPC_', 'CREA'}):
            return 'Actor'

        return 'ObjectReference'

    def attached_records(self, script_formid: str) -> list:
        """Every record whose SCRI names `script_formid`; the index is built on first use."""
        index = getattr(self, '_attached_index', None)
        if index is None:
            index = {}
            for rec_fid, scri_fid in self.record_scri.items():
                index.setdefault(scri_fid, []).append(rec_fid)
            self._attached_index = index
        return index.get(script_formid, [])

    def is_fallout(self) -> bool:
        """Whether the scanned plugin is FO3/FNV: it holds a record type only they have; cached."""
        found = getattr(self, '_is_fallout', None)
        if found is None:
            found = self._is_fallout = not set(FALLOUT_ONLY_SIGS).isdisjoint(self.record_type.values())
        return found

    def attached_signatures(self, script_formid: str) -> set:
        """Record signatures of every record the script is attached to."""
        return {self.record_type.get(rec_fid, '')
                for rec_fid in self.attached_records(script_formid)}

    @staticmethod
    def _is_player_base(rec_fid: str) -> bool:
        """True for the player's base NPC_ record (TES4 FormID 0x00000007)."""
        try:
            return (int(rec_fid, 16) & 0x00FFFFFF) == 0x07
        except (TypeError, ValueError):
            return False

    # TES4 magic-school enum -> the EFSH each school's enchantment glow uses.
    # Fallback for MGEFs with neither an EffectShader nor an EnchantEffect
    # (bound armor, summons): the school glow is what Oblivion shows on the
    # enchant anyway, and every one of these EditorIDs exists in Oblivion.esm.
    def get_mgef_shader_edid(self, code: str) -> str:
        """EFSH EditorID for a TES4 magic-effect code (pme/sme argument).

        Preference order mirrors what Oblivion's PlayMagicEffectVisuals shows:
        the effect's own EffectShader, else its EnchantEffect shader, else the
        school's enchantment glow.  Returns '' if the code is unknown.
        """
        entry = self.mgef_shaders.get(code.lower())
        if not entry:
            return ''
        shader_fid, ench_fid, school = entry
        for fid in (shader_fid, ench_fid):
            if fid and int(fid, 16) != 0:
                edid = self.formid_to_edid.get(fid, '')
                if edid:
                    return edid
        fallback = SCHOOL_ENCHANT_SHADER.get(school, '')
        if fallback and fallback in self.edid_to_formid:
            return self.formid_to_edid.get(self.edid_to_formid[fallback], '')
        return ''

    def is_quest_ref(self, name: str) -> bool:
        """Check if a name refers to a known quest."""
        return name.lower() in self.quest_edids

    def unique_placed_ref(self, base_fid: str) -> str:
        """The ONE placed reference of a base record, or '' when there is none
        or more than one.

        Oblivion resolves a unique actor's base EditorID to its placed
        instance, so a script property that names an NPC_/CREA base means the
        ACHR/ACRE — Skyrim's VM refuses the base into a reference-typed
        property and it reads None (see constants.wants_placed_reference).
        Ambiguity binds to nothing new: with several placements the base is
        returned unchanged by the caller, exactly as before this existed.
        """
        if self._base_to_unique_ref is None:
            first: dict[str, str] = {}
            dup: set[str] = set()
            for ref_fid, b in self.record_base.items():
                key = (b or '').upper()
                if not key:
                    continue
                if key in first:
                    dup.add(key)
                else:
                    first[key] = ref_fid
            self._base_to_unique_ref = {k: v for k, v in first.items()
                                        if k not in dup}
        return self._base_to_unique_ref.get((base_fid or '').upper(), '')

    def get_quest_script_type(self, quest_name: str) -> str:
        """Get the Papyrus script class name for a quest, e.g. 'TES4_MyQuestScript'.
        Returns 'Quest' if no attached script is found."""
        low = quest_name.lower()
        fid = self.edid_to_formid.get(low, '')
        if not fid:
            return 'Quest'
        scri_fid = self.record_scri.get(fid, '')
        if not scri_fid:
            return 'Quest'
        script_edid = self.script_formid_to_edid.get(scri_fid, '')
        if not script_edid:
            return 'Quest'
        return papyrus_script_name(script_edid)

    def get_cell_family(self, cell_name: str) -> list:
        """CELL EditorIDs that TES4 `GetInCell <cell_name>` matches.

        TES4 matches GetInCell by EditorID PREFIX, not by identity, so
        `GetInCell Chorrol` is true in all 86 cells whose EditorID starts with
        "Chorrol" (ChorrolCastle, ChorrolMagesGuild, ...).  Oblivion leans on
        this hard: 62 CELL records exist purely as the named anchor for a
        family and hold no refs at all, several saying so outright
        (`FULL=Dummy cell for GetInCell`).  Those anchors are cells the player
        can never stand in, so translating the call as a single equality
        against the named cell yields a condition that is permanently false.

        Returns the matching EditorIDs (original case), the exact-name match
        first so a single-cell result keeps its identity.  Empty if unknown.
        """
        low = cell_name.lower()
        fids = self.record_type
        out = []
        for edid_low, fid in self.edid_to_formid.items():
            if not edid_low.startswith(low):
                continue
            if fids.get(fid, '') != 'CELL':
                continue
            out.append(self.formid_to_edid.get(fid, ''))
        out = [e for e in out if e]
        out.sort(key=lambda e: (e.lower() != low, e.lower()))
        return out

    def split_cell_family(self, cell_name: str) -> tuple:
        """get_cell_family split into (interior EditorIDs, exterior grid keys).

        A Papyrus `Cell` property only ever binds to an INTERIOR cell. Every
        vanilla Skyrim script bears this out -- all 43 of its Cell properties
        name interiors (HelgenKeep, Jorrvaskr, MarkarthAbandonedHouse, ...) and
        not one names an exterior. Declaring a property for an exterior grid
        cell produces, at runtime,

            Property <X> ... cannot be bound because (<fid>) is not the right
            type

        and the property reads None thereafter. That was 773 of the binding
        failures in one session, all of them exterior cells, while the
        interiors of the very same families bound fine (MS08BoatScript: 44
        interior OK, 41 exterior failed, no exceptions).

        Exteriors are still part of the TES4 prefix match, so dropping them
        would quietly narrow the test. They are returned as
        (worldspace EditorID, x, y) grid keys instead, which the emitted helper
        compares against the ref's own worldspace and grid position -- an exact
        equivalent that needs no property binding.
        """
        interior, exterior = [], []
        for edid in self.get_cell_family(cell_name):
            fid = self.edid_to_formid.get(edid.lower(), '')
            geom = self.cell_geom.get(fid)
            if geom is None:
                # No geometry recorded: treat as interior, which is the
                # behaviour before this split and still binds when correct.
                interior.append(edid)
                continue
            is_int, wrld_fid, x, y = geom
            if is_int:
                interior.append(edid)
                continue
            wrld_edid = converted_worldspace_edid(
                self.formid_to_edid.get(wrld_fid, ''), self.worldspace_renames)
            if x is None or y is None:
                # An exterior with no XCLC is the worldspace's own persistent
                # "dummy cell". It holds no grid square, so the faithful test is
                # membership of the WORLDSPACE itself -- and it still cannot
                # back a Cell property, so it must not fall through to one.
                if wrld_edid:
                    exterior.append((wrld_edid, None, None))
                continue
            exterior.append((wrld_edid, x, y))
        return interior, exterior

    def get_script_owner_packages_of_type(self, script_edid: str,
                                          pkg_type: int) -> list:
        """Same as get_actor_packages_of_type for a BARE (self) call.

        A bare `GetCurrentAIPackage` runs on whatever actor the script is
        attached to, so the owner is found by walking SCRI back to the
        NPC_/CREA that names this script.  When the script is attached to more
        than one actor the union is returned: the test must be true whenever
        ANY of them is running a package of that type, and the disjunction the
        caller emits is exactly that.
        """
        out = []
        for actor_fid in self.script_owner_actors(script_edid):
            for pack_fid in self.actor_packages.get(actor_fid, ()):
                if self.pack_type.get(pack_fid) != pkg_type:
                    continue
                edid = self.formid_to_edid.get(pack_fid, '')
                if edid and edid not in out:
                    out.append(edid)
        return out

    def script_owner_actors(self, script_edid: str) -> list:
        """FormIDs of the records whose SCRI names the script `script_edid`."""
        want = script_edid.lower()
        script_fid = next((fid for fid, edid in self.script_formid_to_edid.items()
                           if edid.lower() == want), '')
        return [fid for fid, scri in self.record_scri.items()
                if script_fid and scri == script_fid]

    def actor_formid(self, name: str) -> str:
        """The FormID `name` names, following a placed reference to its base."""
        fid = self.edid_to_formid.get(name.lower(), '')
        return self.record_base.get(fid, fid)

    def walk_speed_formula(self, actor_fids) -> tuple | None:
        """(authored Speed, walk min, walk max) shared by every actor, else None.

        See: docs/commentary/script_convert.md#speed-write-becomes-speedmult
        """
        forms = {(self.actor_speed.get(f), self.record_type.get(f)) for f in actor_fids}
        if len(forms) != 1:
            return None
        speed, sig = forms.pop()
        kind = 'creature' if sig == 'CREA' else 'char'
        low, high = (self.move_gmsts.get(f'fmove{kind}walk{end}') for end in ('min', 'max'))
        if speed is None or low is None or high is None:
            return None
        return speed, low, high

    def get_actor_packages_of_type(self, actor_name: str, pkg_type: int) -> list:
        """PACK EditorIDs of `actor_name`'s own packages whose PKDT.Type matches.

        TES4 `GetCurrentAIPackage` returns the running package's TYPE code;
        Skyrim's `Actor.GetCurrentPackage()` returns the Package form and
        neither vanilla `Package.psc` nor SKSE exposes its type, so the numeric
        comparison has no direct equivalent.  It is reconstructed instead: the
        set of packages an actor can be running is fixed at conversion time by
        its own AIPackage list, so `x.GetCurrentAIPackage == 5` becomes an
        equality against each of x's Wander packages, OR'd together.

        Scoping to the actor's OWN list is what makes this tractable — the
        plugin has 1,820 Wander packages overall but the affected actors carry
        between one and three apiece.

        `actor_name` may name the base NPC_/CREA or a placed ACHR/ACRE, which
        is followed through NAME.  Returns [] when the actor or its packages
        are unknown, which keeps the caller on the old no-op path.
        """
        fid = self.edid_to_formid.get(actor_name.lower(), '')
        if not fid:
            return []
        if fid not in self.actor_packages:
            base = self.record_base.get(fid, '')
            if base:
                fid = base
        out = []
        for pack_fid in self.actor_packages.get(fid, ()):
            if self.pack_type.get(pack_fid) != pkg_type:
                continue
            edid = self.formid_to_edid.get(pack_fid, '')
            if edid:
                out.append(edid)
        return out

    def get_base_signature(self, name: str) -> str:
        """Record signature a name ultimately refers to ('ACTI', 'NPC_', ...).

        For a placed reference (REFR/ACHR/ACRE) this follows the NAME chain to
        the BASE record, so `CGPrisonSecretWallRef` reports 'ACTI' (its base
        `prisonSecretWall01`) rather than 'REFR'. Returns '' when unknown.

        Callers use this to tell an ANIMATED OBJECT from an ACTOR, which decide
        completely different animation APIs — see PlayGroup in converter.py.
        """
        fid = self.edid_to_formid.get(name.lower(), '')
        if not fid:
            return ''
        base_fid = self.record_base.get(fid, '')
        if base_fid:
            return self.record_type.get(base_fid, '')
        return self.record_type.get(fid, '')

    def needs_havok_release(self, name: str) -> bool:
        """True if *name*'s mesh ships bodies HELD until a script releases them.

        The converted NIF carries KEYFRAMED bodies that kept a non-zero mass —
        `physics_flags_from_data` bit 1 — which `_convert_collision` writes for
        breakaway pieces and constrained trap islands only.  Those are exactly
        the objects whose `playgroup` must be followed by
        SetMotionType(Motion_Dynamic); every other animated object converts to
        a mass-0 keyframed body that cannot fall no matter what the script does.

        Resolves through a placed reference to its base record, like
        get_base_signature, so `CTrapLogs01Ref.playgroup` works.
        """
        fid = self.edid_to_formid.get(name.lower(), '')
        if not fid:
            return False
        return _model_is_held(
            self.record_model.get(self.record_base.get(fid, '') or fid, ''))

    def script_owner_needs_havok_release(self, script_edid: str) -> bool:
        """needs_havok_release for a BARE (self) `playgroup`.

        A bare call runs on whatever record the script is attached to, so walk
        SCRI back to the owners.  True if ANY owner's mesh is held — a script
        shared between a held trap and something else still has to release the
        trap, and the release is inert on anything that is not held.
        """
        want = (script_edid or '').lower()
        if not want:
            return False
        script_fid = ''
        for fid, edid in self.script_formid_to_edid.items():
            if edid.lower() == want:
                script_fid = fid
                break
        if not script_fid:
            return False
        return any(_model_is_held(self.record_model.get(rec_fid, ''))
                   for rec_fid, scri in self.record_scri.items()
                   if scri == script_fid)

    def record_script_edid(self, name: str) -> str:
        """EditorID of the script on record `name` (a placed ref falls back to its base's); '' for none.

        The player is a converter keyword (`Game.GetPlayer()`), never a bound
        property, so it never takes a script even where its base NPC_ has one.
        """
        low = name.lower()
        if low in ('player', 'playerref'):
            return ''
        fid = self.edid_to_formid.get(low, '')
        scri_fid = self.record_scri.get(fid, '') or self.record_scri.get(self.record_base.get(fid, ''), '')
        return self.script_formid_to_edid.get(scri_fid, '') if scri_fid else ''

    def get_record_script_type(self, name: str) -> str:
        """The Papyrus script class attached to record `name`, '' when it has none."""
        script_edid = self.record_script_edid(name)
        return papyrus_script_name(script_edid) if script_edid else ''

    def build_ref_as_int_map(self, scpt_path: str):
        """Type TES4 `ref` variables from every script that touches them: Int when only ever set to numbers,
        a base form when set to a base record, and a Property when another script reads or writes them.

        The masters' SCPT sources are read first (an override plugin's script reaching into a master's script
        variable needs that script's declarations; a plugin's own SCPT must win). The plugin's INFO and QUST
        result scripts count as uses too.

        See: docs/fork/fo4_script_compile.md#ref-as-number
        """
        export_dir = os.path.dirname(scpt_path)
        records = []
        for d in _export_dirs_with_masters(export_dir):
            p = os.path.join(d, os.path.basename(scpt_path))
            if os.path.isfile(p):
                records.extend(parse_export_file(p))
        sources, self.script_ref_vars, self.script_all_vars, self.script_actor_vars = _script_declarations(records)
        if not self.script_ref_vars:
            return
        usage: dict[tuple[str, str], set[str]] = {}
        ref_flow: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for scn_low, sctx in sources.items():
            self._scan_ref_usage(scn_low, sctx, usage, ref_flow)
        _scan_plugin_result_scripts(export_dir, lambda text: self._scan_ref_usage('', text, usage, ref_flow))
        self._classify_ref_usage(usage, ref_flow)
        self.cross_script_vars = self._cross_script_vars(sources.values(), export_dir)

    def _script_of(self, owner: str, var: str, declared: dict, own: str = '') -> str:
        """The script (lowercase) declaring `var` for `owner` (a script name, or a record whose SCRI does), or ''.
        `own`, the scanning script itself, never resolves through a record."""
        if var in declared.get(owner, ()):
            return owner
        if owner == own:
            return ''
        scri = self.record_scri.get(self.edid_to_formid.get(owner, ''), '')
        script = self.script_formid_to_edid.get(scri, '').lower() if scri else ''
        return script if var in declared.get(script, ()) else ''

    def _scan_ref_usage(self, scn_low: str, text: str, usage: dict, ref_flow: dict) -> None:
        """Note each use of a declared ref variable in `text`, script `scn_low` ('' for a result script):
        `var.Call` is a reference use, and each `set [owner.]var to value` says what the value holds."""
        own_refs = self.script_ref_vars.get(scn_low, ())
        for raw_line in text.split('\n'):
            line = raw_line.strip()
            if not line or line.startswith(';'):
                continue
            for ref_var in own_refs:
                if re.search(r'\b' + re.escape(ref_var) + r'\.\w+', line, re.IGNORECASE):
                    usage.setdefault((scn_low, ref_var), set()).add('ref')
            sm = _SET_RE.match(line)
            if sm:
                self._note_set(sm, scn_low, usage, ref_flow)

    def _note_set(self, match, scn_low: str, usage: dict, ref_flow: dict) -> None:
        """Record what one `set [owner.]var to value` says about a declared ref variable, and the variable it
        copies from (the edge a base form spreads along)."""
        var = match.group(2).lower()
        owner = self._script_of((match.group(1) or scn_low).lower(), var, self.script_ref_vars, scn_low)
        if not owner:
            return
        value = match.group(3).split(';', 1)[0].strip()
        kinds = self._set_value_kinds(value)
        usage.setdefault((owner, var), set()).update(kinds)
        source = self._flow_source(value, scn_low) if 'ref' in kinds else None
        if source:
            ref_flow.setdefault((owner, var), set()).add(source)

    def _set_value_kinds(self, value: str) -> set:
        """What `set x to <value>` puts in x: {'zero'}, {'int'} (a number, arithmetic, a numeric command such as
        `GetItemCount`, or a global), or {'ref'} plus 'baseform' when the value names a base record."""
        if _NUMBER_RE.match(value):
            return {'zero'} if value == '0' else {'int'}
        command = _COMMAND_RE.match(value)
        if ('"' not in value and _ARITHMETIC_RE.search(value)) or (
                command and command_return_type(command.group(1)) in ('Int', 'Float')):
            return {'int'}
        name = value.strip('"')
        if not _WORD_RE.match(name):
            return {'ref'}
        rtype = self.record_type.get(self.edid_to_formid.get(name.lower(), ''), '')
        if rtype == 'GLOB':
            return {'int'}
        return {'ref', 'baseform'} if rtype and rtype not in PLACED_REF_SIGS else {'ref'}

    def _flow_source(self, value: str, scn_low: str):
        """The (script, var) a `set` copies from, or None: a bare name that is no record is the script's own
        variable; `Owner.var` resolves Owner to its script."""
        name = value.strip('"')
        if _WORD_RE.match(name):
            return None if self.edid_to_formid.get(name.lower()) else (scn_low, name.lower())
        qualified = _QUALIFIED_RE.match(value)
        if not qualified:
            return None
        src_var = qualified.group(2).lower()
        src = self._script_of(qualified.group(1).lower(), src_var, self.script_ref_vars)
        return (src, src_var) if src else None

    def _classify_ref_usage(self, usage: dict, ref_flow: dict) -> None:
        """Int for a ref variable set to non-zero numbers and never used as a reference; a base form for one
        given a base record, spread along variable-to-variable copies until it stops spreading."""
        for key, types in usage.items():
            if 'ref' not in types and 'int' in types:
                self.ref_as_int.add(key)
            elif 'baseform' in types:
                self.ref_as_base_form.add(key)
        changed = True
        while changed:
            changed = False
            for dest, sources in ref_flow.items():
                if dest not in self.ref_as_base_form and any(s in self.ref_as_base_form for s in sources):
                    self.ref_as_base_form.add(dest)
                    changed = True

    def _cross_script_vars(self, sources, export_dir: str) -> dict:
        """{script: variables another script reads or writes as `Owner.var`}, from every SCPT source and the
        plugin's result scripts: those variables must be Properties on the owning script."""
        found: dict[str, set[str]] = {}

        def scan(text):
            """Add each `Owner.var` in `text` that names a declared variable."""
            for line in _strip_comments(text).split('\n'):
                for match in _OWNER_VAR_RE.finditer(line):
                    var = match.group(2).lower()
                    script = self._script_of(match.group(1).lower(), var, self.script_all_vars)
                    if script:
                        found.setdefault(script, set()).add(var)

        for sctx in sources:
            scan(sctx)
        _scan_plugin_result_scripts(export_dir, scan)
        return found

    def is_remote_ref_var(self, owner_edid: str, var_name: str) -> bool:
        """Whether owner_edid's script declares `var_name` a `ref` that holds a reference."""
        var_low = var_name.lower()
        script = self._script_of(owner_edid.lower(), var_low, self.script_ref_vars)
        return bool(script) and (script, var_low) not in self.ref_as_int


# ===========================================================================
# Script converter
# ===========================================================================



def _strip_comments(text: str) -> str:
    """TES4 source with `;` comments removed, line structure preserved.

    A scan for uses must not see commented-out code: it is exactly the code
    the author DISABLED, so counting it types variables off statements that
    never run.
    """
    nl = chr(10)
    return nl.join(line.split(';', 1)[0] for line in text.split(nl))


#: TES4 declarations: `ref <name>`, and any typed `<type> <name>`.
_REF_DECL_RE = re.compile(r'^\s*ref\s+(\w+)', re.IGNORECASE)
_VAR_DECL_RE = re.compile(r'^\s*(short|long|int|float|ref)\s+(\w+)', re.IGNORECASE)
#: `set [owner.]var to value`, an `Owner.var` access, and the shapes of a `set` value.
_SET_RE = re.compile(r'\bset\s+(?:(\w+)\.)?(\w+)\s+to\s+(.+)', re.IGNORECASE)
_OWNER_VAR_RE = re.compile(r'\b(\w+)\.(\w+)\b')
_NUMBER_RE = re.compile(r'^-?\d+(\.\d+)?$')
_WORD_RE = re.compile(r'^\w+$')
_QUALIFIED_RE = re.compile(r'^(\w+)\.(\w+)$')
_COMMAND_RE = re.compile(r'^(?:\w+\.)?(\w+)(?:\s|$)')
_ARITHMETIC_RE = re.compile(r'[\w)]\s*[-+*/]\s*[\w(.]')
#: `var.<call>` with a call only an Actor has.
_ACTOR_CALL_RE = re.compile(
    r'(\w+)\s*\.\s*(?:' + '|'.join(re.escape(f) for f in sorted(ACTOR_ONLY_FUNCTIONS - OBJREF_SHARED_FUNCTIONS))
    + r')(?:\s|$|\()', re.IGNORECASE)


def _script_declarations(records: list) -> tuple:
    """(sources, ref vars, all vars, actor vars), each keyed by lowercase script EditorID: the SCTX text, its
    `ref` names, {name: Papyrus type}, and the ref names given an Actor-only call outside a comment."""
    sources, ref_vars, all_vars, actor_vars = {}, {}, {}, {}
    for rec in records:
        edid, sctx = rec.get('EditorID', ''), rec.get('SCTX', '')
        if not edid or not sctx:
            continue
        scn_low = edid.lower()
        sources[scn_low] = sctx
        refs, typed = set(), {}
        for line in sctx.split('\n'):
            m = _REF_DECL_RE.match(line.strip())
            if m:
                refs.add(m.group(1).lower())
            m = _VAR_DECL_RE.match(line.strip())
            if m:
                typed[m.group(2).lower()] = variable_type(m.group(1).lower())
        if refs:
            ref_vars[scn_low] = refs
            actor_used = {m.group(1).lower() for m in _ACTOR_CALL_RE.finditer(_strip_comments(sctx))} & refs
            if actor_used:
                actor_vars[scn_low] = actor_used
        if typed:
            all_vars[scn_low] = typed
    return sources, ref_vars, all_vars, actor_vars


def _scan_plugin_result_scripts(export_dir: str, scan) -> None:
    """Feed THIS plugin's INFO result scripts (both halves) and QUST stage
    scripts to `scan`: a pure union that only ADDS names which must become
    Properties.  The masters' copies are not read -- each master's own run
    emits its fragments."""
    for extra_file, field_name in [('INFO.txt', 'ResultScript'),
                                   ('INFO.txt', 'ResultScriptEnd'),
                                   ('QUST.txt', 'SCTX')]:
        prefix = field_name + '='
        for raw_line in _export_lines(os.path.join(export_dir, extra_file)):
            if raw_line.startswith(prefix):
                text = raw_line[len(prefix):].strip()
                scan(unescape_value(text))


def _export_lines(path: str):
    """The lines of one export file; nothing when it is missing or unreadable."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            yield from f
    except (OSError, UnicodeDecodeError):
        return
