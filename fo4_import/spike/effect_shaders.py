"""Which Fallout 4 effect shader an FNV script's EffectShader property plays (data/effect_shaders.json).

The build writes no FNV EFSH: Fallout 4's EFSH (form version 106) has no
particle shader and FNV's effect textures do not ship. A converted script's
`EffectShader` property, named as FNV's shader, gets the Fallout4.esm
shader the table names, matched ignoring case as FNV's script names are; a
shader the table leaves out stays empty and is counted.

See: docs/fork/script_markers.md#effect-shaders
"""

import json
from pathlib import Path

from tes5_import.base.tes5_reader import first_sub, walk

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'effect_shaders.json'


def load_table(path: Path = TABLE) -> dict:
    """{FNV effect shader EditorID: Fallout4.esm effect shader EditorID}."""
    return json.loads(path.read_text(encoding='utf-8'))['effect_shaders']


class EffectShaders:
    """The table resolved against Fallout4.esm."""

    def __init__(self, builder, table: 'dict | None' = None):
        """Index FO4's effect shaders; raise when the table names one Fallout4.esm lacks."""
        self.builder, table = builder, load_table() if table is None else table
        fo4 = {(first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252'): rec.form_id
               for rec, _ in walk(builder.fo4, b'EFSH')}
        missing = sorted(set(table.values()) - set(fo4))
        if missing:
            raise ValueError(f'effect_shaders.json names effect shaders Fallout4.esm lacks: {missing}')
        self.mapped = {fnv.lower(): fo4[name] for fnv, name in table.items()}
        self.unmapped = set()

    def of(self, prop: str) -> 'int | None':
        """The Fallout4.esm shader for the FNV shader `prop` names; None when unmapped, counted once."""
        fid = self.mapped.get(prop.lower())
        if fid is None and prop.lower() not in self.unmapped:
            self.unmapped.add(prop.lower())
            self.builder.counts[f'EffectShader not mapped ({prop})'] += 1
        return fid
