"""Spike 3 end to end: Doc Mitchell's converted script on his Fallout 4 stand-in.

`dialogue.build(..., scripts=<converted folder>)` calls `attach`: a helper
quest carrying TES4_PlayerControls, and the VMAD putting GSDocMitchellScript
on Doc's stand-in with its properties filled where the spike world has the
form (TES4AV_<name> from the spike's actor values, which are plugin ones where
Fallout 4 has none; TES4PlayerControls from the helper quest; the rest stay
unfilled). `compile_into` compiles the script
and the Fallout 4 helpers with Fallout 4's compiler into <Data>/Scripts.

See: docs/fork/fo4_spikes.md#spike-3-end-to-end
"""

import re
import shutil
import tempfile
from pathlib import Path

from fo4_import.base.papyrus import compile_folder, header_dirs
from fo4_import.base.vmad import object_scripts
from fo4_import.spike import records as R
from script_convert.target import AV_PROPERTY_PREFIX, CONTROLS_SCRIPT

DOC_SCRIPT = 'FALLOUTNV_GSDocMitchellScript'
_PROPERTY = re.compile(r'^(\w+)\s+Property\s+(\w+)', re.I | re.M)


def declared_properties(psc: str) -> list:
    """[(type, name)] of a script's properties, in declaration order."""
    return _PROPERTY.findall(psc)


def fill(declared: list, helpers: dict, av) -> dict:
    """{property: FormID} for the properties this spike can fill; `helpers` is {script type: quest}, `av` name -> FormID."""
    out = {}
    for ptype, name in declared:
        if ptype == 'ActorValue' and name.startswith(AV_PROPERTY_PREFIX):
            fid = av(name[len(AV_PROPERTY_PREFIX):])
            if fid is not None:
                out[name] = fid
        elif ptype in helpers:
            out[name] = helpers[ptype]
    return out


def attach(scripts_dir: Path, ids, av) -> tuple:
    """(VMAD for Doc's stand-in, [helper quest records]); the quest's FormID from `ids`, actor values from `av`."""
    quest = ids.take()
    record = R.pack_script_quest(quest, 'FNVSpike_PlayerControls', object_scripts([(CONTROLS_SCRIPT, {}, {})]))
    psc = (scripts_dir / f'{DOC_SCRIPT}.psc').read_text(encoding='utf-8')
    props = fill(declared_properties(psc), {CONTROLS_SCRIPT: quest}, av)
    return object_scripts([(DOC_SCRIPT, props, {})]), [(quest, record)]


def compile_into(scripts_dir: Path, data_dir: Path) -> str:
    """Compile Doc's script and every static helper in `scripts_dir` into <data_dir>/Scripts; the compiler output."""
    scripts_dir, out = scripts_dir.resolve(), (data_dir / 'Scripts').resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fo4spike_') as tmp:
        for psc in scripts_dir.glob('*.psc'):
            if psc.stem == DOC_SCRIPT or not psc.stem.upper().startswith('FALLOUTNV_'):
                shutil.copy2(psc, tmp)
        return compile_folder(Path(tmp), out, f'{header_dirs()};{scripts_dir}')
