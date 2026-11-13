"""FalloutHelpers.esl: the records every converted FO3/FNV plugin masters and no source plugin has.

    py -3.14 -m fo4_import.helpers_plugin --out <Data>/FalloutHelpers.esl
    py -3.14 -m fo4_import.helpers_plugin --trace-switch --out "<MO2 mods>/F3NV - Trace/F3NV_Trace.esl"

Actor values FO4 lacks (Variable01-10, the FO3/FNV skills), the start-game
quests running the helper quest scripts, and the helpers' globals; one copy
for every converted game, since they hold player and actor state. Object ids
come from script_convert.constants (FALLOUT4_HELPER_*), a save contract.
Cleanroom UI's CleanroomUI.esl (cleanroom_plugin) is written beside it.

See: docs/fork/fo4_spikes.md#spike-3-helper-plugin
"""

import argparse
import re
from pathlib import Path

from fo4_import import cleanroom_plugin
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.support_records import pack_avif, pack_global, pack_mesg, pack_script_quest
from fo4_import.base.vmad import object_scripts
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.helpers_races import race_records
from script_convert.constants import (FALLOUT4_HELPER_AV_DEFAULTS, FALLOUT4_HELPER_AVS, FALLOUT4_HELPER_GLOBALS,
                                      FALLOUT4_HELPER_MESSAGES, FALLOUT4_HELPER_PLUGIN,
                                      FALLOUT4_HELPER_QUEST_MESSAGES, FALLOUT4_HELPER_QUESTS, FALLOUT4_HELPER_ROBOT_FRENZY,
                                      FALLOUT4_TRACE_PLUGIN)
from script_convert.target import fallout4_actor_values

MASTERS = ['Fallout4.esm']
#: MESG DNAM flag Message Box.
MESSAGE_BOX = 0x1
#: Editor ID prefix of the plugin's actor values (TES4Variable01), as the converter's TES4* globals.
EDID_PREFIX = 'TES4'


def form_id(object_id: int, index: int) -> int:
    """A helper record's FormID where the helper plugin is master `index`."""
    return index << 24 | object_id


def own_id(object_id: int) -> int:
    """A helper record's FormID inside the helper plugin itself."""
    return form_id(object_id, len(MASTERS))


def actor_value_form(name: str, index: int) -> 'int | None':
    """The FormID of actor value `name` (any case; Fallout4.esm's or the helper plugin's), None if neither has it."""
    entry = fallout4_actor_values().get(name.lower())
    if entry is None:
        return None
    _, plugin, object_id = entry
    return form_id(object_id, index) if plugin == FALLOUT4_HELPER_PLUGIN else object_id


def helper_forms(index: int) -> dict:
    """{Papyrus type: {property name or '*': FormID}}: helper quests, globals."""
    out = {script: {'*': form_id(oid, index)} for script, oid in FALLOUT4_HELPER_QUESTS.items()}
    out['GlobalVariable'] = {edid: form_id(oid, index) for edid, oid in FALLOUT4_HELPER_GLOBALS.items()}
    return out


def records(fo4: bytes = None) -> list:
    """[(signature, record)] of everything the helper plugin holds, in object id order; `fo4` is Fallout4.esm's
    bytes (read from the install when None), whose FO4-only race abilities are gated (helpers_races)."""
    out = [('AVIF', pack_avif(own_id(oid), EDID_PREFIX + name, re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name), '',
                              FALLOUT4_HELPER_AV_DEFAULTS.get(name, 0.0)))
           for name, oid in FALLOUT4_HELPER_AVS.items()]
    out += [('QUST', pack_script_quest(own_id(oid), script, object_scripts([(script, _messages(script), {})])))
            for script, oid in FALLOUT4_HELPER_QUESTS.items()]
    out += [('GLOB', pack_global(own_id(oid), edid)) for edid, oid in FALLOUT4_HELPER_GLOBALS.items()]
    out += [('MESG', pack_mesg(own_id(oid), edid, text, text, MESSAGE_BOX, list(buttons)))
            for edid, (oid, text, buttons) in FALLOUT4_HELPER_MESSAGES.items()]
    return out + race_records(fo4 or (FALLOUT4_DIR / 'Data' / 'Fallout4.esm').read_bytes(), own_id)


def _messages(script: str) -> dict:
    """{property: helper message FormID} a helper quest script is given."""
    return {prop: own_id(FALLOUT4_HELPER_MESSAGES[edid][0])
            for prop, edid in FALLOUT4_HELPER_QUEST_MESSAGES.get(script, {}).items()}


def build(out: Path) -> int:
    """Write the helper plugin to `out`; the record count."""
    w = FO4PluginWriter(masters=MASTERS, is_esm=True, is_esl=True, description='Shared records for converted FO3/FNV')
    made = records()
    for sig, record in made:
        w.add_record(sig, record)
    ids = [*FALLOUT4_HELPER_AVS.values(), *FALLOUT4_HELPER_QUESTS.values(), *FALLOUT4_HELPER_GLOBALS.values(),
           *(oid for oid, _, _ in FALLOUT4_HELPER_MESSAGES.values()), FALLOUT4_HELPER_ROBOT_FRENZY]
    w.next_object_id = own_id(max(ids) + 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(out))
    return len(made)


def build_trace_switch(out: Path) -> None:
    """Write FALLOUT4_TRACE_PLUGIN to `out`: an empty light plugin, no masters, which turns the trace on while enabled.
    See: docs/fork/fo4_pipeline.md#trace
    """
    w = FO4PluginWriter(masters=[], is_esm=True, is_esl=True, description='Turns the F3NV session trace on')
    out.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(out))


def main():
    """Build the helper plugin and Cleanroom UI's beside it, or with --trace-switch the trace switch plugin."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True, help=f'Plugin to write ({FALLOUT4_HELPER_PLUGIN}, or {FALLOUT4_TRACE_PLUGIN})')
    ap.add_argument('--trace-switch', action='store_true', help=f'write the empty {FALLOUT4_TRACE_PLUGIN} instead')
    args = ap.parse_args()
    if args.trace_switch:
        build_trace_switch(Path(args.out))
        print(f'{args.out}: the trace switch')
        return
    print(f'{args.out}: {build(Path(args.out))} records')
    print(f'{cleanroom_plugin.build(Path(args.out).parent)}: Cleanroom UI\'s holder')


if __name__ == '__main__':
    main()
