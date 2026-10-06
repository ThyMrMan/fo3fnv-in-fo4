"""Spike 3 end to end: Doc Mitchell's converted script on his Fallout 4 stand-in.

`dialogue.build(..., scripts=<converted folder>)` calls `attach`: a helper
quest carrying TES4_PlayerControls, and the VMAD putting GSDocMitchellScript
on Doc's stand-in with its properties filled where the spike world has the
form (TES4AV_<name> from the spike's actor values, which are plugin ones where
Fallout 4 has none; TES4PlayerControls from the helper quest; the rest stay
unfilled). `Fragments` gives each spike line whose FNV INFO has a converted
fragment script its INFO VMAD. `compile_into` compiles the scripts and the
Fallout 4 helpers with Fallout 4's compiler into <Data>/Scripts.

See: docs/fork/fo4_spikes.md#spike-3-end-to-end
"""

import re
import shutil
import tempfile
from pathlib import Path

from fo4_import.base.papyrus import compile_folder, header_dirs
from fo4_import.base.vmad import info_fragments, object_scripts
from fo4_import.spike import records as R
from tes5_import.base.text_reader import parse_export_file
from script_convert.target import AV_PROPERTY_PREFIX, CONTROLS_SCRIPT

DOC_SCRIPT = 'FALLOUTNV_GSDocMitchellScript'
FRAGMENT_PREFIX = 'FALLOUTNV_TIF__'
#: Papyrus property type -> the Fallout4.esm dump whose same-named records fill it.
FORM_DUMPS = {'MiscObject': 'MISC', 'Potion': 'ALCH'}
FO4_DUMP = Path(__file__).resolve().parents[2] / 'references' / 'Fallout4.esm'
_PROPERTY = re.compile(r'^(\w+)\s+Property\s+(\w+)', re.I | re.M)
_CONVERTED_TYPE = re.compile(r'\bFALLOUTNV_\w+', re.I)
TRACE_SCRIPT = 'FNVSpike_SceneTrace'
TRACE_LOG = 'FNVSpikeTrace'


def declared_properties(psc: str) -> list:
    """[(type, name)] of a script's properties, in declaration order."""
    return _PROPERTY.findall(psc)


def fo4_forms() -> dict:
    """{Papyrus type: {editor ID: FormID}} of the records FORM_DUMPS names."""
    return {ptype: {r['EditorID']: int(r['FormID'], 16) for r in parse_export_file(str(FO4_DUMP / f'{sig}.txt'))
                    if r.get('EditorID')} for ptype, sig in FORM_DUMPS.items()}


def fill(declared: list, helpers: dict, av, forms: dict = None) -> dict:
    """{property: FormID} for the properties this spike can fill.

    `helpers` is {script type: quest}, `av` maps an actor value name to its
    FormID, `forms` is fo4_forms(): a property named after a Fallout 4
    record of its type gets that record.
    """
    out = {}
    for ptype, name in declared:
        fid = None
        if ptype == 'ActorValue' and name.startswith(AV_PROPERTY_PREFIX):
            fid = av(name[len(AV_PROPERTY_PREFIX):])
        elif ptype in helpers:
            fid = helpers[ptype]
        elif forms:
            fid = forms.get(ptype, {}).get(name)
        if fid is not None:
            out[name] = fid
    return out


class Fragments:
    """The spike lines' converted INFO fragments.

    Built twice: a first pass with no `avs` lists the actor values the
    fragments need (`needed`) and packs nothing, so the spike can give the
    plugin's own ones their FormIDs after every line has its own; the second
    pass packs each VMAD with those FormIDs (`avs`, name -> FormID).
    """

    def __init__(self, scripts_dir: Path, forms: dict, avs: dict = None, needed: list = ()):
        self.dir, self.forms, self.avs = scripts_dir, forms, avs
        self.needed, self.used = list(needed), []

    def vmad(self, fnv_info: str) -> bytes:
        """The INFO VMAD for FNV INFO `fnv_info` (hex FormID); b'' with no fragment script, or on the first pass."""
        name = f'{FRAGMENT_PREFIX}{fnv_info}'
        path = self.dir / f'{name}.psc'
        if not path.exists():
            return b''
        declared = declared_properties(path.read_text(encoding='utf-8'))
        if self.avs is None:
            self.needed += [n[len(AV_PROPERTY_PREFIX):] for t, n in declared
                            if t == 'ActorValue' and n.startswith(AV_PROPERTY_PREFIX)
                            and n[len(AV_PROPERTY_PREFIX):] not in self.needed]
            return b''
        self.used.append(name)
        props = fill(declared, {}, self.avs.get, self.forms)
        return info_fragments(name, props, begin='Fragment_1', end='Fragment_0')


def attach(scripts_dir: Path, ids, av) -> tuple:
    """(VMAD for Doc's stand-in, [helper quest records]); the quest's FormID from `ids`, actor values from `av`."""
    quest = ids.take()
    record = R.pack_script_quest(quest, 'FNVSpike_PlayerControls', object_scripts([(CONTROLS_SCRIPT, {}, {})]))
    psc = (scripts_dir / f'{DOC_SCRIPT}.psc').read_text(encoding='utf-8')
    props = fill(declared_properties(psc), {CONTROLS_SCRIPT: quest}, av)
    return object_scripts([(DOC_SCRIPT, props, {})]), [(quest, record)]


def with_types(scripts_dir: Path, names) -> set:
    """`names` and every converted script they name, transitively: a script whose types are missing does not link."""
    known = {p.stem.upper(): p.stem for p in scripts_dir.glob('FALLOUTNV_*.psc')}
    todo, seen = list(names), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        text = (scripts_dir / f'{name}.psc').read_text(encoding='utf-8')
        todo += [known[t.upper()] for t in _CONVERTED_TYPE.findall(text) if t.upper() in known]
    return seen


def compile_into(scripts_dir: Path, data_dir: Path, fragments: list = ()) -> str:
    """Compile Doc's script, `fragments`, the scripts they name and every static helper into <data_dir>/Scripts."""
    scripts_dir, out = scripts_dir.resolve(), (data_dir / 'Scripts').resolve()
    out.mkdir(parents=True, exist_ok=True)
    wanted = with_types(scripts_dir, [DOC_SCRIPT, *fragments])
    with tempfile.TemporaryDirectory(prefix='fo4spike_') as tmp:
        for psc in scripts_dir.glob('*.psc'):
            if psc.stem in wanted or not psc.stem.upper().startswith('FALLOUTNV_'):
                shutil.copy2(psc, tmp)
        return compile_folder(Path(tmp), out, f'{header_dirs()};{scripts_dir}')


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
    return R.pack_script_quest(fid, TRACE_SCRIPT, object_scripts([(TRACE_SCRIPT, {'Conversation': conversation}, {})]))


def compile_source(name: str, text: str, data_dir: Path) -> str:
    """Compile one generated script into <data_dir>/Scripts."""
    out = (data_dir / 'Scripts').resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fo4spike_') as tmp:
        (Path(tmp) / f'{name}.psc').write_text(text, encoding='utf-8')
        return compile_folder(Path(tmp), out, f'{header_dirs()};{tmp}')
