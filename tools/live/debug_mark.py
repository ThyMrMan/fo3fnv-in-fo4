#!/usr/bin/env python3
"""Build TES4DebugMark.esp: a play-test key that marks a moment in the flight recorder.

The plugin is one start-game quest whose PlayerRef alias runs
TES4_DebugMark, plus the TES4MarkKey global (65 = F7). It is ESL-flagged and
names only Skyrim.esm, so it loads beside any converted game without taking a
slot or touching the conversion. A key press writes TES4MARK lines to the
Papyrus log; the bridge keeps them as `mark` events, and
tools/live/session_report.py explains each one.

    python tools/live/debug_mark.py               # -> output/TES4DebugMark/

Enable the folder as a mod (with TES4DebugMark.esp checked); Papyrus logging
must be on, since marks travel through the Papyrus log.

See: docs/commentary/tools_live_session_report.md#mark-key
"""

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tes5_import.base.writer import (PluginWriter, pack_formid_subrecord, pack_record, pack_string_subrecord,
                                     pack_subrecord, pack_uint32_subrecord)

PLUGIN = 'TES4DebugMark.esp'
SCRIPT = 'TES4_DebugMark'
KEY_GLOBAL = 'TES4MarkKey'
QUEST = 'TES4DebugMarkQuest'

#: DirectInput scan code of F7, which vanilla Skyrim leaves unbound.
DEFAULT_KEY = 65

#: Light-plugin ids: own index 1 (after Skyrim.esm), objects from 0x800.
_QUEST_FID, _GLOBAL_FID = 0x01000800, 0x01000801

#: TES4 record flag of a light (ESL-flagged) plugin.
_LIGHT = 0x200

#: QUST DNAM flags Start Game Enabled + Starts Enabled.
_START_ENABLED = 0x0011

#: Alias FNAM flags: Optional, Allow Disabled, Allow Dead, Allow Reserved.
_ALIAS_FLAGS = 0x00000292

_PLAYER_REF = 0x00000014


def _global(key: int) -> bytes:
    """The TES4MarkKey GLOB record, a short holding the scan code."""
    subs = pack_string_subrecord('EDID', KEY_GLOBAL)
    subs += pack_subrecord('FNAM', b's') + pack_subrecord('FLTV', struct.pack('<f', float(key)))
    return pack_record('GLOB', _GLOBAL_FID, 0, subs)


def _quest() -> bytes:
    """The start-game quest, its alias 0 forced to PlayerRef and running TES4_DebugMark."""
    from script_convert.pipeline import build_vmad_quest_fragments
    vmad = build_vmad_quest_fragments(QUEST, [], None, None, quest_fid=_QUEST_FID,
                                      alias_scripts=[(0, [(SCRIPT, {KEY_GLOBAL: _GLOBAL_FID})])])
    q = pack_string_subrecord('EDID', QUEST) + pack_subrecord('VMAD', vmad)
    q += pack_string_subrecord('FULL', 'TES4 Debug Mark')
    q += pack_subrecord('DNAM', struct.pack('<HBBII', _START_ENABLED, 0, 0, 0, 0))
    q += pack_subrecord('NEXT', b'') + pack_uint32_subrecord('ANAM', 1)
    q += pack_uint32_subrecord('ALST', 0) + pack_string_subrecord('ALID', 'Player')
    q += pack_uint32_subrecord('FNAM', _ALIAS_FLAGS) + pack_formid_subrecord('ALFR', _PLAYER_REF)
    q += pack_formid_subrecord('VTCK', 0) + pack_subrecord('ALED', b'')
    return pack_record('QUST', _QUEST_FID, 0, q)


def write_plugin(path: Path, key: int) -> None:
    """Write the ESL-flagged plugin to `path`."""
    writer = PluginWriter(masters=['Skyrim.esm'], is_esm=False, author='tes4skyrim',
                          description='Play-test marker for the flight recorder')
    writer.add_record('GLOB', _global(key))
    writer.add_record('QUST', _quest())
    writer.write(str(path))
    data = bytearray(path.read_bytes())
    struct.pack_into('<I', data, 8, struct.unpack_from('<I', data, 8)[0] | _LIGHT)
    path.write_bytes(bytes(data))


def compile_script(out_dir: Path) -> None:
    """Compile TES4_DebugMark.psc into `out_dir`/Scripts, against vanilla and SKSE headers."""
    from convert import load_config
    from papyrus_compile import find_skse_source_scripts, find_skyrim_source_scripts
    from tools.script.compile_papyrus import compile_one, find_compiler
    config = load_config()
    skse = find_skse_source_scripts(config)
    if not skse:
        raise SystemExit('SKSE script headers not found; the mark script calls SKSE natives')
    scripts = out_dir / 'Scripts'
    scripts.mkdir(parents=True, exist_ok=True)
    psc = Path(__file__).resolve().parent / 'debug_mark' / f'{SCRIPT}.psc'
    status, _key, raw, _name = compile_one((psc, find_compiler(), scripts, find_skyrim_source_scripts(config), skse))
    if status != 'ok':
        raise SystemExit(f'{SCRIPT}.psc failed to compile: {raw}')


def main(argv=None) -> int:
    """Build the plugin and its compiled script."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', default=str(ROOT / 'output' / 'TES4DebugMark'), help='mod folder to write')
    ap.add_argument('--key', type=int, default=DEFAULT_KEY, help='DirectInput scan code (65 = F7)')
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_plugin(out / PLUGIN, args.key)
    compile_script(out)
    print(f'wrote {out / PLUGIN} and Scripts/{SCRIPT}.pex')
    return 0


if __name__ == '__main__':
    sys.exit(main())
