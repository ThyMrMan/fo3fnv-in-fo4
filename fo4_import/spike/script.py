"""Spike 3 end to end: Doc Mitchell's converted script on his Fallout 4 stand-in.

`dialogue.build(..., scripts=<converted folder>)` calls `attach`: the VMAD
putting GSDocMitchellScript on Doc's stand-in with its properties filled where
the spike world has the form (actor values, helper quests and globals from
Fallout4.esm and FalloutHelpers.esl; the rest stay unfilled). `Fragments` gives each spike line whose FNV INFO has a converted
fragment script its INFO VMAD. `compile_into` compiles the scripts and the
Fallout 4 helpers with Fallout 4's compiler into <Data>/Scripts.

See: docs/fork/fo4_spikes.md#spike-3-end-to-end
"""

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from asset_convert.game_paths import namespace_for
from fo4_import.base.file_stamps import Stamps
from fo4_import.base.papyrus import compile_folder, header_dirs
from fo4_import.base.support_records import pack_script_quest
from fo4_import.base.vmad import info_fragments, object_scripts, quest_fragments
from fo4_import.helpers_plugin import actor_value_form, helper_forms
from fo4_import.spike.items import ENGINE_IDS
from fo4_import.pipeline.export_index import export_records
from fo4_import.pipeline.code_tag import ROOT
from output_layout import record_dir
from script_convert.target import AV_PROPERTY_PREFIX
from tools.script.compile_papyrus import compile_fallout4

DOC_SCRIPT = 'FALLOUTNV_GSDocMitchellScript'
FRAGMENT_PREFIX = 'FALLOUTNV_TIF__'
QUEST_PREFIX = 'FALLOUTNV_QF_'
PACKAGE_PREFIX = 'FALLOUTNV_PF__'
#: FNV quests the spike converts -> their object id, outside the spike's sequential ids so no line moves.
QUESTS = {'VDoctors': 0x1000}
_STAGE_FRAGMENT = re.compile(r'^Function (Fragment_Stage_(\d+)_Item_(\d+))\(', re.I | re.M)
#: Papyrus property type -> the Fallout4.esm dump whose same-named records fill it.
FORM_DUMPS = {'MiscObject': 'MISC', 'Potion': 'ALCH', 'GlobalVariable': 'GLOB'}
#: Types filled only by engine objects (FormID below ENGINE_IDS): the same form in both games, e.g. GameHour.
ENGINE_ONLY = frozenset({'GlobalVariable'})
FO4_DUMP = Path(__file__).resolve().parents[2] / 'references' / 'Fallout4.esm'
_PROPERTY = re.compile(r'^(\w+)\s+Property\s+(\w+)', re.I | re.M)
TRACE_SCRIPT = 'FNVSpike_SceneTrace'
TRACE_LOG = 'FNVSpikeTrace'
#: compile_into's staging folders (one per output Scripts folder).
STAGE = ROOT / 'output' / 'fo4_cache' / 'script_stage'
#: Compiler instances compile_into runs at once.
WORKERS = max(1, (os.cpu_count() or 2) - 1)


def stage_fragments(psc: str) -> list:
    """[(stage, log index, function)] of a converted quest stage script."""
    return [(int(stage), int(item), name) for name, stage, item in _STAGE_FRAGMENT.findall(psc)]


def declared_properties(psc: str) -> list:
    """[(type, name)] of a script's properties, in declaration order."""
    return _PROPERTY.findall(psc)


def fo4_forms() -> dict:
    """{Papyrus type: {editor ID: FormID}} of the records FORM_DUMPS names (ENGINE_ONLY types: engine objects)."""
    out = {}
    for ptype, sig in FORM_DUMPS.items():
        ids = ((r['EditorID'], int(r['FormID'], 16)) for r in export_records(FO4_DUMP, sig) if r.get('EditorID'))
        out[ptype] = {edid: fid for edid, fid in ids if ptype not in ENGINE_ONLY or fid < ENGINE_IDS}
    return out


def base_forms(helper_index: int) -> dict:
    """fill()'s `forms`: fo4_forms() and the helper plugin's, joined per type."""
    fo4, helpers = fo4_forms(), helper_forms(helper_index)
    return {ptype: {**fo4.get(ptype, {}), **helpers.get(ptype, {})} for ptype in fo4.keys() | helpers.keys()}


def fill(declared: list, forms: dict, helper_index: int) -> dict:
    """{property: FormID} for the properties this spike can fill.

    TES4AV_<name> from Fallout4.esm or the helper plugin (master number
    `helper_index`); `forms` is {Papyrus type: {property name, or '*' for
    any: FormID}}: helper quests and globals, and Fallout4.esm records named
    as the property.
    """
    out = {}
    for ptype, name in declared:
        if ptype == 'ActorValue' and name.startswith(AV_PROPERTY_PREFIX):
            fid = actor_value_form(name[len(AV_PROPERTY_PREFIX):], helper_index)
        else:
            by_name = forms.get(ptype, {})
            fid = by_name.get('*', by_name.get(name))
        if fid is not None:
            out[name] = fid
    return out


def spike_forms(helper_index: int, own_index: int) -> dict:
    """fill()'s `forms`: helper quests, globals, FO4 records, QUESTS."""
    quests = {'Quest': {edid: own_index << 24 | oid for edid, oid in QUESTS.items()}}
    return {**base_forms(helper_index), **quests}


def quest_record(scripts_dir: Path, edid: str, fid: int, stages: list, forms: dict, helper_index: int) -> tuple:
    """(QUST record, stage script name): FNV quest `edid` with its stages and its converted stage fragments."""
    script = f'{QUEST_PREFIX}{edid}'
    psc = (scripts_dir / f'{script}.psc').read_text(encoding='utf-8')
    vmad = quest_fragments(script, stage_fragments(psc), fill(declared_properties(psc), forms, helper_index))
    return pack_script_quest(fid, edid, vmad, stages), script


class Fragments:
    """The spike lines' converted INFO fragments; `used` lists the scripts given out."""

    def __init__(self, scripts_dir: Path, forms: dict, helper_index: int):
        self.dir, self.forms, self.helper_index, self.used = scripts_dir, forms, helper_index, []

    def vmad(self, fnv_info: str) -> bytes:
        """The INFO VMAD for FNV INFO `fnv_info` (hex FormID); b'' with no fragment script."""
        name = f'{FRAGMENT_PREFIX}{fnv_info}'
        path = self.dir / f'{name}.psc'
        if not path.exists():
            return b''
        self.used.append(name)
        props = fill(declared_properties(path.read_text(encoding='utf-8')), self.forms, self.helper_index)
        return info_fragments(name, props, begin='Fragment_1', end='Fragment_0')


def attach(scripts_dir: Path, forms: dict, helper_index: int) -> bytes:
    """The VMAD putting Doc's converted script on his stand-in, filled."""
    psc = (scripts_dir / f'{DOC_SCRIPT}.psc').read_text(encoding='utf-8')
    return object_scripts([(DOC_SCRIPT, fill(declared_properties(psc), forms, helper_index), {})])


def converted_prefix(scripts_dir: Path) -> str:
    """Converted-script prefix of `scripts_dir` (named for its plugin): the namespace."""
    return namespace_for(record_dir(ROOT / 'export', scripts_dir.name)).upper() + '_'


def with_types(scripts_dir: Path, names, prefix: str) -> set:
    """`names` and every converted script (`prefix` names) they name, transitively: a script whose types are
    missing does not link. Each script's named types are kept between builds by file stamp (file_stamps)."""
    known = {p.stem.upper(): p.stem for p in scripts_dir.glob(f'{prefix}*.psc')}
    converted = re.compile(rf'\b{re.escape(prefix)}\w+', re.I)
    found = lambda path: sorted({t.upper() for t in converted.findall(path.read_text(encoding='utf-8'))})
    stamps = Stamps(STAGE / f'types_{hashlib.sha1(f"{scripts_dir}|{prefix}".lower().encode()).hexdigest()[:12]}.json')
    todo, seen = list(names), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo += [known[t] for t in stamps.value(scripts_dir / f'{name}.psc', found) if t in known]
    stamps.save()
    return seen


def adopted_scripts(names: list, masters: tuple, shipped: tuple) -> list:
    """The masters' converted sources (in `masters`) of `names` that no master's Scripts folder (`shipped`)
    holds compiled."""
    out = []
    for name in names:
        source = next((Path(m) / f'{name}.psc' for m in masters if (Path(m) / f'{name}.psc').is_file()), None)
        if source and not any((Path(s) / f'{name}.pex').is_file() for s in shipped):
            out.append(source)
    return out


def compile_into(scripts_dir: Path, data_dir: Path, fragments: list = (), masters: tuple = (),
                 shipped: tuple = ()) -> str:
    """Compile Doc's script (when the folder has it), `fragments`, the scripts they name and every static helper
    into <data_dir>/Scripts; a summary. Only what changed since the last build compiles, from a staging folder
    kept between builds. A dependent plugin's build compiles only its own folder's scripts, its masters'
    folders `masters` imported (theirs ship with them), and any of theirs it uses that no master's Scripts
    folder `shipped` holds compiled (adopted_scripts).
    See: docs/fork/fo4_plugin_layout.md#dlc-build
    """
    scripts_dir, out = scripts_dir.resolve(), (data_dir / 'Scripts').resolve()
    out.mkdir(parents=True, exist_ok=True)
    prefix = converted_prefix(scripts_dir)
    roots = [DOC_SCRIPT] if (scripts_dir / f'{DOC_SCRIPT}.psc').exists() else []
    own = [f for f in fragments if not masters or (scripts_dir / f'{f}.psc').exists()]
    adopted = adopted_scripts([f for f in fragments if f not in own], masters, shipped)
    wanted = with_types(scripts_dir, [*roots, *own], prefix)
    keep = {p.name for p in scripts_dir.glob('*.psc') if p.stem in wanted or not p.stem.upper().startswith(prefix)}
    keep |= {path.name for path in adopted}
    sources = {**{name: scripts_dir / name for name in keep}, **{path.name: path for path in adopted}}
    stage = STAGE / hashlib.sha1(str(out).encode()).hexdigest()[:12]
    stage.mkdir(parents=True, exist_ok=True)
    for old in stage.glob('*.psc'):
        if old.name not in keep:
            old.unlink()
    for name in sorted(keep):
        if not (stage / name).exists() or (stage / name).read_bytes() != sources[name].read_bytes():
            shutil.copyfile(sources[name], stage / name)
    compiled, own, names = compile_fallout4(SimpleNamespace(src=str(stage), out=str(out), full=False, workers=WORKERS,
                                                            headers=';'.join([header_dirs(), *(str(Path(m).resolve()) for m in masters)])
                                                            if masters else None))
    failed = sorted(n for n in names if n.lower() not in compiled)
    return f'{len(names) - len(failed)} of {len(names)} scripts compile' + ''.join(
        f'\n  {n}: {"; ".join(own.get(n, ["no error of its own (a script it uses failed, or the compiler did)"]))}'
        for n in failed)


def trace_source(plugin: str, scenes: list, actors: list) -> str:
    """A debug quest script logging to FNVSpikeTrace whenever the spike's dialogue state changes.

    State: which of `scenes` [(edid, FormID)] play, who holds the
    conversation quest's alias 0, and each of `actors` [(label, FormID)]'s
    current scene and whether it is in dialogue with the player.
    """
    def form(fid: int, kind: str) -> str:
        return f'(Game.GetFormFromFile(0x{fid & 0xFFFFFF:06X}, "{plugin}") as {kind})'
    body = ['  String now = ""']
    for edid, fid in scenes:
        body += [f'  If {form(fid, "Scene")}.IsPlaying()', f'    now += " {edid}"', '  EndIf']
    body += ['  now += " | alias=" + (Conversation.GetAlias(0) as ReferenceAlias).GetReference()']
    for label, fid in actors:
        body += [f'  Actor a{label} = {form(fid, "Actor")}',
                 f'  now += " | {label} scene=" + a{label}.GetCurrentScene() + " talking=" '
                 f'+ a{label}.IsInDialogueWithPlayer()']
    return '\n'.join([f'Scriptname {TRACE_SCRIPT} extends Quest', 'Quest Property Conversation Auto',
                      'String Last = ""', '', 'Event OnInit()', '  StartTimer(0.25)', 'EndEvent', '',
                      'Event OnTimer(int aiTimerID)', *body,
                      '  If now != Last', f'    Debug.OpenUserLog("{TRACE_LOG}")',
                      f'    Debug.TraceUser("{TRACE_LOG}", Utility.GetCurrentRealTime() + now)',
                      '    Last = now', '  EndIf', '  StartTimer(0.25)', 'EndEvent', ''])


def trace_quest(fid: int, conversation: int) -> bytes:
    """The debug quest record carrying the trace script."""
    return pack_script_quest(fid, TRACE_SCRIPT, object_scripts([(TRACE_SCRIPT, {'Conversation': conversation}, {})]))


def compile_source(name: str, text: str, data_dir: Path) -> str:
    """Compile one generated script into <data_dir>/Scripts."""
    out = (data_dir / 'Scripts').resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fo4spike_') as tmp:
        (Path(tmp) / f'{name}.psc').write_text(text, encoding='utf-8')
        return compile_folder(Path(tmp), out, f'{header_dirs()};{tmp}')
