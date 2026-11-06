"""Script object properties a Fallout 4 build leaves unfilled (fo4_audit.check_properties), one finding per
script property.

- error `timer`: the script's OnTimer pass uses it, so each pass fails and logs a stack (a quest polling at its
  authored delay: Lonesome Road's NVDLC04DivideSupport, 0.1 s).
- error `helper`: a form the converter itself names (a `TES4` property, or one of the build's own `F3NV_`
  scripts), which the build should always make.
- review `fnv-form`: FNV has a form of that name the build left out; `no-fnv-form`: no form of that name.
- error `dangling`: filled with a FormID no file defines.

See: docs/fork/fo4_preflight.md#script-properties
"""

import re
from collections import defaultdict
from pathlib import Path

from fo4_import.pipeline.export_index import export_chain
from fo4_import.spike.script import declared_properties
from tools.validate.fo4_audit import Plugin, check_properties, fnv_names, source
from tools.validate.preflight.build_diff import sample
from tools.validate.preflight.findings import Finding

#: The OnTimer event of a Papyrus script.
TIMER = re.compile(r'^Event OnTimer\(.*?^EndEvent', re.MULTILINE | re.DOTALL | re.IGNORECASE)
#: Property and script name prefixes the converter makes itself.
HELPER_PROPERTY, HELPER_SCRIPT = 'tes4', 'f3nv_'
#: (severity, summary) per kind.
KINDS = {'timer': ('error', 'its OnTimer pass uses it, so every pass fails'),
         'helper': ('error', 'a form the converter names and should make'),
         'fnv-form': ('review', 'the FNV form of that name is not in the build'),
         'no-fnv-form': ('review', 'no FNV form has that name')}


def timer_uses(text: str, prop: str) -> bool:
    """Whether `prop` appears in the OnTimer event of script source `text`."""
    block = TIMER.search(text)
    return bool(block) and re.search(rf'\b{re.escape(prop)}\b', block.group(0), re.IGNORECASE) is not None


def kind_of(script: str, prop: str, text: str, names: set) -> str:
    """The KINDS key of unfilled property `prop` of `script` (source `text`), FNV EditorIDs `names` lower."""
    if timer_uses(text, prop):
        return 'timer'
    if prop.lower().startswith(HELPER_PROPERTY) or script.lower().startswith(HELPER_SCRIPT):
        return 'helper'
    return 'fnv-form' if prop.lower() in names else 'no-fnv-form'


def unfilled_findings(game: str, unfilled: list, scripts: Path, names: set) -> list:
    """One finding per (script, property) of `unfilled` [(record, script, property)], its records as detail."""
    records, texts = defaultdict(list), {}
    for record, script, prop in unfilled:
        records[(script, prop)].append(record)
    out = []
    for (script, prop), held in sorted(records.items()):
        text = texts.setdefault(script, source(scripts, script))
        kind = kind_of(script, prop, text, names)
        typed = dict((p.lower(), t) for t, p in declared_properties(text)).get(prop.lower(), '?')
        severity, why = KINDS[kind]
        out.append(Finding('properties', f'properties|{game}|{kind}|{script}.{prop}', severity,
                           f'{script}.{prop} ({typed}) is unfilled on {len(held)} records: {why}',
                           sample(sorted(set(held)))))
    return out


def audit(game: str, plugin: Path, dirs: list, scripts: Path, export_dir: Path) -> list:
    """The unfilled and dangling script property findings for one Fallout 4 build (masters read from `dirs`, FNV
    names from its export's master chain)."""
    unfilled, dangling = check_properties(Plugin(Path(plugin), list(dirs)), Path(scripts))
    names = set().union(*(fnv_names(Path(e)) for e in export_chain(Path(export_dir))))
    out = unfilled_findings(game, unfilled, Path(scripts), names)
    counts = defaultdict(int)
    for f in out:
        counts[f.key.split('|')[2]] += 1
    print(f'  properties: {len(unfilled)} unfilled on records, by kind (script properties): {dict(counts)}')
    rows = sorted({f'{record} {script}.{prop}' for record, script, prop in dangling})
    return out + ([Finding('properties', f'properties|{game}|dangling', 'error',
                           f'{len(rows)} script properties name a FormID no file defines', sample(rows))]
                  if rows else [])
