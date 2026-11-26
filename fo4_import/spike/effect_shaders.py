"""Which Fallout 4 effect shader an FNV script's EffectShader property plays (data/effect_shaders.json).

The build writes no FNV EFSH: Fallout 4's EFSH (form version 106) has no
particle shader and FNV's effect textures do not ship. A converted script's
`EffectShader` property, named as FNV's shader, gets the Fallout4.esm
shader the table names, matched ignoring case as FNV's script names are.
A shader the table leaves out is routed, each route counted: a stealth
shader (stealth_shaders) plays as STEALTH; else it takes a listed one's
not playing as STEALTH (route): one with the same particle texture, else fill texture, else any;
the nearest in fill and edge color, then with the same membrane and particle
shaders on.

See: docs/fork/script_markers.md#effect-shaders
"""

import json
import math
import re
from pathlib import Path

from fo4_import.pipeline.export_index import export_records
from tes5_import.base.tes5_reader import first_sub, walk

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'effect_shaders.json'
#: FNV EFSH DATA flags No Membrane Shader and No Particle Shader (xEdit wbDefinitionsFNV).
SHADERS_OFF = 0x1 | 0x8
#: FNV actor values Invisibility and Chameleon (xEdit wbDefinitionsFNV actor values 48, 49), as the export writes.
HIDING = frozenset(('48', '49'))
#: The Fallout4.esm shader a stealth shader plays as.
STEALTH = 'StealthBoyInvisibilityEffect'
#: Script lines that open a new branch (their first word, lower case).
BRANCH_WORDS = frozenset(('if', 'elseif', 'else', 'endif', 'begin', 'end'))
#: A shader played, and a spell added or removed, in FNV script text.
PLAYED = re.compile(r'\b(?:pms|playmagicshadervisuals)\s+(\w+)', re.I)
SPELL_CHANGED = re.compile(r'\b(?:addspell|removespell)\s+(\w+)', re.I)


def load_table(path: Path = TABLE) -> dict:
    """{FNV effect shader EditorID: Fallout4.esm effect shader EditorID}."""
    return json.loads(path.read_text(encoding='utf-8'))['effect_shaders']


def hiding_spells(spells) -> set:
    """Lower-case EditorIDs of SPEL export records with an effect on HIDING."""
    return {rec.get('EditorID', '').lower() for rec in spells
            if any(rec.get(f'Effect[{i}].ActorValue') in HIDING for i in range(int(rec.get('EffectCount', 0) or 0)))}


def branches(text: str) -> list:
    """FNV script `text` split at each BRANCH_WORDS line, comments dropped: [branch text]."""
    out = ['']
    for line in text.splitlines():
        code = line.split(';')[0].strip()
        if code.split(' ')[0].lower() in BRANCH_WORDS:
            out.append('')
        out[-1] += code + '\n'
    return out


def stealth_shaders(texts, hiding: set) -> set:
    """Lower-case shader names that script `texts` play in a branch adding or removing a `hiding` spell."""
    out = set()
    for branch in (b for text in texts for b in branches(text)):
        if any(spell.lower() in hiding for spell in SPELL_CHANGED.findall(branch)):
            out.update(name.lower() for name in PLAYED.findall(branch))
    return out


def script_texts(export_dir) -> list:
    """Export `export_dir`'s script texts: SCPT, INFO result, PACK event."""
    texts = [rec.get('SCTX', '') for rec in export_records(export_dir, 'SCPT')]
    texts += [rec.get('ResultScript', '') for rec in export_records(export_dir, 'INFO')]
    return texts + [v for rec in export_records(export_dir, 'PACK') for k, v in rec.items() if k.endswith('.Script')]


def texture(rec: dict, tag: str) -> str:
    """EFSH `rec`'s `tag` texture path, lower case; '' without one."""
    return rec.get(tag, '').replace('/', chr(92)).lower()


def colors(rec: dict) -> tuple:
    """EFSH `rec`'s fill and edge colors (R, G, B each)."""
    return tuple(int(rec.get(f'DATA.{part}Color{c}') or 0) for part in ('Fill', 'Edge') for c in 'RGB')


def shaders_on(rec: dict) -> int:
    """EFSH `rec`'s SHADERS_OFF flags."""
    return int(rec.get('DATA.Flags') or 0) & SHADERS_OFF


def route(rec: dict, listed: list) -> 'tuple | None':
    """(route, listed EFSH record) for EFSH `rec` among `listed` export records; None when there are none."""
    for name, test in (('same particle texture', lambda r: texture(r, 'ICO2') == texture(rec, 'ICO2') != ''),
                       ('same fill texture', lambda r: texture(r, 'ICON') == texture(rec, 'ICON') != ''),
                       ('nearest color', lambda r: True)):
        near = [r for r in listed if test(r)]
        if near:
            return name, min(near, key=lambda r: (math.dist(colors(r), colors(rec)), shaders_on(r) != shaders_on(rec)))
    return None


class EffectShaders:
    """The table resolved against Fallout4.esm, unlisted shaders routed onto listed ones of the export."""

    def __init__(self, builder, table: 'dict | None' = None):
        """Index FO4's effect shaders; raise when the table or STEALTH names one Fallout4.esm lacks."""
        self.builder, table = builder, load_table() if table is None else table
        self.fo4 = {(first_sub(rec.body, b'EDID') or b'').rstrip(b'\0').decode('cp1252'): rec.form_id
                    for rec, _ in walk(builder.fo4, b'EFSH')}
        missing = sorted({*table.values(), STEALTH} - set(self.fo4))
        if missing:
            raise ValueError(f'effect_shaders.json names effect shaders Fallout4.esm lacks: {missing}')
        self.mapped = {fnv.lower(): self.fo4[name] for fnv, name in table.items()}
        self.routed, self.export, self.stealth = {}, None, None

    def of(self, prop: str) -> 'int | None':
        """The FO4 shader for FNV shader `prop`: the table's, else routed; None."""
        fid = self.mapped.get(prop.lower())
        return fid if fid is not None else self._routed(prop)

    def _routed(self, prop: str) -> 'int | None':
        """`_find` of unlisted shader `prop`, counted once by route; None when not found."""
        key = prop.lower()
        if key not in self.routed:
            found = self._find(key)
            self.routed[key] = found[1] if found else None
            self.builder.counts[f'EffectShader route ({found[0]})' if found else f'EffectShader not mapped ({prop})'] += 1
        return self.routed[key]

    def _find(self, key: str) -> 'tuple | None':
        """(route, FO4 FormID) of the export's shader named `key`: STEALTH's for a stealth shader, else route's."""
        if self.export is None:
            export_dir = self.builder.export_dir
            self.export = {r.get('EditorID', '').lower(): r for r in export_records(export_dir, 'EFSH')}
            self.stealth = stealth_shaders(script_texts(export_dir), hiding_spells(export_records(export_dir, 'SPEL')))
        rec = self.export.get(key)
        if rec is None:
            return None
        if key in self.stealth:
            return 'stealth', self.fo4[STEALTH]
        stealth = self.fo4[STEALTH]
        found = route(rec, [r for name, r in sorted(self.export.items()) if self.mapped.get(name, stealth) != stealth])
        return (found[0], self.mapped[found[1]['EditorID'].lower()]) if found else None
