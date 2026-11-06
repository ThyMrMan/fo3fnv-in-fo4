"""The shader names and texture paths of every NIF a Fallout 4 build wrote, read block by block.

A shader property's name is its material: empty, or a BGSM or BGEM. Any other name (a string index read as the
wrong string, "BSX") makes the game look for a material that is not there. An effect shader never names a BGSM.
The materials and textures found here are resolved with the rest by asset_fo4.

See: docs/fork/fo4_preflight.md#materials
"""

import struct
from collections import defaultdict

from fo4_import.nif.blocks import Reader, read_effect, read_texture_set
from fo4_import.nif.file import read_header
from tools.validate.preflight.asset_load import norm
from tools.validate.preflight.findings import Finding

#: Shader property types: {block type: offset of its name's string index}.
NAME_AT = {'BSLightingShaderProperty': 4, 'BSEffectShaderProperty': 0}

#: The effect shader block, whose material is a BGEM.
EFFECT = 'BSEffectShaderProperty'

#: An effect shader's texture path fields.
EFFECT_TEXTURES = ('source_texture', 'greyscale', 'env_map', 'normal', 'env_mask')

#: Material file endings.
MATERIALS = ('.bgsm', '.bgem')

#: Meshes listed per finding.
SHOWN = 5


def string_at(strings: list, index: int) -> str:
    """String `index` of a NIF's table: '' for -1, `<string N>` past the table."""
    if index == -1:
        return ''
    return strings[index] if 0 <= index < len(strings) else f'<string {index}>'


def shader_parts(data: bytes) -> tuple:
    """([(shader block type, name)], [texture paths]) of a Fallout 4 NIF's shader properties and texture sets."""
    nif, entries, pos = read_header(data)
    names, textures = [], []
    for kind, size in entries:
        raw, pos = data[pos:pos + size], pos + size
        if kind in NAME_AT:
            names.append((kind, string_at(nif.strings, struct.unpack_from('<i', raw, NAME_AT[kind])[0])))
        if kind == 'BSShaderTextureSet':
            textures += read_texture_set(Reader(raw))['textures']
        elif kind == EFFECT:
            effect = read_effect(Reader(raw))
            textures += [effect[k] for k in EFFECT_TEXTURES]
    return names, [t for t in textures if t]


def name_problem(kind: str, name: str) -> 'str | None':
    """Why a shader's name is wrong (`shader-name`, `effect-bgsm`), or None."""
    low = name.lower()
    if kind == EFFECT and low.endswith('.bgsm'):
        return 'effect-bgsm'
    return None if not name or low.endswith(MATERIALS) else 'shader-name'


_WHAT = {'shader-name': 'is not a .bgsm or .bgem: the game looks for a material of that name and draws purple',
         'effect-bgsm': 'is a .bgsm on an effect shader, which reads only a .bgem'}


def built_nifs(files) -> list:
    """Data paths of the NIFs in `files` (the build's folder), loose or archived."""
    return sorted(p for p in {*files.loose(), *files.archived()} if p.endswith('.nif'))


def scan(own, paths: list, materials: dict, textures: dict) -> tuple:
    """({(problem, name): meshes}, [unreadable meshes]); adds each NIF's materials and textures to the maps."""
    bad, unreadable = defaultdict(set), []
    for path in paths:
        try:
            names, named = shader_parts(own.read(path))
        except (ValueError, struct.error, UnicodeDecodeError, IndexError):
            unreadable.append(path)
            continue
        for kind, name in names:
            problem = name_problem(kind, name)
            if problem:
                bad[problem, name].add(path)
            elif name:
                materials[norm(name, 'materials')].add(path)
        for tex in named:
            textures[norm(tex, 'textures')].add(path)
    return bad, unreadable


def audit(game: str, own, materials: dict, textures: dict) -> list:
    """Findings for wrong shader names over every NIF in `own`; their materials and textures join the maps."""
    bad, unreadable = scan(own, built_nifs(own), materials, textures)
    out = [Finding('assets', f'assets|{game}|{problem}|{name}', 'error',
                   f'shader name "{name}" in {len(meshes)} meshes {_WHAT[problem]}',
                   tuple(sorted(meshes)[:SHOWN]))
           for (problem, name), meshes in sorted(bad.items())]
    return out + [Finding('assets', f'assets|{game}|unreadable|{path}', 'review',
                          f'{path} is not a Fallout 4 NIF the audit can read') for path in unreadable]
