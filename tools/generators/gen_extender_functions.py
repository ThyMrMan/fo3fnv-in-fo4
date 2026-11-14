"""Regenerate script_convert/data/extender_functions.json: every xNVSE, JIP LN and FOSE script function, with what
it returns (number, form, string or array).

Usage:
  python tools/generators/gen_extender_functions.py

See: docs/fork/nvse_script_language.md#unknown-functions
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'script_convert' / 'data' / 'extender_functions.json'
#: (command table file, its registration pattern: command name, then an optional return type) per extender.
TABLES = (
    (ROOT / 'references' / 'xNVSE' / 'nvse' / 'nvse' / 'CommandTable.cpp',
     re.compile(r'ADD_CMD(?:_VER)?(?:_RET)?\(\s*(\w+)\s*(?:,\s*kRetnType_(\w+))?')),
    (ROOT / 'references' / 'FOSE' / 'src' / 'fose' / 'fose' / 'CommandTable.cpp',
     re.compile(r'ADD_CMD(?:_RET)?\(\s*(\w+)\s*(?:,\s*kRetnType_(\w+))?')),
    (ROOT / 'references' / 'JIP-LN-NVSE' / 'jip_nvse.cpp',
     re.compile(r'REG_CMD(?:_(FRM|STR|ARR|AMB))?\(\s*(\w+)')),
)
#: A command's second name: DEFINE_..._ALT...(name, alt, ...).
ALT = re.compile(r'DEFINE_\w*ALT\w*\(\s*(\w+)\s*,\s*(\w+)')
#: Registered return type -> the kind of value the converter's inert read must have.
KINDS = {'Form': 'form', 'FRM': 'form', 'String': 'string', 'STR': 'string', 'Array': 'array', 'ARR': 'array'}


def _registered(path: Path, pattern: re.Pattern) -> dict:
    """{command name: kind} of one command table."""
    out = {}
    for match in pattern.finditer(path.read_text(encoding='utf-8', errors='replace')):
        if path.name == 'jip_nvse.cpp':
            kind, name = match.group(1) or '', match.group(2)
        else:
            name, kind = match.group(1), match.group(2) or ''
        out[name] = KINDS.get(kind, 'number')
    return out


def _alternates(folder: Path) -> dict:
    """{command name: its second name} declared anywhere under `folder`."""
    out = {}
    for path in folder.rglob('*'):
        if path.suffix.lower() in ('.h', '.cpp'):
            out.update(ALT.findall(path.read_text(encoding='utf-8', errors='replace')))
    return out


def main():
    """Read every table, add each command's second name with its kind, and write OUT sorted; a typed
    registration wins over an untyped one of the same name."""
    kinds = {}
    for path, pattern in TABLES:
        found = _registered(path, pattern)
        for name, alt in _alternates(path.parent).items():
            if name in found:
                found[alt] = found[name]
        for name, kind in found.items():
            if kinds.get(name.lower(), 'number') == 'number':
                kinds[name.lower()] = kind
    OUT.write_text(json.dumps(dict(sorted(kinds.items())), indent=0) + '\n', encoding='utf-8')
    print(f'Wrote {len(kinds)} functions -> {OUT}')


if __name__ == '__main__':
    main()
